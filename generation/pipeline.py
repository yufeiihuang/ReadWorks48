"""Polly Neural narration with byte-accurate word mapping and reusable WAV assets."""
import hashlib
import io
import json
import re
import wave
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

SAMPLE_RATE = 16000
PIPELINE_VERSION = 4  # 4: narrate and time the title before the body
WORD_CLIP_VERSION = 1  # bump to re-synthesize every shared word clip
WORDS_PREFIX = 'generated/words'


def validate_passage(passage):
    if not isinstance(passage, dict):
        raise ValueError('Passage must be a JSON object')
    for field in ('id', 'revision', 'title', 'language', 'paragraphs'):
        if field not in passage:
            raise ValueError(f'Missing required field: {field}')
    if not isinstance(passage['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', passage['id']):
        raise ValueError('Passage id must contain only letters, numbers, underscores, or hyphens')
    if not isinstance(passage['language'], str) or not passage['language']:
        raise ValueError('language must be a nonempty string')
    if not isinstance(passage['title'], str) or not passage['title'].strip():
        raise ValueError('title must be a nonempty string')
    if not isinstance(passage['revision'], int) or isinstance(passage['revision'], bool) or passage['revision'] < 1:
        raise ValueError('revision must be a positive integer')
    paragraphs = passage['paragraphs']
    if not isinstance(paragraphs, list) or not paragraphs:
        raise ValueError('paragraphs must be a nonempty list')
    ids = {'__title__'}  # reserved for title word timings
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict) or not isinstance(paragraph.get('id'), str) or not paragraph['id']:
            raise ValueError('Every paragraph needs a nonempty string id')
        if paragraph['id'] in ids:
            raise ValueError('Paragraph ids must be unique')
        ids.add(paragraph['id'])
        if not isinstance(paragraph.get('text'), str) or not paragraph['text'].strip():
            raise ValueError('Every paragraph needs nonempty text')
    if sum(len(p['text']) for p in paragraphs) > 100000:
        raise ValueError('MVP passage limit is 100,000 characters')


def chunks(text, limit=2800):
    """Preserve exact text; prefer sentence or whitespace boundaries within Polly limits."""
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            candidates = list(re.finditer(r'[.!?][\u201d\u2019\"\']*\s+|\s+', text[start:end]))
            sentences = [m for m in candidates if m.group()[0] in '.!?']
            chosen = sentences[-1] if sentences else (candidates[-1] if candidates else None)
            if chosen is None:
                raise ValueError('A word exceeds the narration chunk limit')
            end = start + chosen.end()
        yield start, text[start:end]
        start = end


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


def map_marks(text, marks, paragraph, char_offset, time_offset, duration_ms, token_index):
    raw = text.encode('utf-8')
    tokens, timings, covered = [], [], set()
    last_end, last_time = 0, -1
    for mark in marks:
        if mark.get('type') != 'word':
            continue
        start, end, time = mark['start'], mark['end'], mark['time']
        if not (isinstance(start, int) and isinstance(end, int) and isinstance(time, int)):
            raise ValueError('Invalid speech mark types')
        if not (last_end <= start < end <= len(raw)) or not (last_time <= time < duration_ms):
            raise ValueError('Speech mark offsets/timestamps are out of range or unordered')
        prefix = raw[:start].decode('utf-8')
        word = raw[start:end].decode('utf-8')
        if word != mark['value']:
            raise ValueError(f'Speech mark does not match display text: {word!r}')
        begin = len(prefix)
        covered.update(range(begin, begin + len(word)))
        token_id = f'w{token_index + len(tokens)}'
        absolute_start = char_offset + begin
        tokens.append({'id': token_id, 'paragraphId': paragraph['id'], 'text': word,
                       'start': utf16_length(paragraph['text'][:absolute_start]),
                       'end': utf16_length(paragraph['text'][:absolute_start + len(word)])})
        timings.append({'tokenId': token_id, 'startMs': round(time_offset + time, 3)})
        last_end, last_time = end, time
    missing = [i for i, char in enumerate(text) if char.isalnum() and i not in covered]
    if missing:
        raise ValueError(f'Unmapped spoken text near {text[max(0, missing[0]-10):missing[0]+20]!r}')
    return tokens, timings


