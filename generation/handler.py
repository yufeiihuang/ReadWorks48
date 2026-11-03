"""Private IAM-invoked passage preparation. Event: {"passage": <manifest input>}."""
import os
import tempfile
import boto3
from botocore.config import Config
from pipeline import generate, publish, validate_passage


def handler(event, context):
    passage = event.get('passage') if isinstance(event, dict) else None
    try:
        validate_passage(passage)
    except ValueError as error:
        return {'status': 'invalid_input', 'error': str(error)}
    polly = boto3.client('polly', config=Config(retries={'mode': 'standard', 'max_attempts': 4}))
    with tempfile.TemporaryDirectory() as directory:
        manifest, output, _ = generate(passage, directory, polly, voice=os.environ.get('POLLY_VOICE', 'Stephen'))
        url = publish(manifest, output, boto3.client('s3'), os.environ['ASSET_BUCKET'])
    return {'status': 'ready', 'manifestUrl': url, 'assetVersion': manifest['assetVersion'],
            'words': len(manifest['tokens']), 'generation': manifest['generation']}
