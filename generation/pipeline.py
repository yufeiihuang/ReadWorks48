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


def _escape_with_byte_map(display, ssml_byte_base, display_char_base):
    """XML-escape `display` the same way pronunciation.build_ssml does, while
    recording, for each byte position in the escaped SSML, which ABSOLUTE display
    character index it belongs to. Returns (escaped_str, byte_to_display) where
    byte_to_display maps an absolute SSML byte offset (ssml_byte_base + local) to
    the absolute display char index (display_char_base + local). This lets us
    translate Polly's SSML byte offsets back to display offsets even when escaping
    changes lengths."""
    from pronunciation import _xml_escape
    escaped_parts = []
    byte_to_display = {}
    local_byte = 0
    for display_index, char in enumerate(display):
        piece = _xml_escape(char)
        piece_bytes = piece.encode('utf-8')
        for offset in range(len(piece_bytes)):
            byte_to_display[ssml_byte_base + local_byte + offset] = display_char_base + display_index
        local_byte += len(piece_bytes)
        escaped_parts.append(piece)
    return ''.join(escaped_parts), byte_to_display


def _ssml_segment_layout(text, segments):
    """Return the SSML string and per-segment byte/display layout.

    Mirrors pronunciation.build_ssml exactly. Each plain entry carries a
    byte_to_display map so a speech mark's SSML byte offset resolves to a display
    character index regardless of XML escaping."""
    from pronunciation import _xml_escape
    layout = []
    ssml = '<speak>'
    display_cursor = 0
    for segment in segments:
        display = segment['text']
        display_start = display_cursor
        display_end = display_cursor + len(display)
        if segment['kind'] == 'sub':
            prefix = f'<sub alias="{_xml_escape(segment["alias"])}">'
            escaped = _xml_escape(display)
            open_at = len(ssml.encode('utf-8'))
            ssml += prefix
            content_start = len(ssml.encode('utf-8'))
            ssml += escaped
            content_end = len(ssml.encode('utf-8'))
            ssml += '</sub>'
            byte_end = len(ssml.encode('utf-8'))
            layout.append({'kind': 'sub', 'display_start': display_start, 'display_end': display_end,
                           'byte_start': open_at, 'byte_end': byte_end,
                           'content_byte_start': content_start, 'content_byte_end': content_end})
        else:
            content_start = len(ssml.encode('utf-8'))
            escaped, byte_to_display = _escape_with_byte_map(display, content_start, display_start)
            ssml += escaped
            content_end = len(ssml.encode('utf-8'))
            layout.append({'kind': 'plain', 'display_start': display_start, 'display_end': display_end,
                           'byte_start': content_start, 'byte_end': content_end,
                           'content_byte_start': content_start, 'content_byte_end': content_end,
                           'byte_to_display': byte_to_display})
        display_cursor = display_end
    ssml += '</speak>'
    return ssml, layout


class UnsupportedSSMLMapping(Exception):
    """Raised when SSML speech marks cannot be mapped safely; caller falls back."""


