import unittest
from human_alignment import align
from test_pipeline import passage


def transcript(words):
    items=[]
    for index, word in enumerate(words):
        text, confidence = word if isinstance(word, tuple) else (word,1)
        items.append({'type':'pronunciation','start_time':str(index),'end_time':str(index+.5),
                      'alternatives':[{'content':text,'confidence':str(confidence)}]})
    return {'results':{'items':items}}


class HumanAlignmentTests(unittest.TestCase):
    def run_align(self,text,words):
        return align(passage(text),transcript(words),'abc123','https://example.com/audio.mp3')

    def test_spoken_title_is_not_assigned_to_passage_words(self):
        manifest,report=self.run_align('Maya watered the garden.', ['A','Garden','Story','by','Jill','Maya','watered','the','garden'])
        self.assertEqual(manifest['timings'][0]['startMs'],5000)
        self.assertEqual(report['alignedWords'],4)
        self.assertEqual(manifest['audio']['engine'],'human')
        self.assertTrue(manifest['audio']['url'].startswith('/generated/'))
        self.assertTrue(manifest['audio']['url'].endswith('/audio.mp3'))
        self.assertEqual(manifest['audio']['sourceUrl'],'https://example.com/audio.mp3')
        self.assertEqual(manifest['audio']['sha256'],'abc123')

    def test_unrecognized_and_low_confidence_words_get_no_invented_timings(self):
        manifest,report=self.run_align('Doug Widener loves the park.', ['Doug',('Winer',.5),'loves',('the',.4),'park'])
        self.assertEqual([t['text'] for t in manifest['tokens']],['Doug','loves','park'])
        self.assertEqual([t['text'] for t in report['uncertainWords']],['Widener','the'])
        self.assertTrue(report['needsReview'])
        self.assertEqual(manifest['paragraphs'][0]['text'],'Doug Widener loves the park.')

    def test_numerals_match_without_interpolating_word_boundaries(self):
        manifest,report=self.run_align('Over six million and one hundred people.', ['Over','6','million','and','100','people'])
        self.assertEqual(report['alignedWords'],5)
        times={word['text']:manifest['timings'][i] for i,word in enumerate(manifest['tokens'])}
        self.assertEqual(times['six']['startMs'],1000)
        self.assertNotIn('one',times)
        self.assertNotIn('hundred',times)
        self.assertEqual([word['reason'] for word in report['uncertainWords']], ['phrase_only','phrase_only'])
        self.assertEqual(len(report['phraseLevelTokenIds']),2)

    def test_repeated_words_and_unicode_keep_display_offsets(self):
        manifest,report=self.run_align('😀 café café.', ['café','café'])
        self.assertEqual([t['start'] for t in manifest['tokens']],[3,8])
        self.assertEqual([t['startMs'] for t in manifest['timings']],[0,1000])
        self.assertEqual(report['coverage'],1)

    def test_changed_text_reuses_input_transcript_but_changes_alignment_identity(self):
        first,_=self.run_align('Maya walked.', ['Maya','walked'])
        second,_=self.run_align('Maya walked slowly.', ['Maya','walked'])
        self.assertNotEqual(first['assetVersion'],second['assetVersion'])

    def test_empty_match_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'No words'):
            self.run_align('Garden.', ['Music'])
