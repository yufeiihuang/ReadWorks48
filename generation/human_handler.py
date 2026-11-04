"""IAM-only workflow task: advance human preparation once without waiting inside Lambda."""
import os
import boto3
from botocore.config import Config
from human_pipeline import advance


def handler(event, context):
    session = boto3.Session()
    config = Config(retries={'mode': 'standard', 'max_attempts': 4})
    return advance(session.client('s3', config=config), session.client('transcribe', config=config),
                   os.environ['ASSET_BUCKET'], event)
