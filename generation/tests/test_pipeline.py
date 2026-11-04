import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from pipeline import chunks, generate, map_marks, validate_passage, word_clip_id, word_key


def passage(text='Hello again. Hello world.'):
    return {'id': 'test', 'revision': 1, 'title': 'Test', 'language': 'en-US',
            'paragraphs': [{'id': 'p1', 'text': text}]}


class FakePolly:
    def __init__(self):
        self.calls = []

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs['OutputFormat'] == 'pcm':
            payload = b'\x00\x00' * 16000
        else:
            import re
            text = kwargs['Text']
            words = list(re.finditer(r'\w+', text))
            marks = [{'type': 'word', 'start': len(text[:m.start()].encode()),
                      'end': len(text[:m.end()].encode()), 'value': m.group(),
                      'time': int(i * 900 / len(words))} for i, m in enumerate(words)]
            payload = '\n'.join(json.dumps(m) for m in marks).encode()
        return {'AudioStream': io.BytesIO(payload), 'RequestCharacters': len(kwargs['Text'])}


class PipelineTests(unittest.TestCase):
    def test_title_precedes_body_with_matching_timings(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakePolly()
            item = passage('Hello world.')
            item['title'] = 'A Garden'
            manifest, _, _ = generate(item, tmp, client)
            self.assertEqual(manifest['narrationTitle'], {'id': '__title__', 'text': 'A Garden'})
            self.assertEqual(manifest['paragraphs'], item['paragraphs'])
            self.assertEqual([t['text'] for t in manifest['tokens']], ['A', 'Garden', 'Hello', 'world'])
            self.assertEqual([t['paragraphId'] for t in manifest['tokens']], ['__title__', '__title__', 'p1', 'p1'])
            self.assertEqual(manifest['timings'][0]['startMs'], 0)
            self.assertEqual(manifest['timings'][2]['startMs'], 1150)
            self.assertEqual(client.calls[0]['Text'], 'A Garden')

    def test_chunk_limit_preserves_every_character(self):
        text = ('An accented café is here. ' * 400) + 'Done.'
        parts = list(chunks(text))
        self.assertEqual(''.join(t for _, t in parts), text)
        self.assertTrue(all(len(t) <= 2800 for _, t in parts))
        for start, chunk in parts:
            self.assertEqual(text[start:start + len(chunk)], chunk)

    def test_unsplittable_word_fails(self):
        with self.assertRaisesRegex(ValueError, 'word exceeds'):
            list(chunks('x' * 3001))

    def test_utf8_to_javascript_utf16_and_repeated_words(self):
        text = '😀 café café'
        marks = [{'type': 'word', 'start': 5, 'end': 10, 'value': 'café', 'time': 0},
                 {'type': 'word', 'start': 11, 'end': 16, 'value': 'café', 'time': 500}]
        tokens, timing = map_marks(text, marks, {'id': 'p', 'text': text}, 0, 100, 1000, 0)
        self.assertEqual([t['start'] for t in tokens], [3, 8])
        self.assertEqual([t['end'] for t in tokens], [7, 12])
        self.assertNotEqual(tokens[0]['id'], tokens[1]['id'])
        self.assertEqual(timing[1]['startMs'], 600)

    def test_missing_word_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unmapped'):
            map_marks('Hello world', [{'type':'word','start':0,'end':5,'value':'Hello','time':0}],
                      {'id':'p','text':'Hello world'},0,0,1000,0)

    def test_long_passage_audio_and_marks_share_settings_and_offsets(self):
        item = passage('Hello world. ' * 300)
        with tempfile.TemporaryDirectory() as tmp:
            client = FakePolly()
            manifest, directory, cached = generate(item, tmp, client)
            self.assertFalse(cached)
            self.assertGreater(manifest['generation']['chunkCount'], 1)
            self.assertEqual(len(manifest['tokens']), 601)
            passage_calls = [c for c in client.calls if c['OutputFormat'] != 'mp3']
            for audio_call, mark_call in zip(passage_calls[::2], passage_calls[1::2]):
                for setting in ('Text', 'TextType', 'VoiceId', 'Engine', 'LanguageCode'):
                    self.assertEqual(audio_call[setting], mark_call[setting])
                self.assertEqual(audio_call['VoiceId'], 'Stephen')
            with wave.open(str(directory / 'audio.wav')) as wav:
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.getnframes(), 18400 * manifest['generation']['chunkCount'])
            raw = json.loads((directory / 'speech-marks.json').read_text())
            self.assertEqual(raw[1]['audioOffsetMs'], 1150)
            calls = len(client.calls)
            _, _, cached = generate(item, tmp, client)
            self.assertTrue(cached)
            self.assertEqual(len(client.calls), calls)
            # A modified recording must not be reused.
            (directory / 'audio.wav').write_bytes(b'broken')
            _, _, cached = generate(item, tmp, client)
            self.assertFalse(cached)

    def test_each_unique_word_gets_one_isolated_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakePolly()
            manifest, _, _ = generate(passage('Hello again. hello US us.'), tmp, client)
            words = [c['Text'] for c in client.calls if c['OutputFormat'] == 'mp3']
            # "Hello"/"hello" share a clip; "US" stays separate from "us".
            self.assertEqual(sorted(words), ['US', 'again', 'hello', 'test', 'us'])
            for call in client.calls:
                self.assertEqual((call['VoiceId'], call['Engine']), ('Stephen', 'neural'))
            audio = manifest['wordAudio']
            self.assertEqual(audio['baseUrl'], '/generated/words/Stephen/')
            self.assertEqual(set(audio['clips']), {t['id'] for t in manifest['tokens']})
            self.assertEqual(audio['clips']['w1'], audio['clips']['w3'])
            for clip_id in audio['clips'].values():
                self.assertTrue((Path(tmp) / 'generated/words/Stephen' / f'{clip_id}.mp3').stat().st_size > 0)
            self.assertEqual(manifest['generation']['wordClipCount'], 5)
            self.assertEqual(manifest['generation']['wordRequestCharacters'], 5 + 5 + 2 + 2 + 4)

    def test_word_clips_are_shared_between_passages(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate(passage('Hello world.'), tmp, FakePolly())
            client = FakePolly()
            other = passage('World, hello friend.')
            other['id'] = 'other'
            generate(other, tmp, client)
            self.assertEqual([c['Text'] for c in client.calls if c['OutputFormat'] == 'mp3'], ['friend'])

    def test_word_clip_identity(self):
        self.assertEqual(word_key('Garden'), 'garden')
        self.assertEqual(word_key('NASA'), 'NASA')
        self.assertEqual(word_clip_id('The', 'Stephen', 'en-US'), word_clip_id('the', 'Stephen', 'en-US'))
        self.assertNotEqual(word_clip_id('the', 'Stephen', 'en-US'), word_clip_id('the', 'Joanna', 'en-US'))

    def test_revision_changes_asset_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = passage()
            first, _, _ = generate(item,tmp,FakePolly())
            item['revision'] = 2
            second, _, _ = generate(item,tmp,FakePolly())
            self.assertNotEqual(first['assetVersion'],second['assetVersion'])

    def test_invalid_input_and_duplicate_paragraphs(self):
        with self.assertRaises(ValueError):
            validate_passage(None)
        item = passage()
        item['paragraphs'] *= 2
        with self.assertRaisesRegex(ValueError,'unique'):
            validate_passage(item)


if __name__ == '__main__':
    unittest.main()
