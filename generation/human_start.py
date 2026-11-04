"""Start a workflow for a private human-passages/*.json upload or an IAM retry invocation."""
import hashlib
import json
import os
import re
from urllib.parse import unquote_plus
import boto3
from botocore.exceptions import ClientError


def start(service, workflow_arn, source_key, event_identity=None):
    if not isinstance(source_key, str) or not re.fullmatch(r'human-passages/[A-Za-z0-9_-]+\.json', source_key):
        raise ValueError('Expected human-passages/PASSAGE_ID.json')
    options = {'stateMachineArn': workflow_arn, 'input': json.dumps({'sourceKey': source_key})}
    if event_identity:
        options['name'] = 'human-'+hashlib.sha256(event_identity.encode()).hexdigest()[:48]
    try:
        result = service.start_execution(**options)
        return {'status': 'started', 'executionArn': result['executionArn']}
    except ClientError as error:
        if event_identity and error.response['Error']['Code'] == 'ExecutionAlreadyExists':
            return {'status': 'duplicate'}
        raise


def handler(event, context):
    service = boto3.client('stepfunctions')
    arn = os.environ['HUMAN_WORKFLOW_ARN']
    if 'Records' not in event:
        return start(service, arn, event.get('sourceKey', ''))
    results = []
    for record in event['Records']:
        if record.get('eventSource') != 'aws:s3' or not record.get('eventName', '').startswith('ObjectCreated:'):
            continue
        source = record['s3']
        key = unquote_plus(source['object']['key'])
        if source['bucket']['name'] != os.environ['ASSET_BUCKET'] or not key.startswith('human-passages/') or not key.endswith('.json'):
            continue
        identity = source['bucket']['name']+'/'+key+'/'+str(source['object'].get('sequencer') or source['object'].get('versionId') or record.get('eventTime'))
        results.append(start(service, arn, key, identity))
    return {'results': results}