def map_ssml_marks(text, marks, segments, paragraph, char_offset, time_offset, duration_ms, token_index):
    """Map Polly word speech marks from an SSML request back to DISPLAY-text tokens.

    `segments` is pronunciation.build_segments(text, suggestions). The display text
    (and therefore every token offset) comes from `segments`/`text` that we control;
    the spoken alias inside a <sub> is never used for offsets or identity, only its
    timestamp. Raises UnsupportedSSMLMapping if anything looks off, so the caller
    can safely fall back to the plain-text path for this chunk."""
    ssml, layout = _ssml_segment_layout(text, segments)
    raw = ssml.encode('utf-8')
    word_marks = []
    for mark in marks:
        if mark.get('type') != 'word':
            continue
        start, end, time = mark.get('start'), mark.get('end'), mark.get('time')
        if not (isinstance(start, int) and isinstance(end, int) and isinstance(time, int)):
            raise UnsupportedSSMLMapping('Invalid speech mark types')
        if not (0 <= start < end <= len(raw)):
            raise UnsupportedSSMLMapping('Speech mark offset out of range')
        word_marks.append((start, end, time))

    tokens, timings, covered = [], [], set()
    last_time = -1
    for segment_item in layout:
        seg_display_start = segment_item['display_start']
        seg_display_end = segment_item['display_end']
        if segment_item['kind'] == 'sub':
            # One display token for the whole span; timestamp from the first mark
            # whose start falls inside the <sub> content. The alias value/offsets
            # are intentionally ignored.
            hits = [m for m in word_marks
                    if segment_item['content_byte_start'] <= m[0] < segment_item['content_byte_end']]
            if not hits:
                raise UnsupportedSSMLMapping('Substitution produced no spoken word')
            time = min(h[2] for h in hits)
            if not (last_time <= time < duration_ms):
                raise UnsupportedSSMLMapping('Substitution timestamp out of order')
            display_word = text[seg_display_start:seg_display_end]
            token_id = f'w{token_index + len(tokens)}'
            absolute_start = char_offset + seg_display_start
            tokens.append({'id': token_id, 'paragraphId': paragraph['id'], 'text': display_word,
                           'start': utf16_length(paragraph['text'][:absolute_start]),
                           'end': utf16_length(paragraph['text'][:absolute_start + len(display_word)])})
            timings.append({'tokenId': token_id, 'startMs': round(time_offset + time, 3)})
            covered.update(range(seg_display_start, seg_display_end))
            last_time = time
        else:
            # Plain segment: translate each mark's SSML byte offsets back to display
            # char indices via the byte->display map, so XML escaping (e.g. quotes
            # around onomatopoeia) never shifts offsets.
            byte_to_display = segment_item['byte_to_display']
            for start, end, time in word_marks:
                if not (segment_item['byte_start'] <= start < segment_item['byte_end']):
                    continue
                if raw[start:end].decode('utf-8', 'ignore').startswith('<'):
                    continue  # markup token: skip
                display_begin = byte_to_display.get(start)
                # end byte is exclusive; map the last covered byte to its display char
                last_display = byte_to_display.get(end - 1)
                if display_begin is None or last_display is None:
                    raise UnsupportedSSMLMapping('Plain mark offset not on a display boundary')
                display_end = last_display + 1
                display_word = text[display_begin:display_end]
                # Ignore marks that fall only on punctuation/whitespace (not a word).
                if not any(char.isalnum() for char in display_word):
                    continue
                if not (last_time <= time < duration_ms):
                    raise UnsupportedSSMLMapping('Plain speech mark timestamp out of order')
                token_id = f'w{token_index + len(tokens)}'
                absolute_start = char_offset + display_begin
                tokens.append({'id': token_id, 'paragraphId': paragraph['id'], 'text': display_word,
                               'start': utf16_length(paragraph['text'][:absolute_start]),
                               'end': utf16_length(paragraph['text'][:absolute_start + len(display_word)])})
                timings.append({'tokenId': token_id, 'startMs': round(time_offset + time, 3)})
                covered.update(range(display_begin, display_end))
                last_time = time

    # Same coverage guarantee as plain text: every alnum display char is spoken.
    missing = [i for i, char in enumerate(text) if char.isalnum() and i not in covered]
    if missing:
        raise UnsupportedSSMLMapping(
            f'Unmapped spoken text near {text[max(0, missing[0]-10):missing[0]+20]!r}')
    return tokens, timings


def fingerprint(passage, voice, pronunciation=None):
    payload = {'pipelineVersion': PIPELINE_VERSION, 'passage': {k: passage[k] for k in ('id', 'revision', 'title', 'language', 'paragraphs')},
               'engine': 'neural', 'voice': voice, 'sampleRate': SAMPLE_RATE}
    # Only alter the hash when pronunciation substitutions were actually applied,
    # so recordings made with the feature OFF keep their existing identity/cache.
    if pronunciation:
        payload['pronunciation'] = pronunciation
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_stream(response, key='AudioStream'):
    with closing(response[key]) as stream:
        return stream.read()


def word_key(text):
    """Words that differ only by a leading capital share a clip ("The"/"the"); ALL-CAPS words
    like "US" keep their own, since Polly may spell them out."""
    return text.lower() if text[1:] == text[1:].lower() else text


def word_clip_id(text, voice, language, alias=None):
    payload = {'clipVersion': WORD_CLIP_VERSION, 'word': word_key(text), 'voice': voice,
               'language': language, 'engine': 'neural', 'format': 'mp3'}
    # A pronunciation-corrected clip ("Brrr" spoken as "burr") is a distinct asset
    # from the plain clip, so the alias participates in its identity. Omitted when
    # there is no alias, keeping existing clip ids unchanged.
    if alias:
        payload['alias'] = alias
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


