"""Non-blocking human-recording preparation; one call per workflow poll, no Lambda sleeps."""
import hashlib
import json
import math
import re
from botocore.exceptions import ClientError
from human_alignment import align
from pipeline import validate_passage

MISSING = {'NoSuchKey', '404', 'NotFound'}
MAX_AUDIO_BYTES = 100 * 1024 * 1024
MAX_JSON_BYTES = 5 * 1024 * 1024


def transcription_identity(audio_hash, language, bucket=None):
    if not isinstance(audio_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', audio_hash):
        raise ValueError('audio.sha256 must be the recording SHA-256')
    if language != 'en-US':
        raise ValueError('Human alignment currently supports en-US passages')
    bucket_scope = '-'+hashlib.sha256(bucket.encode()).hexdigest()[:8] if bucket else ''
    return (f'soundworks-human-{audio_hash[:32]}{bucket_scope}-{language}-v1',
            f'human-transcripts/{audio_hash}/{language}-v1.json')


def read_json(s3, bucket, key, optional=False):
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if optional and error.response['Error']['Code'] in MISSING:
            return None, None
        raise
    with response['Body'] as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError('Human preparation JSON is too large')
    return json.loads(raw), response.get('ETag')


def put_json(s3, bucket, key, data, immutable=False, **conditions):
    return s3.put_object(Bucket=bucket, Key=key,
                         Body=json.dumps(data, ensure_ascii=False).encode(), ContentType='application/json',
                         CacheControl='public,max-age=31536000,immutable' if immutable else 'no-cache,no-store',
                         **conditions)


def validate_request(request, source_key, bucket=None):
    validate_passage(request)
    if source_key != f"human-passages/{request['id']}.json":
        raise ValueError('Source key must match the passage id')
    audio = request.get('audio')
    if not isinstance(audio, dict):
        raise ValueError('audio must describe the approved recording')
    job_name, transcript_key = transcription_identity(audio.get('sha256', ''), request['language'], bucket)
    if audio.get('key') != f"human-input/{audio['sha256']}/audio.mp3":
        raise ValueError('audio.key must name the content-addressed human-input MP3')
    if not isinstance(audio.get('sourceUrl'), str) or not audio['sourceUrl'].startswith('https://'):
        raise ValueError('audio.sourceUrl must use HTTPS')
    for flag in ('qaVerified', 'cachedOnly'):
        if not isinstance(request.get(flag, False), bool):
            raise ValueError(f'{flag} must be a boolean')
    confidence = request.get('minimumConfidence', .8)
    if isinstance(confidence, bool) or not isinstance(confidence, (int,float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError('minimumConfidence must be between 0 and 1')
    return audio, job_name, transcript_key


def verify_recording(s3, bucket, key, expected_hash, etag):
    response = s3.get_object(Bucket=bucket, Key=key, IfMatch=etag)
    digest, size = hashlib.sha256(), 0
    with response['Body'] as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            if size > MAX_AUDIO_BYTES:
                raise ValueError('Human recording exceeds 100 MB')
            digest.update(block)
    if not size or digest.hexdigest() != expected_hash:
        raise ValueError('Human recording bytes do not match audio.sha256')


def publish_pointer(s3, bucket, source_key, source_etag, manifest):
    # Read the pointer *before* rechecking the source. A concurrent newer publisher
    # then changes its ETag, so an old run cannot overwrite the newer pointer.
    pointer_key = f"generated/{manifest['id']}/current.json"
    _, pointer_etag = read_json(s3, bucket, pointer_key, optional=True)
    if s3.head_object(Bucket=bucket, Key=source_key)['ETag'] != source_etag:
        return False
    condition = {'IfMatch': pointer_etag} if pointer_etag else {'IfNoneMatch': '*'}
    try:
        put_json(s3, bucket, pointer_key,
                 {'manifestUrl': f"/generated/{manifest['id']}/{manifest['assetVersion']}/manifest.json",
                  'assetVersion': manifest['assetVersion'], 'sourceETag': source_etag}, **condition)
    except ClientError as error:
        if error.response['Error']['Code'] in {'PreconditionFailed', '412', 'ConditionalRequestConflict', '409'}:
            return False
        raise
    return True


def advance(s3, transcribe, bucket, state):
    source_key = state.get('sourceKey', '')
    if not isinstance(source_key, str) or not re.fullmatch(r'human-passages/[A-Za-z0-9_-]+\.json', source_key):
        raise ValueError('Expected a human-passages/PASSAGE_ID.json source key')
    request, source_etag = read_json(s3, bucket, source_key)
    if state.get('sourceETag') and state['sourceETag'] != source_etag:
        return {**state, 'status': 'superseded'}
    audio, job_name, transcript_key = validate_request(request, source_key, bucket)
    audio_head = s3.head_object(Bucket=bucket, Key=audio['key'])
    if not 0 < audio_head['ContentLength'] <= MAX_AUDIO_BYTES:
        raise ValueError('Human recording must be between 1 byte and 100 MB')
    if state.get('audioETag') and state['audioETag'] != audio_head['ETag']:
        raise ValueError('Recording changed during preparation; upload it under its new SHA-256')
    if not state.get('audioETag'):
        verify_recording(s3, bucket, audio['key'], audio['sha256'], audio_head['ETag'])
    state = {'sourceKey': source_key, 'sourceETag': source_etag, 'audioETag': audio_head['ETag'],
             'passageId': request['id'], 'jobName': job_name}
    transcript, _ = read_json(s3, bucket, transcript_key, optional=True)
    if transcript is None:
        if request.get('cachedOnly', False):
            return {**state, 'status': 'failed', 'reason': 'No cached transcript; cachedOnly prevents a new paid transcription job'}
        try:
            job = transcribe.get_transcription_job(TranscriptionJobName=job_name)['TranscriptionJob']
        except ClientError as error:
            if error.response['Error']['Code'] != 'BadRequestException':
                raise
            try:
                job = transcribe.start_transcription_job(
                    TranscriptionJobName=job_name, LanguageCode=request['language'], MediaFormat='mp3',
                    Media={'MediaFileUri': f"s3://{bucket}/{audio['key']}"},
                    OutputBucketName=bucket, OutputKey=transcript_key)['TranscriptionJob']
            except ClientError as conflict:
                if conflict.response['Error']['Code'] != 'ConflictException':
                    raise
                job = transcribe.get_transcription_job(TranscriptionJobName=job_name)['TranscriptionJob']
        if job['TranscriptionJobStatus'] == 'FAILED':
            return {**state, 'status': 'failed', 'reason': job.get('FailureReason', 'Transcription failed')}
        if job['TranscriptionJobStatus'] != 'COMPLETED':
            return {**state, 'status': 'processing'}
        transcript, _ = read_json(s3, bucket, transcript_key)
    manifest, report = align(request, transcript, audio['sha256'], audio['sourceUrl'],
                             minimum_confidence=request.get('minimumConfidence', .8),
                             qa_verified=request.get('qaVerified', False))
    prefix = f"generated/{request['id']}/{manifest['assetVersion']}"
    # Copy exactly the same bytes that were transcribed. No synthesis or transcoding.
    audio_ready = False
    try:
        existing_audio = s3.head_object(Bucket=bucket, Key=prefix+'/audio.mp3')
        audio_ready = (existing_audio.get('Metadata', {}).get('sha256') == audio['sha256']
                       and existing_audio['ContentLength'] == audio_head['ContentLength'])
    except ClientError as error:
        if error.response['Error']['Code'] not in MISSING:
            raise
    if not audio_ready:
        s3.copy_object(Bucket=bucket, Key=prefix+'/audio.mp3',
                       CopySource={'Bucket': bucket, 'Key': audio['key']},
                       CopySourceIfMatch=state['audioETag'], MetadataDirective='REPLACE',
                       Metadata={'sha256': audio['sha256']},
                       ContentType='audio/mpeg', CacheControl='public,max-age=31536000,immutable')
    for filename, data in [('timings.json', manifest['timings']), ('alignment-report.json', report),
                           ('manifest.json', manifest)]:
        put_json(s3, bucket, prefix+'/'+filename, data, immutable=True)
    published = publish_pointer(s3, bucket, source_key, source_etag, manifest)
    return {**state, 'status': 'ready' if published else 'superseded',
            'manifestUrl': '/'+prefix+'/manifest.json', 'alignedWords': report['alignedWords'],
            'sourceWords': report['sourceWords'], 'coverage': report['coverage'],
            'needsReview': report['needsReview']}
