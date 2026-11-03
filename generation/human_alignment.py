"""Match timestamped Transcribe words to a known passage without invented timestamps."""
import difflib
import hashlib
import json
import math
import re
import unicodedata
from pipeline import utf16_length, validate_passage

ALIGNER_VERSION = 3
WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
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


def alignment_hash(passage, audio_hash, confidence):
    source = {key: passage[key] for key in ('id','revision','title','language','paragraphs')}
    return hashlib.sha256(json.dumps({'passage':source,'audioHash':audio_hash,
        'confidence':confidence,'alignerVersion':ALIGNER_VERSION},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def align(passage, transcript, audio_hash, audio_url, minimum_confidence=.8):
    validate_passage(passage)
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
        if not all(math.isfinite(t) for t in (start,end)) or start < previous_start or end <= start:
            raise ValueError('Transcription timestamps must be ordered and valid')
        previous_start = start
        index = len(speech)
        speech.append({'text':alternative['content'],'startMs':start,'endMs':end,
                       'confidence':float(alternative.get('confidence',0))})
        speech_units.extend((unit,index) for unit in canonical_units(alternative['content']))
    matcher = difflib.SequenceMatcher(None,[unit for unit,_ in source_units],
                                     [unit for unit,_ in speech_units],autojunk=False)
    mapping = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            mapping[block.a+offset] = block.b+offset
    units_by_word = {}
    for index, (_, word_index) in enumerate(source_units):
        units_by_word.setdefault(word_index,[]).append(index)
    tokens, timings, uncertain, phrase_level = [], [], [], []
    used_speech = set()
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
        if confidence < minimum_confidence:
            uncertain.append({**word,'reason':'low_confidence','confidence':confidence})
            continue
        start = min(item['startMs'] for item in items)
        end = max(item['endMs'] for item in items)
        if start < last_timing:
            uncertain.append({**word,'reason':'nonmonotonic'})
            continue
        shared = any(sum(1 for unit, target in mapping.items()
                         if speech_units[target][1]==speech_id and source_units[unit][1]!=index)>0
                     for speech_id in speech_ids)
        precision = 'word'
        if shared:
            phrase_level.append(word['id'])
            uncertain.append({**word, 'reason': 'phrase_only', 'confidence': confidence})
            continue
        tokens.append(word)
        timings.append({'tokenId':word['id'],'startMs':round(start,3),'endMs':round(end,3),
                        'confidence':confidence,'precision':precision})
        used_speech.update(speech_ids)
        if first_timing is None: first_timing=start
        last_timing=start
    if not tokens:
        raise ValueError('No words matched confidently enough to preview')
    digest = alignment_hash(passage,audio_hash,minimum_confidence)
    prefix = f"/generated/{passage['id']}/human-{digest[:24]}"
    report = {'sourceWords':len(source_words),'alignedWords':len(tokens),
              'coverage':len(tokens)/len(source_words),'uncertainWords':uncertain,
              'phraseLevelTokenIds':phrase_level,'firstPassageWordMs':first_timing,
              'unassignedSpeech':[item for i,item in enumerate(speech) if i not in used_speech],
              'minimumConfidence':minimum_confidence,'needsReview':bool(uncertain or phrase_level)}
    manifest = {**passage,'schemaVersion':1,'assetVersion':'human-'+digest[:24],
                'audio':{'url':prefix+'/audio.mp3','sourceUrl':audio_url,'engine':'human','voice':'Original ReadWorks narrator','sha256':audio_hash},
                'tokens':tokens,'timings':timings,'timingsUrl':prefix+'/timings.json',
                'alignment':{'method':'transcribe-text-matching','reportUrl':prefix+'/alignment-report.json',
                             **{k:report[k] for k in ('sourceWords','alignedWords','coverage','needsReview','minimumConfidence')}},
                'generation':{'status':'needs_review' if report['needsReview'] else 'aligned',
                              'engine':'human','textHash':digest,'alignerVersion':ALIGNER_VERSION}}
    return manifest,report