def generate_word_clips(tokens, language, output_root, polly, voice, s3=None, bucket=None, aliases=None):
    """Synthesize each unique word on its own, so it starts and ends in silence. Clips are shared by
    every passage with the same voice: a clip already on disk or in the bucket is never re-requested.
    `aliases` optionally maps a display word to its corrected pronunciation; such a clip is
    synthesized from <sub> SSML so isolated playback matches the narration.
    Returns the manifest's wordAudio section and the characters billed."""
    from pronunciation import build_ssml
    aliases = aliases or {}
    clips, billed, unique = {}, 0, {}
    for token in tokens:
        alias = aliases.get(token['text'])
        clip_id = word_clip_id(token['text'], voice, language, alias)
        clips[token['id']] = clip_id
        # Keep the display word (for the <sub> original) and its alias together.
        unique.setdefault(clip_id, (word_key(token['text']), token['text'], alias))
    for clip_id, (spoken, display_word, alias) in unique.items():
        key = word_clip_key(voice, clip_id)
        path = Path(output_root) / key
        if path.exists() and path.stat().st_size > 0:
            continue
        if bucket and _remote_exists(s3, bucket, key):
            continue
        if alias:
            # One-span SSML: <speak><sub alias="burr">Brrr</sub></speak>.
            ssml = build_ssml(display_word, [{'start': 0, 'end': len(display_word),
                                              'original': display_word, 'pronunciation': alias}])
            response = polly.synthesize_speech(Text=ssml, TextType='ssml', VoiceId=voice, Engine='neural',
                                               LanguageCode=language, OutputFormat='mp3')
            billed_text = ssml
        else:
            response = polly.synthesize_speech(Text=spoken, TextType='text', VoiceId=voice, Engine='neural',
                                               LanguageCode=language, OutputFormat='mp3')
            billed_text = spoken
        data = read_stream(response)
        if not data:
            raise ValueError(f'Polly returned no audio for the word {display_word!r}')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)
        billed += response.get('RequestCharacters', len(billed_text))
    section = {'baseUrl': f'/{WORDS_PREFIX}/{quote(voice, safe="")}/', 'format': 'mp3',
               'voice': voice, 'engine': 'neural', 'clips': clips}
    return section, billed