def fingerprint(passage, voice):
    payload = {'pipelineVersion': PIPELINE_VERSION, 'passage': {k: passage[k] for k in ('id', 'revision', 'title', 'language', 'paragraphs')},
               'engine': 'neural', 'voice': voice, 'sampleRate': SAMPLE_RATE}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_stream(response, key='AudioStream'):
    with closing(response[key]) as stream:
        return stream.read()


def word_key(text):
    """Words that differ only by a leading capital share a clip ("The"/"the"); ALL-CAPS words
    like "US" keep their own, since Polly may spell them out."""
    return text.lower() if text[1:] == text[1:].lower() else text


def word_clip_id(text, voice, language):
    payload = {'clipVersion': WORD_CLIP_VERSION, 'word': word_key(text), 'voice': voice,
               'language': language, 'engine': 'neural', 'format': 'mp3'}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def word_clip_key(voice, clip_id):
    return f'{WORDS_PREFIX}/{quote(voice, safe="")}/{clip_id}.mp3'


def _remote_exists(s3, bucket, key):
    try:
        return s3.head_object(Bucket=bucket, Key=key)['ContentLength'] > 0
    except Exception as error:
        if _missing_object(error):
            return False
        raise


def generate_word_clips(tokens, language, output_root, polly, voice, s3=None, bucket=None):
    """Synthesize each unique word on its own, so it starts and ends in silence. Clips are shared by
    every passage with the same voice: a clip already on disk or in the bucket is never re-requested.
    Returns the manifest's wordAudio section and the characters billed."""
    clips, billed, unique = {}, 0, {}
    for token in tokens:
        clip_id = word_clip_id(token['text'], voice, language)
        clips[token['id']] = clip_id
        unique.setdefault(clip_id, word_key(token['text']))
    for clip_id, text in unique.items():
        key = word_clip_key(voice, clip_id)
        path = Path(output_root) / key
        if path.exists() and path.stat().st_size > 0:
            continue
        if bucket and _remote_exists(s3, bucket, key):
            continue
        response = polly.synthesize_speech(Text=text, TextType='text', VoiceId=voice, Engine='neural',
                                           LanguageCode=language, OutputFormat='mp3')
        data = read_stream(response)
        if not data:
            raise ValueError(f'Polly returned no audio for the word {text!r}')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)
        billed += response.get('RequestCharacters', len(text))
    section = {'baseUrl': f'/{WORDS_PREFIX}/{quote(voice, safe="")}/', 'format': 'mp3',
               'voice': voice, 'engine': 'neural', 'clips': clips}
    return section, billed


