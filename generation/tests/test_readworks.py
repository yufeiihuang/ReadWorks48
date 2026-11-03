import json
import tempfile
import unittest
from pathlib import Path
from pipeline import prepare, validate_passage
from readworks import convert, is_readworks, load_passage
from test_pipeline import FakePolly
from test_s3_cache import FakeS3

UUID = '2b781dab-4521-40d2-a9b6-ad5f2bb0ba98'


def product(**changes):
    return {
        'uuid': UUID, 'title': "Let's Meet", 'lang': 'EN', 'au': 'audio_id', 'features': ['au', 'hau'],
        'text': 'A city park is fun. Doug’s job is big.\nHe says, “Parks are great.”',
        'content': '<figure><img alt="a park" src="x.jpg"/><figcaption><p>A caption.</p></figcaption></figure> '
                   '<p>A city park is <span data-vocab-sense-id="1">fun</span>. Doug’s job is big.</p> '
                   '<p>He says, “Parks are great.&rdquo; </p> <p> </p>',
        **changes,
    }


class ConvertTests(unittest.TestCase):
    def test_maps_fields_into_valid_passage(self):
        passage = convert(product())
        validate_passage(passage)
        self.assertEqual(passage['id'], UUID)
        self.assertEqual(passage['language'], 'en-US')
        self.assertEqual(passage['source']['au'], 'audio_id')
        self.assertEqual(passage['paragraphs'], [
            {'id': 'p1', 'text': 'A city park is fun. Doug’s job is big.'},
            {'id': 'p2', 'text': 'He says, “Parks are great.”'},
        ])

    def test_rejects_ebook_style(self):
        with self.assertRaisesRegex(ValueError, 'Ebook'):
            convert(product(features=['au', 'ebook']))

    def test_rejects_displayed_words_missing_from_text(self):
        with self.assertRaisesRegex(ValueError, 'differ'):
            convert(product(content='<h2>A Heading</h2>' + product()['content']))

    def test_rejects_unsupported_language_and_missing_text(self):
        with self.assertRaisesRegex(ValueError, 'language'):
            convert(product(lang='ES'))
        with self.assertRaisesRegex(ValueError, 'text'):
            convert(product(text=''))

    def test_normalized_passages_pass_through_unchanged(self):
        normalized = {'id': 'demo', 'revision': 1, 'title': 'Demo', 'language': 'en-US',
                      'paragraphs': [{'id': 'p1', 'text': 'Hello.'}]}
        self.assertFalse(is_readworks(normalized))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'demo.json'
            path.write_text(json.dumps(normalized))
            self.assertEqual(load_passage(str(path)), normalized)


class EndToEndTests(unittest.TestCase):
    def test_product_json_generates_matching_words_and_current_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'product.json'
            path.write_text(json.dumps(product()))
            passage = load_passage(str(path))
            s3, polly = FakeS3(), FakePolly()
            result = prepare(passage, tmp, polly, s3=s3, bucket='bucket')
            manifest = result['manifest']
            paragraphs = {p['id']: p['text'] for p in manifest['paragraphs']}
            for token in manifest['tokens']:
                self.assertEqual(paragraphs[token['paragraphId']][token['start']:token['end']], token['text'])
            self.assertEqual(len(manifest['timings']), len(manifest['tokens']))
            self.assertEqual(manifest['source']['provider'], 'readworks')
            pointer = json.loads(s3.objects[f'generated/{UUID}/current.json']['body'])
            self.assertEqual(pointer['manifestUrl'], result['manifestUrl'])
            self.assertIn(f"{result['manifestUrl'][1:]}", s3.objects)

    def test_cache_hit_also_restores_current_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            passage = convert(product())
            s3, polly = FakeS3(), FakePolly()
            first = prepare(passage, tmp, polly, s3=s3, bucket='bucket')
            del s3.objects[f'generated/{UUID}/current.json']
            calls = len(polly.calls)
            second = prepare(passage, tmp, polly, s3=s3, bucket='bucket')
            self.assertTrue(second['cached'])
            self.assertEqual(len(polly.calls), calls)
            pointer = json.loads(s3.objects[f'generated/{UUID}/current.json']['body'])
            self.assertEqual(pointer['manifestUrl'], first['manifestUrl'])


if __name__ == '__main__':
    unittest.main()
