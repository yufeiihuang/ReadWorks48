import contextlib
import copy
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pipeline import cache_key, cached_manifest, prepare
from test_pipeline import FakePolly, passage
import handler


class S3Error(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {'Error': {'Code': code}}


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.fail_manifest = False
        self.deny = False

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[Key] = {'body': Body, 'metadata': kwargs.get('Metadata', {})}
        return {}

    def upload_file(self, filename, bucket, key, ExtraArgs):
        if self.fail_manifest and key.endswith('/manifest.json'):
            raise RuntimeError('Simulated upload failure')
        self.put_object(Bucket=bucket, Key=key, Body=Path(filename).read_bytes(), **ExtraArgs)

    def get_object(self, Bucket, Key):
        if self.deny:
            raise S3Error('AccessDenied')
        if Key not in self.objects:
            raise S3Error('NoSuchKey')
        obj = self.objects[Key]
        return {'Body': io.BytesIO(obj['body']), 'ContentLength': len(obj['body']),
                'VersionId': hashlib.sha256(obj['body']).hexdigest()}

    def head_object(self, Bucket, Key):
        response = self.get_object(Bucket, Key)
        response['Body'].close()
        return {'ContentLength': response['ContentLength'], 'Metadata': self.objects[Key]['metadata']}


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.store, self.polly = FakeS3(), FakePolly()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_prepare(self, item=None, **kwargs):
        return prepare(item or passage(), self.tmp.name, self.polly, self.store, 'bucket', **kwargs)

    def test_fresh_lambda_reuses_s3_without_synthesizing(self):
        first = self.run_prepare()
        self.assertFalse(first['cached'])
        calls = len(self.polly.calls)
        with tempfile.TemporaryDirectory() as fresh:
            second = prepare(passage(), fresh, self.polly, self.store, 'bucket')
        self.assertTrue(second['cached'])
        self.assertEqual(second['cacheSource'], 's3')
        self.assertEqual(second['synthesisRequestCharacters'], 0)
        self.assertEqual(first['manifestUrl'], second['manifestUrl'])
        self.assertEqual(len(self.polly.calls), calls)

    def test_text_revision_voice_and_pipeline_settings_invalidate_cache(self):
        self.run_prepare()
        for change in ('text', 'revision', 'voice', 'settings'):
            item = copy.deepcopy(passage())
            voice = 'Stephen'
            if change == 'text': item['paragraphs'][0]['text'] += ' More words.'
            if change == 'revision': item['revision'] = 2
            if change == 'voice': voice = 'Matthew'
            calls = len(self.polly.calls)
            if change == 'settings':
                with patch('pipeline.PIPELINE_VERSION', 100):
                    result = self.run_prepare(item, voice=voice)
            else:
                result = self.run_prepare(item, voice=voice)
            self.assertFalse(result['cached'], change)
            self.assertGreater(len(self.polly.calls), calls)

    def test_missing_or_mismatched_assets_are_not_reused(self):
        first = self.run_prepare()
        manifest = first['manifest']
        timings_key = manifest['timingsUrl'].lstrip('/')
        self.store.objects[timings_key]['body'] = b'[]'
        self.assertIsNone(cached_manifest(passage(), 'Stephen', self.store, 'bucket'))
        self.run_prepare()  # Repair from local cache.
        del self.store.objects[manifest['audio']['url'].lstrip('/')]
        self.assertIsNone(cached_manifest(passage(), 'Stephen', self.store, 'bucket'))

    def test_force_bypasses_s3_and_local_caches(self):
        self.run_prepare()
        calls = len(self.polly.calls)
        result = self.run_prepare(force=True)
        self.assertFalse(result['cached'])
        self.assertGreater(len(self.polly.calls), calls)

    def test_access_denied_does_not_silently_spend_on_regeneration(self):
        self.store.deny = True
        with self.assertRaises(S3Error): self.run_prepare()
        self.assertEqual(self.polly.calls, [])

    def test_failed_publish_never_creates_completion_index(self):
        self.store.fail_manifest = True
        with self.assertRaises(RuntimeError): self.run_prepare()
        self.assertNotIn(cache_key(passage(), 'Stephen'), self.store.objects)

    def test_corrupt_index_is_a_cache_miss(self):
        self.store.put_object(Bucket='bucket', Key=cache_key(passage(),'Stephen'), Body=b'{broken')
        self.assertFalse(self.run_prepare()['cached'])


class S3EventTests(unittest.TestCase):
    def setUp(self):
        self.store, self.polly = FakeS3(), FakePolly()
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'ASSET_BUCKET':'bucket', 'POLLY_VOICE':'Stephen'}).start()
        patch.object(handler.boto3,'client',side_effect=lambda name, **kwargs: self.store if name=='s3' else self.polly).start()

    def event(self, key='passages/test.json'):
        return {'Records':[{'eventSource':'aws:s3','eventName':'ObjectCreated:Put',
                            's3':{'bucket':{'name':'bucket'},'object':{'key':key,'versionId':'old-version'}}}]}

    def invoke(self, event):
        with contextlib.redirect_stdout(io.StringIO()):
            return handler.handler(event,None)

    def upload(self, item):
        self.store.put_object(Bucket='bucket', Key='passages/test.json', Body=json.dumps(item).encode())

    def test_upload_edit_and_duplicate_notification(self):
        self.upload(passage())
        first = self.invoke(self.event())['results'][0]
        self.assertFalse(first['cached'])
        calls = len(self.polly.calls)
        duplicate = self.invoke(self.event())['results'][0]
        self.assertTrue(duplicate['cached'])
        self.assertEqual(len(self.polly.calls),calls)
        edited = passage('The passage has been edited.')
        self.upload(edited)
        result = self.invoke(self.event())['results'][0]
        self.assertFalse(result['cached'])
        self.assertNotEqual(first['assetVersion'],result['assetVersion'])
        self.assertEqual(result['generation']['textHash'], __import__('pipeline').fingerprint(edited,'Stephen'))
        # Even a delayed old event reads the current source, which is cached now.
        self.assertTrue(self.invoke(self.event())['results'][0]['cached'])

    def test_generated_files_do_not_trigger_recursive_generation(self):
        self.assertEqual(self.invoke(self.event('generated/test/cache/result.json')),{'results':[]})
        self.assertEqual(self.polly.calls,[])

    def test_source_filename_must_match_passage_id(self):
        self.upload({**passage(), 'id':'different'})
        with self.assertRaisesRegex(ValueError,'Source key'): self.invoke(self.event())
        self.assertEqual(self.polly.calls,[])
