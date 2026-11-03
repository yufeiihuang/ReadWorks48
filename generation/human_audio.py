"""Prepare a human-audio preview with cached batch transcription and text matching."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from human_alignment import align, alignment_hash
from pipeline import validate_passage


def transcribe(session, bucket, audio_path, language, maximum_wait):
    audio_hash = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    s3, service = session.client('s3'), session.client('transcribe')
    output_key = f'human-transcripts/{audio_hash}/{language}-v1.json'
    try:
        response = s3.get_object(Bucket=bucket,Key=output_key)
        with response['Body'] as stream: return json.loads(stream.read()), audio_hash, True
    except ClientError as error:
        if error.response['Error']['Code'] not in ('NoSuchKey','404','NotFound'): raise
    name = f'soundworks-human-{audio_hash[:32]}-{language}-v1'
    try:
        job = service.get_transcription_job(TranscriptionJobName=name)['TranscriptionJob']
    except ClientError as error:
        if error.response['Error']['Code'] != 'BadRequestException': raise
        source_key = f'human-input/{audio_hash}/audio.mp3'
        s3.upload_file(str(audio_path),bucket,source_key,ExtraArgs={'ContentType':'audio/mpeg'})
        try:
            job = service.start_transcription_job(TranscriptionJobName=name,LanguageCode=language,MediaFormat='mp3',
                Media={'MediaFileUri':f's3://{bucket}/{source_key}'},OutputBucketName=bucket,
                OutputKey=output_key)['TranscriptionJob']
        except ClientError as conflict:
            if conflict.response['Error']['Code'] != 'ConflictException': raise
            job = service.get_transcription_job(TranscriptionJobName=name)['TranscriptionJob']
    deadline = time.monotonic()+maximum_wait
    print('Transcription status: '+job['TranscriptionJobStatus'],flush=True)
    while job['TranscriptionJobStatus'] not in ('COMPLETED','FAILED'):
        if time.monotonic() >= deadline:
            raise RuntimeError(f'Transcription still running ({name}); rerun to resume without starting a new job')
        time.sleep(5)
        job=service.get_transcription_job(TranscriptionJobName=name)['TranscriptionJob']
    if job['TranscriptionJobStatus']=='FAILED': raise RuntimeError(job.get('FailureReason','Transcription failed'))
    response=s3.get_object(Bucket=bucket,Key=output_key)
    with response['Body'] as stream: return json.loads(stream.read()),audio_hash,False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('passage',type=Path)
    parser.add_argument('--audio',type=Path,required=True,help='Local MP3 of the exact human recording')
    parser.add_argument('--audio-url',required=True,help='Browser-accessible URL for that exact recording')
    parser.add_argument('--bucket',required=True)
    parser.add_argument('--region',default='us-west-2')
    parser.add_argument('--profile')
    parser.add_argument('--confidence',type=float,default=.8)
    parser.add_argument('--maximum-wait',type=int,default=600)
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'output'/'human')
    parser.add_argument('--publish-preview',action='store_true',help='Publish the experimental manifest, including review diagnostics')
    args=parser.parse_args()
    if not 0 <= args.confidence <= 1: parser.error('--confidence must be between 0 and 1')
    if not args.audio.is_file() or args.audio.suffix.lower() != '.mp3': parser.error('--audio must be an existing MP3 file')
    if not args.audio_url.startswith('https://'): parser.error('--audio-url must use HTTPS')
    passage=json.loads(args.passage.read_text());validate_passage(passage)
    session=boto3.Session(profile_name=args.profile,region_name=args.region)
    transcript,audio_hash,cached=transcribe(session,args.bucket,args.audio,passage['language'],args.maximum_wait)
    manifest,report=align(passage,transcript,audio_hash,args.audio_url,args.confidence)
    directory=args.output/passage['id']/alignment_hash(passage,audio_hash,args.confidence)[:24]
    directory.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(args.audio, directory/'audio.mp3')
    for filename,data in [('timings.json',manifest['timings']),('alignment-report.json',report),('manifest.json',manifest)]:
        (directory/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    url=None
    if args.publish_preview:
        s3=session.client('s3')
        prefix=f"generated/{passage['id']}/{manifest['assetVersion']}"
        for filename in ['audio.mp3','timings.json','alignment-report.json','manifest.json']:
            s3.upload_file(str(directory/filename),args.bucket,prefix+'/'+filename,
                          ExtraArgs={'ContentType':'audio/mpeg' if filename == 'audio.mp3' else 'application/json',
                                     'CacheControl':'public,max-age=31536000,immutable'})
        url='/'+prefix+'/manifest.json'
    print(json.dumps({'manifest':str(directory/'manifest.json'),'manifestUrl':url,
        'transcriptionCached':cached,'alignedWords':report['alignedWords'],'sourceWords':report['sourceWords'],
        'coverage':report['coverage'],'needsReview':report['needsReview'],
        'unmatchedWords':[w['text'] for w in report['uncertainWords']],
        'phraseLevelWords':len(report['phraseLevelTokenIds'])},indent=2))


if __name__=='__main__': main()