def generate(passage, output_root, polly, voice='Stephen', force=False, s3=None, bucket=None,
             detect=None, pronunciation_enabled=False):
    """Generate narration. When `pronunciation_enabled` and a `detect` callable are
    supplied, onomatopoeia are spoken via <sub alias> SSML while the DISPLAYED text,
    tokens, and timings remain keyed to the original text. `detect(text)` returns raw
    Bedrock suggestions for a chunk; any failure or bad data falls back to plain text."""
    from pronunciation import validate_suggestions, build_segments, build_ssml
    validate_passage(passage)
    use_pronunciation = bool(pronunciation_enabled and detect)
    # Collected only to describe the applied substitutions for the fingerprint.
    applied = []
    aliases = {}

    directory = Path(output_root) / passage['id'] / fingerprint(passage, voice)[:20]
    # When the feature is off the identity is exactly as before; when on, it is
    # recomputed below once we know which substitutions actually applied.
    if not use_pronunciation:
        digest = fingerprint(passage, voice)
        manifest_path = directory / 'manifest.json'
        if not force and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            audio_path = directory / 'audio.wav'
            if (manifest.get('generation', {}).get('textHash') == digest and audio_path.exists()
                    and hashlib.sha256(audio_path.read_bytes()).hexdigest() == manifest['audio']['sha256']
                    and (directory / 'timings.json').exists()
                    and (directory / 'timings.json').read_text() == json.dumps(manifest['timings'], ensure_ascii=False, indent=2)):
                return manifest, directory, True
    audio = bytearray()
    tokens, timings, raw_chunks = [], [], []
    billed = 0
    title_paragraph = {'id': '__title__', 'text': passage['title']}
    for paragraph in [title_paragraph, *passage['paragraphs']]:
        for char_offset, text in chunks(paragraph['text']):
            if not text.strip():
                continue
            suggestions = []
            if use_pronunciation:
                suggestions = validate_suggestions(text, detect(text) or [])
            segments = build_segments(text, suggestions) if suggestions else None
            if segments is not None:
                # SSML path: speak the corrected pronunciation. Falls back to plain
                # text for this chunk if the marks can't be mapped safely.
                ssml = build_ssml(text, suggestions)
                settings = dict(Text=ssml, TextType='ssml', VoiceId=voice, Engine='neural', LanguageCode=passage['language'])
            else:
                settings = dict(Text=text, TextType='text', VoiceId=voice, Engine='neural', LanguageCode=passage['language'])
            audio_response = polly.synthesize_speech(**settings, OutputFormat='pcm', SampleRate=str(SAMPLE_RATE))
            pcm = read_stream(audio_response)
            marks_response = polly.synthesize_speech(**settings, OutputFormat='json', SpeechMarkTypes=['word'])
            marks = [json.loads(line) for line in read_stream(marks_response).decode().splitlines() if line.strip()]
            if not pcm or len(pcm) % 2:
                raise ValueError('Polly returned invalid 16-bit PCM audio')
            offset_ms = len(audio) / 2 / SAMPLE_RATE * 1000
            duration_ms = len(pcm) / 2 / SAMPLE_RATE * 1000
            if segments is not None:
                try:
                    mapped, times = map_ssml_marks(text, marks, segments, paragraph, char_offset,
                                                   offset_ms, duration_ms, len(tokens))
                    for item in suggestions:
                        applied.append({'original': item['original'], 'pronunciation': item['pronunciation']})
                        aliases[item['original']] = item['pronunciation']
                except UnsupportedSSMLMapping:
                    # Re-synthesize this chunk as plain text so narration is never lost.
                    settings = dict(Text=text, TextType='text', VoiceId=voice, Engine='neural', LanguageCode=passage['language'])
                    audio_response = polly.synthesize_speech(**settings, OutputFormat='pcm', SampleRate=str(SAMPLE_RATE))
                    pcm = read_stream(audio_response)
                    marks_response = polly.synthesize_speech(**settings, OutputFormat='json', SpeechMarkTypes=['word'])
                    marks = [json.loads(line) for line in read_stream(marks_response).decode().splitlines() if line.strip()]
                    if not pcm or len(pcm) % 2:
                        raise ValueError('Polly returned invalid 16-bit PCM audio')
                    duration_ms = len(pcm) / 2 / SAMPLE_RATE * 1000
                    mapped, times = map_marks(text, marks, paragraph, char_offset, offset_ms, duration_ms, len(tokens))
            else:
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
    # Identity now reflects the substitutions that actually applied (none -> unchanged).
    pronunciation_summary = sorted(applied, key=lambda s: (s['original'], s['pronunciation'])) or None
    digest = fingerprint(passage, voice, pronunciation_summary)
    directory = Path(output_root) / passage['id'] / digest[:20]
    directory.mkdir(parents=True, exist_ok=True)
    word_audio, word_billed = generate_word_clips(tokens, passage['language'], output_root, polly, voice, s3, bucket, aliases)
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
                               'requestCharacters': billed + word_billed, 'wordRequestCharacters': word_billed,
                               **({'pronunciation': pronunciation_summary} if pronunciation_summary else {})}}
    (directory / 'audio.wav').write_bytes(wav_data)
    for name, data in [('timings.json', timings), ('speech-marks.json', raw_chunks)]:
        (directory / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    # Publish completion last; a failed generation never installs a ready manifest.
    temporary = directory / 'manifest.tmp'
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    temporary.replace(directory / 'manifest.json')
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


def prepare(passage, output_root, polly, s3=None, bucket=None, voice='Stephen', force=False,
            detect=None, pronunciation_enabled=False):
    """Check shared S3 cache before local generation or any synthesis requests."""
    validate_passage(passage)
    # The shared S3 cache is keyed by the plain fingerprint, so it would return a
    # recording made WITHOUT pronunciation substitutions. Skip it when the feature
    # is on; the local path below still avoids re-synthesis via its own identity.
    if bucket and not force and not (pronunciation_enabled and detect):
        manifest = cached_manifest(passage, voice, s3, bucket)
        if manifest is not None:
            url = manifest['audio']['url'].rsplit('/', 1)[0] + '/manifest.json'
            publish_current(manifest, url, s3, bucket)
            return {'manifest': manifest, 'directory': None, 'cached': True, 'cacheSource': 's3',
                    'manifestUrl': url, 'synthesisRequestCharacters': 0}
    manifest, directory, cached = generate(passage, output_root, polly, voice=voice, force=force, s3=s3, bucket=bucket,
                                           detect=detect, pronunciation_enabled=pronunciation_enabled)
    url = publish(manifest, directory, s3, bucket, output_root) if bucket else None
    if bucket:
        publish_current(manifest, url, s3, bucket)
    return {'manifest': manifest, 'directory': directory, 'cached': cached,
            'cacheSource': 'local' if cached else None, 'manifestUrl': url,
            'synthesisRequestCharacters': 0 if cached else manifest['generation']['requestCharacters']}