def generate(passage, output_root, polly, voice='Stephen', force=False, s3=None, bucket=None):
    validate_passage(passage)
    digest = fingerprint(passage, voice)
    directory = Path(output_root) / passage['id'] / digest[:20]
    manifest_path = directory / 'manifest.json'
    if not force and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        audio_path = directory / 'audio.wav'
        if (manifest.get('generation', {}).get('textHash') == digest and audio_path.exists()
                and hashlib.sha256(audio_path.read_bytes()).hexdigest() == manifest['audio']['sha256']
                and (directory / 'timings.json').exists()
                and (directory / 'timings.json').read_text() == json.dumps(manifest['timings'], ensure_ascii=False, indent=2)):
            return manifest, directory, True
    directory.mkdir(parents=True, exist_ok=True)
    audio = bytearray()
    tokens, timings, raw_chunks = [], [], []
    billed = 0
    title_paragraph = {'id': '__title__', 'text': passage['title']}
    for paragraph in [title_paragraph, *passage['paragraphs']]:
        for char_offset, text in chunks(paragraph['text']):
            if not text.strip():
                continue
            settings = dict(Text=text, TextType='text', VoiceId=voice, Engine='neural', LanguageCode=passage['language'])
            audio_response = polly.synthesize_speech(**settings, OutputFormat='pcm', SampleRate=str(SAMPLE_RATE))
            pcm = read_stream(audio_response)
            marks_response = polly.synthesize_speech(**settings, OutputFormat='json', SpeechMarkTypes=['word'])
            marks = [json.loads(line) for line in read_stream(marks_response).decode().splitlines() if line.strip()]
            if not pcm or len(pcm) % 2:
                raise ValueError('Polly returned invalid 16-bit PCM audio')
            offset_ms = len(audio) / 2 / SAMPLE_RATE * 1000
            duration_ms = len(pcm) / 2 / SAMPLE_RATE * 1000
            mapped, times = map_marks(text, marks, paragraph, char_offset, offset_ms, duration_ms, len(tokens))
            tokens.extend(mapped)
            timings.extend(times)
            raw_chunks.append({'paragraphId': paragraph['id'], 'characterOffset': char_offset,
                               'audioOffsetMs': offset_ms, 'durationMs': duration_ms, 'marks': marks})
            audio.extend(pcm)
            # A short boundary pause is part of both the recording and cumulative timing.
            audio.extend(b'\x00\x00' * int(SAMPLE_RATE * .15))
            billed += audio_response.get('RequestCharacters', len(text)) + marks_response.get('RequestCharacters', len(text))
    if not tokens:
        raise ValueError('No spoken words were generated')
    word_audio, word_billed = generate_word_clips(tokens, passage['language'], output_root, polly, voice, s3, bucket)
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio)
    wav_data = buffer.getvalue()
    audio_hash = hashlib.sha256(wav_data).hexdigest()
    asset_version = digest[:20] + '-' + audio_hash[:12]
    relative = f"/generated/{quote(passage['id'], safe='')}/{asset_version}"
    manifest = {**passage, 'schemaVersion': 1, 'assetVersion': asset_version, 'tokens': tokens, 'narrationTitle': title_paragraph,
                'audio': {'url': relative + '/audio.wav', 'format': 'wav', 'engine': 'neural', 'voice': voice,
                          'durationMs': len(audio) / 2 / SAMPLE_RATE * 1000, 'sha256': hashlib.sha256(wav_data).hexdigest()},
                'timings': timings, 'timingsUrl': relative + '/timings.json', 'wordAudio': word_audio,
                'generation': {'status': 'ready', 'engine': 'neural', 'voice': voice, 'textHash': digest,
                               'sampleRate': SAMPLE_RATE, 'chunkCount': len(raw_chunks),
                               'wordClipCount': len(set(word_audio['clips'].values())),
                               'requestCharacters': billed + word_billed, 'wordRequestCharacters': word_billed}}
    (directory / 'audio.wav').write_bytes(wav_data)
    for name, data in [('timings.json', timings), ('speech-marks.json', raw_chunks)]:
        (directory / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    # Publish completion last; a failed generation never installs a ready manifest.
    temporary = directory / 'manifest.tmp'
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    temporary.replace(manifest_path)
    return manifest, directory, False


def publish_word_clips(manifest, output_root, s3, bucket):
    """Upload this passage's word clips that the shared bucket doesn't have yet."""
    voice = manifest['wordAudio']['voice']
    for clip_id in sorted(set(manifest['wordAudio']['clips'].values())):
        key = word_clip_key(voice, clip_id)
        if _remote_exists(s3, bucket, key):
            continue
        path = Path(output_root) / key
        if not path.exists():
            raise ValueError(f'Word clip {clip_id} is missing locally and in the bucket')
        s3.upload_file(str(path), bucket, key,
                       ExtraArgs={'ContentType': 'audio/mpeg', 'CacheControl': 'public,max-age=31536000,immutable',
                                  'Metadata': {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}})


def publish(manifest, directory, s3, bucket, output_root=None):
    prefix = f"generated/{manifest['id']}/{manifest['assetVersion']}"
    # Word clips are uploaded before the manifest that refers to them.
    publish_word_clips(manifest, output_root if output_root is not None else Path(directory).parent.parent, s3, bucket)
    for filename, content_type in [('audio.wav', 'audio/wav'), ('timings.json', 'application/json'), ('speech-marks.json', 'application/json'), ('manifest.json', 'application/json')]:
        path = Path(directory) / filename
        s3.upload_file(str(path), bucket, f'{prefix}/{filename}',
                       ExtraArgs={'ContentType': content_type, 'CacheControl': 'public,max-age=31536000,immutable',
                                  'Metadata': {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}})
    # This mutable completion index is written only after all immutable assets succeed.
    s3.put_object(Bucket=bucket, Key=cache_key(manifest, manifest['generation']['voice']),
                  Body=json.dumps(manifest, ensure_ascii=False).encode(), ContentType='application/json',
                  CacheControl='no-store')
    return f'/{prefix}/manifest.json'


def publish_current(manifest, manifest_url, s3, bucket):
    """Point the passage's permanent address at this version so the reader can find it."""
    s3.put_object(Bucket=bucket, Key=f"generated/{manifest['id']}/current.json",
                  Body=json.dumps({'manifestUrl': manifest_url, 'assetVersion': manifest['assetVersion']}).encode(),
                  ContentType='application/json', CacheControl='public,max-age=60')


def cache_key(passage, voice):
    return f"generated/{passage['id']}/cache/{fingerprint(passage, voice)}.json"


def _missing_object(error):
    return getattr(error, 'response', {}).get('Error', {}).get('Code') in ('NoSuchKey', 'NotFound', '404')


def _get_json(s3, bucket, key):
    response = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(read_stream(response, 'Body'))


def cached_manifest(passage, voice, s3, bucket):
    """Reuse only a complete, matching published recording; permission failures propagate."""
    try:
        manifest = _get_json(s3, bucket, cache_key(passage, voice))
        digest = fingerprint(passage, voice)
        if (fingerprint(manifest, voice) != digest or manifest['generation']['textHash'] != digest
                or manifest['generation']['status'] != 'ready'
                or manifest['generation']['voice'] != voice or manifest['generation']['engine'] != 'neural'
                or manifest['audio']['voice'] != voice or manifest['audio']['engine'] != 'neural'):
            return None
        version = manifest['assetVersion']
        if not re.fullmatch(r'[a-f0-9]{20}-[a-f0-9]{12}', version):
            return None
        prefix = f"generated/{passage['id']}/{version}"
        if manifest['audio']['url'] != f'/{prefix}/audio.wav' or manifest['timingsUrl'] != f'/{prefix}/timings.json':
            return None
        if not manifest['tokens'] or len(manifest['tokens']) != len(manifest['timings']):
            return None
        clips = manifest['wordAudio']['clips']
        if manifest['wordAudio']['baseUrl'] != f'/{WORDS_PREFIX}/{quote(voice, safe="")}/' \
                or set(clips) != {token['id'] for token in manifest['tokens']}:
            return None
        audio = s3.head_object(Bucket=bucket, Key=f'{prefix}/audio.wav')
        if audio['ContentLength'] <= 44 or audio.get('Metadata', {}).get('sha256') != manifest['audio']['sha256']:
            return None
        if _get_json(s3, bucket, f'{prefix}/timings.json') != manifest['timings']:
            return None
        if s3.head_object(Bucket=bucket, Key=f'{prefix}/speech-marks.json')['ContentLength'] <= 0:
            return None
        return manifest
    except (KeyError, TypeError, ValueError, UnicodeError):
        return None
    except Exception as error:
        if _missing_object(error):
            return None
        raise


def prepare(passage, output_root, polly, s3=None, bucket=None, voice='Stephen', force=False):
    """Check shared S3 cache before local generation or any synthesis requests."""
    validate_passage(passage)
    if bucket and not force:
        manifest = cached_manifest(passage, voice, s3, bucket)
        if manifest is not None:
            url = manifest['audio']['url'].rsplit('/', 1)[0] + '/manifest.json'
            publish_current(manifest, url, s3, bucket)
            return {'manifest': manifest, 'directory': None, 'cached': True, 'cacheSource': 's3',
                    'manifestUrl': url, 'synthesisRequestCharacters': 0}
    manifest, directory, cached = generate(passage, output_root, polly, voice=voice, force=force, s3=s3, bucket=bucket)
    url = publish(manifest, directory, s3, bucket, output_root) if bucket else None
    if bucket:
        publish_current(manifest, url, s3, bucket)
    return {'manifest': manifest, 'directory': directory, 'cached': cached,
            'cacheSource': 'local' if cached else None, 'manifestUrl': url,
            'synthesisRequestCharacters': 0 if cached else manifest['generation']['requestCharacters']}
