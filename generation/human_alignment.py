"""Match timestamped Transcribe words to a known passage without invented timestamps."""
import difflib
from collections import Counter
import hashlib
import json
import math
import re
import unicodedata
from pipeline import utf16_length, validate_passage

ALIGNER_VERSION = 5
WORD = re.compile(r"\d{1,3}(?:,\d{3})+(?![\w,])|[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
SMALL = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']


def number_words(number):
    if number < 20: return [SMALL[number]]
    if number < 100: return [TENS[number // 10]] + (number_words(number % 10) if number % 10 else [])
    if number < 1000: return [SMALL[number // 100], 'hundred'] + (number_words(number % 100) if number % 100 else [])
    for scale, name in [(1000000000,'billion'), (1000000,'million'), (1000,'thousand')]:
        if number >= scale:
            return number_words(number // scale) + [name] + (number_words(number % scale) if number % scale else [])
    raise ValueError('Unsupported number')


def canonical_units(text):
    text = unicodedata.normalize('NFC', text).casefold().replace('’', "'")
    if re.fullmatch(r'\d[\d,]*', text):
        value = int(text.replace(',', ''))
        if value < 1000000000000:
            return number_words(value)
    return [re.sub(r'[^\w]', '', part) for part in text.split('-') if re.sub(r'[^\w]', '', part)]


def alignment_hash(passage, audio_hash, confidence, qa_verified=False, audio_url=None, transcript_hash=None):
    source = {key: passage[key] for key in ('id','revision','title','language','paragraphs','source','audio') if key in passage}
    return hashlib.sha256(json.dumps({'passage':source,'audioHash':audio_hash,
        'confidence':confidence,'qaVerified':qa_verified,'audioUrl':audio_url,
        'transcriptHash':transcript_hash,'alignerVersion':ALIGNER_VERSION},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def align(passage, transcript, audio_hash, audio_url, minimum_confidence=.8, qa_verified=False):
    validate_passage(passage)
    if not isinstance(qa_verified, bool):
        raise ValueError('qa_verified must be a boolean')
    if not 0 <= minimum_confidence <= 1:
        raise ValueError('Confidence threshold must be between 0 and 1')
    source_words, source_units = [], []
    for paragraph in passage['paragraphs']:
        for match in WORD.finditer(paragraph['text']):
            word = {'id':f'w{len(source_words)}','paragraphId':paragraph['id'],'text':match.group(),
                    'start':utf16_length(paragraph['text'][:match.start()]),
                    'end':utf16_length(paragraph['text'][:match.end()])}
            index = len(source_words)
            source_words.append(word)
            source_units.extend((unit,index) for unit in canonical_units(word['text']))
    speech, speech_units = [], []
    previous_start = -1
    for item in transcript['results']['items']:
        if item['type'] != 'pronunciation': continue
        alternative = item['alternatives'][0]
        start, end = float(item['start_time'])*1000, float(item['end_time'])*1000
        if not all(math.isfinite(t) for t in (start,end)) or start < 0 or start < previous_start or end <= start:
            raise ValueError('Transcription timestamps must be ordered and valid')
        previous_start = start
        index = len(speech)
        confidence = float(alternative.get('confidence', 0))
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('Transcription confidence must be between 0 and 1')
        speech.append({'text':alternative['content'],'startMs':start,'endMs':end,
                       'confidence':confidence})
        speech_units.extend((unit,index) for unit in canonical_units(alternative['content']))
    matcher = difflib.SequenceMatcher(None,[unit for unit,_ in source_units],
                                     [unit for unit,_ in speech_units],autojunk=False)
    mapping = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            mapping[block.a+offset] = block.b+offset
    # QA verifies the recording against the source text, not the ASR spelling.
    # Recover small one-to-one recognition substitutions between exact context anchors.
    # Do not assign introductions, missing ASR words, or many-to-one phrases a guessed time.
    recovered_units = set()
    joined_units = set()
    source_unit_counts = Counter(i for _,i in source_units)
    speech_unit_counts = Counter(i for _,i in speech_units)
    if qa_verified:
        operations = matcher.get_opcodes()
        for op_index, (kind, a, b, c, d) in enumerate(operations):
            # Exact concatenation handles ASR compounds without changing authoritative text.
            # Require surrounding exact context and complete, independent source words.
            if (kind == 'replace' and 2 <= b-a <= 3 and d-c == 1
                    and op_index > 0 and op_index < len(operations)-1
                    and operations[op_index-1][0] == operations[op_index+1][0] == 'equal'
                    and ''.join(source_units[i][0] for i in range(a,b)) == speech_units[c][0]
                    and speech_unit_counts[speech_units[c][1]] == 1
                    and all(source_unit_counts[source_units[i][1]] == 1 for i in range(a,b))):
                for i in range(a,b):
                    mapping[i] = c
                    joined_units.add(i)
                continue
            if kind != 'replace' or not 0 < b-a == d-c <= 3:
                continue
            if op_index == 0 or op_index == len(operations)-1:
                continue
            before, after = operations[op_index-1], operations[op_index+1]
            if before[0] != 'equal' or after[0] != 'equal':
                continue
            if before[2]-before[1] < 2 or after[2]-after[1] < 2:
                continue
            # Expanded numbers / hyphenated words are not independent timestamps.
            source_ids = [source_units[i][1] for i in range(a,b)]
            speech_ids = [speech_units[i][1] for i in range(c,d)]
            if len(set(source_ids)) != b-a or len(set(speech_ids)) != d-c:
                continue
            if any(source_unit_counts[i] != 1 for i in source_ids):
                continue
            if any(speech_unit_counts[i] != 1 for i in speech_ids):
                continue
            for offset in range(b-a):
                mapping[a+offset] = c+offset
                recovered_units.add(a+offset)
    units_by_word = {}
    for index, (_, word_index) in enumerate(source_units):
        units_by_word.setdefault(word_index,[]).append(index)
    tokens, timings, uncertain, phrase_level = [], [], [], []
    used_speech = set()
    # Index ownership once instead of scanning every match for every word.
    speech_owners = {}
    for source_unit, speech_unit in mapping.items():
        speech_owners.setdefault(speech_units[speech_unit][1],set()).add(source_units[source_unit][1])
    recovered_words = []
    low_confidence_matches = []
    first_timing = None
    last_timing = -1
    for index, word in enumerate(source_words):
        units = units_by_word.get(index,[])
        if not units or any(unit not in mapping for unit in units):
            uncertain.append({**word,'reason':'unmatched'})
            continue
        speech_ids = {speech_units[mapping[unit]][1] for unit in units}
        items = [speech[i] for i in sorted(speech_ids)]
        confidence = min(item['confidence'] for item in items)
        if confidence < minimum_confidence and not qa_verified:
            uncertain.append({**word,'reason':'low_confidence','confidence':confidence})
            continue
        start = min(item['startMs'] for item in items)
        end = max(item['endMs'] for item in items)
        shared = any(speech_owners[speech_id] != {index} for speech_id in speech_ids)
        precision = 'word'
        if shared and all(unit in joined_units for unit in units):
            owners = sorted(speech_owners[next(iter(speech_ids))])
            weights = [len(''.join(canonical_units(source_words[i]['text']))) for i in owners]
            position = owners.index(index)
            span = end-start
            original_start = start
            start = original_start + span * sum(weights[:position]) / sum(weights)
            end = original_start + span * sum(weights[:position+1]) / sum(weights)
            precision = 'estimated'
        elif shared:
            phrase_level.append(word['id'])
            uncertain.append({**word, 'reason': 'phrase_only', 'confidence': confidence})
            continue
        if start < last_timing:
            uncertain.append({**word,'reason':'nonmonotonic'})
            continue
        if any(unit in recovered_units for unit in units):
            recovered_words.append(word['id'])
        if confidence < minimum_confidence:
            low_confidence_matches.append(word['id'])
        tokens.append(word)
        timings.append({'tokenId':word['id'],'startMs':round(start,3),'endMs':round(end,3),
                        'confidence':confidence,'precision':precision,
                        'matchMethod':'qa-compound-split' if precision == 'estimated' else 'qa-context' if any(unit in recovered_units for unit in units) else 'exact'})
        used_speech.update(speech_ids)
        if first_timing is None: first_timing=start
        last_timing=start
    if not tokens:
        raise ValueError('No words matched confidently enough to preview')
    transcript_hash = hashlib.sha256(json.dumps(transcript['results']['items'], sort_keys=True,
        ensure_ascii=False).encode()).hexdigest()
    digest = alignment_hash(passage,audio_hash,minimum_confidence,qa_verified,audio_url,transcript_hash)
    prefix = f"/generated/{passage['id']}/human-{digest[:24]}"
    report = {'sourceWords':len(source_words),'alignedWords':len(tokens),
              'coverage':len(tokens)/len(source_words),'uncertainWords':uncertain,
              'phraseLevelTokenIds':phrase_level,'firstPassageWordMs':first_timing,
              'unassignedSpeech':[item for i,item in enumerate(speech) if i not in used_speech],
              'minimumConfidence':minimum_confidence,'qaVerified':qa_verified,
              'estimatedTokenIds':[t['tokenId'] for t in timings if t['precision'] == 'estimated'],
              'contextRecoveredTokenIds':recovered_words,'acceptedLowConfidenceTokenIds':low_confidence_matches,
              'needsReview':bool(uncertain or phrase_level or any(t['precision'] == 'estimated' for t in timings))}
    manifest = {**passage,'schemaVersion':1,'assetVersion':'human-'+digest[:24],
                'audio':{'url':prefix+'/audio.mp3','sourceUrl':audio_url,'engine':'human','voice':'Original ReadWorks narrator','sha256':audio_hash},
                'tokens':tokens,'timings':timings,'timingsUrl':prefix+'/timings.json',
                'alignment':{'method':'transcribe-text-matching','transcriptHash':transcript_hash,
                             'reportUrl':prefix+'/alignment-report.json',
                             **{k:report[k] for k in ('sourceWords','alignedWords','coverage','needsReview','minimumConfidence','qaVerified')}},
                'generation':{'status':'needs_review' if report['needsReview'] else 'aligned',
                              'engine':'human','textHash':digest,'alignerVersion':ALIGNER_VERSION}}
    # A normalized input may have been copied from an older generated manifest.
    # Human word replay must slice this recording, never inherit Polly word clips.
    manifest.pop('wordAudio', None)
    return manifest,report
