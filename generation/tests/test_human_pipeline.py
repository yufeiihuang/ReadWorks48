import hashlib
import io
import json
import unittest
from botocore.exceptions import ClientError
from human_pipeline import advance, publish_pointer, transcription_identity
from human_start import start
from test_pipeline import passage
from test_human_alignment import transcript


def error(code):
    return ClientError({'Error': {'Code': code, 'Message': code}}, 'Test')


class Store:
    def __init__(self):
        self.objects = {}
        self.copies = []
        self.before_pointer_put = None

    def put_object(self, Bucket, Key, Body, **kwargs):
        if Key.endswith('/current.json') and self.before_pointer_put:
            callback, self.before_pointer_put = self.before_pointer_put, None
            callback()
        current = self.objects.get(Key)
        if kwargs.get('IfNoneMatch') == '*' and current:
            raise error('PreconditionFailed')
        if 'IfMatch' in kwargs and (not current or current['ETag'] != kwargs['IfMatch']):
            raise error('PreconditionFailed')
        data = Body.encode() if isinstance(Body, str) else Body
        self.objects[Key] = {**kwargs, 'body': data, 'ETag': '"'+hashlib.md5(data).hexdigest()+'"'}
        return {'ETag': self.objects[Key]['ETag']}

    def get_object(self, Bucket, Key, **kwargs):
        if Key not in self.objects:
            raise error('NoSuchKey')
        obj = self.objects[Key]
        if 'IfMatch' in kwargs and obj['ETag'] != kwargs['IfMatch']:
            raise error('PreconditionFailed')
        return {'Body': io.BytesIO(obj['body']), 'ETag': obj['ETag']}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise error('NoSuchKey')
        obj = self.objects[Key]
        return {'ContentLength': len(obj['body']), 'ETag': obj['ETag'], 'Metadata': obj.get('Metadata', {})}

    def copy_object(self, Bucket, Key, CopySource, CopySourceIfMatch, **kwargs):
        data = self.get_object(Bucket=Bucket, Key=CopySource['Key'], IfMatch=CopySourceIfMatch)['Body'].read()
        self.copies.append((CopySource['Key'], Key))
        return self.put_object(Bucket=Bucket, Key=Key, Body=data, **kwargs)

    def json(self, key, data):
        return self.put_object(Bucket='bucket', Key=key, Body=json.dumps(data).encode())


class Transcribe:
    def __init__(self):
        self.jobs = {}
        self.starts = 0
        self.fail_start = False

    def get_transcription_job(self, TranscriptionJobName):
        if TranscriptionJobName not in self.jobs:
            raise error('BadRequestException')
        return {'TranscriptionJob': self.jobs[TranscriptionJobName]}

    def start_transcription_job(self, **kwargs):
        self.starts += 1
        if self.fail_start:
            raise error('AccessDeniedException')
        job = {'TranscriptionJobStatus': 'IN_PROGRESS', **kwargs}
        self.jobs[kwargs['TranscriptionJobName']] = job
        return {'TranscriptionJob': job}


