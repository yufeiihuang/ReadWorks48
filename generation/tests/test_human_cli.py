import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from human_audio import main, upload_recording
from test_human_alignment import transcript
from test_pipeline import passage


class HumanCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root/'passage.json'
        self.source.write_text(json.dumps(passage('The park is quiet.')))
        self.audio = self.root/'audio.mp3'
        self.audio.write_bytes(b'approved sample')
        self.transcript = self.root/'transcript.json'
        self.transcript.write_text(json.dumps(transcript(['The', 'park', 'is', 'quiet'])))
        self.argv = ['human_audio.py', str(self.source), '--audio', str(self.audio),
                     '--audio-url', 'https://example.com/original.mp3', '--qa-verified', '--output', str(self.root/'output')]

    def test_offline_alignment_uses_no_aws_session(self):
        with patch('sys.argv', self.argv+['--transcript', str(self.transcript)]), patch('human_audio.boto3.Session') as session, contextlib.redirect_stdout(io.StringIO()) as output:
            main()
        session.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual(result['coverage'], 1)
        manifest = json.loads(Path(result['manifest']).read_text())
        self.assertTrue(manifest['alignment']['qaVerified'])
        self.assertEqual((Path(result['manifest']).parent/'audio.mp3').read_bytes(), self.audio.read_bytes())

    def test_queue_uploads_recording_before_source_and_never_starts_transcription_locally(self):
        s3 = Mock()
        from botocore.exceptions import ClientError
        s3.head_object.side_effect = ClientError({'Error': {'Code': '404'}}, 'HeadObject')
        session = Mock()
        session.client.return_value = s3
        with patch('sys.argv', self.argv+['--queue', '--cached-only', '--bucket', 'bucket']), patch('human_audio.boto3.Session', return_value=session), contextlib.redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(session.client.call_args_list[0].args, ('s3',))
        self.assertEqual([call[0] for call in s3.method_calls], ['head_object', 'upload_file', 'put_object'])
        request = json.loads(s3.put_object.call_args.kwargs['Body'])
        self.assertEqual(s3.put_object.call_args.kwargs['Key'], 'human-passages/test.json')
        self.assertTrue(request['qaVerified'])
        self.assertTrue(request['cachedOnly'])
        self.assertEqual(request['audio']['sha256'], hashlib.sha256(self.audio.read_bytes()).hexdigest())

    def test_repeated_queue_does_not_upload_another_version_of_unchanged_audio(self):
        sha = hashlib.sha256(self.audio.read_bytes()).hexdigest()
        s3 = Mock()
        s3.head_object.return_value = {'ContentLength': self.audio.stat().st_size, 'Metadata': {'sha256': sha}}
        key = upload_recording(s3, 'bucket', self.audio, sha)
        self.assertEqual(key, f'human-input/{sha}/audio.mp3')
        s3.upload_file.assert_not_called()

    def test_cached_only_cannot_be_silently_ignored_outside_queue_mode(self):
        with patch('sys.argv', self.argv+['--cached-only', '--transcript', str(self.transcript)]), patch('human_audio.boto3.Session') as session, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as failure:
                main()
        self.assertEqual(failure.exception.code, 2)
        session.assert_not_called()
