"""Prepare passages on IAM invocation or changes to private S3 passages/*.json."""
import json
import os
import tempfile
from urllib.parse import unquote_plus
import boto3
from botocore.config import Config
from pipeline import prepare, read_stream, validate_passage


def process_passage(passage, polly, s3, bucket, voice, force=False):
    with tempfile.TemporaryDirectory() as directory:
        result = prepare(passage, directory, polly, s3=s3, bucket=bucket, voice=voice, force=force)
    manifest = result['manifest']
    return {'status': 'ready', 'manifestUrl': result['manifestUrl'], 'assetVersion': manifest['assetVersion'],
            'words': len(manifest['tokens']), 'generation': manifest['generation'],
            'cached': result['cached'], 'cacheSource': result['cacheSource'],
            'synthesisRequestCharacters': result['synthesisRequestCharacters']}


def handler(event, context):
    s3 = boto3.client('s3')
    polly = boto3.client('polly', config=Config(retries={'mode': 'standard', 'max_attempts': 4}))
    bucket = os.environ['ASSET_BUCKET']
    voice = os.environ.get('POLLY_VOICE', 'Stephen')
    if isinstance(event, dict) and 'Records' in event:
        results = []
        for record in event['Records']:
            if record.get('eventSource') != 'aws:s3' or not record.get('eventName', '').startswith('ObjectCreated:'):
                continue
            source_bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            if source_bucket != bucket or not key.startswith('passages/') or not key.endswith('.json'):
                continue
            # S3 events can arrive out of order. Always prepare the current object,
            # never overwrite its output with the older event's object version.
            response = s3.get_object(Bucket=bucket, Key=key)
            if response.get('ContentLength', 0) > 1000000:
                response['Body'].close()
                raise ValueError('Source passage JSON exceeds 1 MB')
            passage = json.loads(read_stream(response, 'Body'))
            validate_passage(passage)
            if key != f"passages/{passage['id']}.json":
                raise ValueError('Source key must be passages/<passage id>.json')
            result = process_passage(passage, polly, s3, bucket, voice)
            result.update({'sourceKey': key, 'sourceVersionId': response.get('VersionId')})
            # A durable per-input result is useful for asynchronous event verification.
            status_key = f"generated/{passage['id']}/events/{passage['id']}-{result['generation']['textHash']}.json"
            s3.put_object(Bucket=bucket, Key=status_key, Body=json.dumps(result).encode(),
                          ContentType='application/json', CacheControl='no-store')
            print(json.dumps(result))
            results.append(result)
        return {'results': results}
    passage = event.get('passage') if isinstance(event, dict) else None
    try:
        validate_passage(passage)
    except ValueError as error:
        return {'status': 'invalid_input', 'error': str(error)}
    return process_passage(passage, polly, s3, bucket, voice, force=event.get('force') is True)