class HumanPreparationTests(unittest.TestCase):
    def setUp(self):
        self.s3, self.service = Store(), Transcribe()
        self.audio = b'original approved MP3 bytes'
        self.sha = hashlib.sha256(self.audio).hexdigest()
        self.audio_key = f'human-input/{self.sha}/audio.mp3'
        self.source_key = 'human-passages/test.json'
        self.request = {**passage('The park is quiet.'), 'qaVerified': True,
                        'audio': {'key': self.audio_key, 'sha256': self.sha, 'sourceUrl': 'https://example.com/a.mp3'}}
        self.s3.put_object(Bucket='bucket', Key=self.audio_key, Body=self.audio)
        self.s3.json(self.source_key, self.request)
        self.job, self.transcript_key = transcription_identity(self.sha, 'en-US', 'bucket')

    def run_step(self, state=None):
        return advance(self.s3, self.service, 'bucket', state or {'sourceKey': self.source_key})

    def cache_transcript(self):
        self.s3.json(self.transcript_key, transcript(['The', 'park', 'is', 'quiet']))

    def test_starts_once_returns_immediately_then_publishes_the_original_audio(self):
        state = self.run_step()
        self.assertEqual(state['status'], 'processing')
        self.assertEqual(self.run_step(state)['status'], 'processing')
        self.assertEqual(self.service.starts, 1)
        self.cache_transcript()
        result = self.run_step(state)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['coverage'], 1)
        manifest = json.loads(self.s3.objects[result['manifestUrl'][1:]]['body'])
        audio = self.s3.objects[manifest['audio']['url'][1:]]
        self.assertEqual(audio['body'], self.audio)
        self.assertEqual(audio['ContentType'], 'audio/mpeg')
        pointer = self.s3.objects['generated/test/current.json']
        self.assertEqual(json.loads(pointer['body'])['manifestUrl'], result['manifestUrl'])
        self.assertEqual(pointer['CacheControl'], 'no-cache,no-store')
        self.run_step()
        self.assertEqual(len(self.s3.copies), 1)

    def test_cached_recording_never_starts_a_new_job_even_when_text_is_edited(self):
        self.cache_transcript()
        first = self.run_step()
        self.request['paragraphs'][0]['text'] = 'The park is quiet!'
        self.s3.json(self.source_key, self.request)
        second = self.run_step()
        self.assertEqual(self.service.starts, 0)
        self.assertEqual(second['status'], 'ready')
        self.assertNotEqual(first['manifestUrl'], second['manifestUrl'])

    def test_changed_source_cannot_be_published_by_an_older_execution(self):
        state = self.run_step()
        self.request['revision'] = 2
        self.s3.json(self.source_key, self.request)
        self.cache_transcript()
        self.assertEqual(self.run_step(state)['status'], 'superseded')
        self.assertNotIn('generated/test/current.json', self.s3.objects)

    def test_changed_audio_and_incorrect_hash_are_rejected(self):
        state = self.run_step()
        self.s3.put_object(Bucket='bucket', Key=self.audio_key, Body=b'changed')
        with self.assertRaisesRegex(ValueError, 'Recording changed'):
            self.run_step(state)
        with self.assertRaisesRegex(ValueError, 'SHA-256|sha256'):
            self.run_step()

    def test_failed_job_does_not_replace_working_pointer(self):
        self.s3.json('generated/test/current.json', {'manifestUrl': '/generated/test/old/manifest.json'})
        self.service.jobs[self.job] = {'TranscriptionJobStatus': 'FAILED', 'FailureReason': 'Unsupported media'}
        result = self.run_step()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(json.loads(self.s3.objects['generated/test/current.json']['body'])['manifestUrl'], '/generated/test/old/manifest.json')

    def test_permission_errors_are_not_treated_as_cache_misses(self):
        self.service.fail_start = True
        with self.assertRaises(ClientError):
            self.run_step()

    def test_conditional_pointer_cannot_overwrite_a_concurrent_newer_publication(self):
        self.cache_transcript()
        self.run_step()
        self.s3.before_pointer_put = lambda: self.s3.json('generated/test/current.json', {'manifestUrl': '/newer'})
        state = self.run_step()
        self.assertEqual(state['status'], 'superseded')
        self.assertEqual(json.loads(self.s3.objects['generated/test/current.json']['body'])['manifestUrl'], '/newer')

    def test_invalid_source_keys_and_foreign_audio_keys_are_rejected(self):
        for key in ['passages/test.json', 'human-passages/../test.json', 'generated/test/current.json']:
            with self.assertRaises(ValueError):
                advance(self.s3, self.service, 'bucket', {'sourceKey': key})
        self.request['audio']['key'] = 'generated/unrelated/audio.mp3'
        self.s3.json(self.source_key, self.request)
        with self.assertRaisesRegex(ValueError, 'audio.key'):
            self.run_step()

    def test_identical_audio_in_another_bucket_cannot_collide_with_this_job(self):
        other_job, other_key = transcription_identity(self.sha, 'en-US', 'teammate-bucket')
        self.assertNotEqual(other_job, self.job)
        self.assertEqual(other_key, self.transcript_key)

    def test_nondefault_confidence_is_preserved_for_unverified_recordings(self):
        self.request['qaVerified'] = False
        self.request['minimumConfidence'] = .95
        self.s3.json(self.source_key, self.request)
        self.s3.json(self.transcript_key, transcript([('The', .9), 'park', 'is', 'quiet']))
        result = self.run_step()
        self.assertEqual(result['alignedWords'], 3)
        self.assertTrue(result['needsReview'])

    def test_invalid_confidence_and_nonboolean_qa_flag_are_rejected(self):
        for value in [True, '0.8', -1, float('nan')]:
            self.request['minimumConfidence'] = value
            self.s3.json(self.source_key, self.request)
            with self.assertRaisesRegex(ValueError, 'minimumConfidence'):
                self.run_step()
        self.request.pop('minimumConfidence')
        self.request['qaVerified'] = 'true'
        self.s3.json(self.source_key, self.request)
        with self.assertRaisesRegex(ValueError, 'qaVerified'):
            self.run_step()


class StarterTests(unittest.TestCase):
    def test_duplicate_event_uses_the_same_execution_name(self):
        class Workflow:
            def __init__(self): self.names = set()
            def start_execution(self, **kwargs):
                name = kwargs.get('name')
                if name in self.names: raise error('ExecutionAlreadyExists')
                self.names.add(name)
                return {'executionArn': 'arn:execution'}
        workflow = Workflow()
        self.assertEqual(start(workflow, 'arn:machine', 'human-passages/test.json', 'event1')['status'], 'started')
        self.assertEqual(start(workflow, 'arn:machine', 'human-passages/test.json', 'event1')['status'], 'duplicate')
        self.assertEqual(start(workflow, 'arn:machine', 'human-passages/test.json', 'event2')['status'], 'started')

    def test_s3_starter_ignores_foreign_buckets_and_nonhuman_outputs(self):
        import os
        from unittest.mock import Mock, patch
        import human_start
        service = Mock()
        service.start_execution.return_value = {'executionArn': 'arn:execution'}
        def record(key, bucket='bucket'):
            return {'eventSource': 'aws:s3', 'eventName': 'ObjectCreated:Put',
                    's3': {'bucket': {'name': bucket}, 'object': {'key': key, 'sequencer': '123'}}}
        event = {'Records': [record('human-passages/test.json'), record('passages/test.json'),
                             record('generated/test/current.json'), record('human-input/audio.mp3'),
                             record('human-passages/test.json', 'other-bucket')]}
        with patch.dict(os.environ, {'ASSET_BUCKET': 'bucket', 'HUMAN_WORKFLOW_ARN': 'arn:machine'}), patch('human_start.boto3.client', return_value=service):
            result = human_start.handler(event, None)
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(service.start_execution.call_count, 1)
