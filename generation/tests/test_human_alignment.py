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


class QaVerifiedAlignmentTests(unittest.TestCase):
    def align_qa(self, text, words):
        return align(passage(text), transcript(words), 'abc123', 'https://example.com/audio.mp3', qa_verified=True)

    def test_qa_exact_matches_keep_real_times_even_with_low_asr_confidence(self):
        manifest, report = self.align_qa('The park is quiet.', [('The', .2), 'park', 'is', 'quiet'])
        self.assertEqual(report['coverage'], 1)
        self.assertEqual(manifest['timings'][0]['startMs'], 0)
        self.assertEqual(manifest['timings'][0]['endMs'], 500)
        self.assertEqual(manifest['timings'][0]['confidence'], .2)
        self.assertEqual(report['acceptedLowConfidenceTokenIds'], ['w0'])
        self.assertFalse(report['needsReview'])

    def test_qa_recovers_name_recognition_between_exact_context_anchors(self):
        manifest, report = self.align_qa('Meet our friend Doug Widener in the park today.',
                                         ['Meet', 'our', 'friend', 'Doug', ('Winer', .5), 'in', 'the', 'park', 'today'])
        name = next(t for t in manifest['tokens'] if t['text'] == 'Widener')
        timing = next(t for t in manifest['timings'] if t['tokenId'] == name['id'])
        self.assertEqual(timing['startMs'], 4000)
        self.assertEqual(timing['endMs'], 4500)
        self.assertEqual(timing['matchMethod'], 'qa-context')
        self.assertEqual(report['contextRecoveredTokenIds'], [name['id']])
        self.assertEqual(report['coverage'], 1)

    def test_qa_does_not_fill_missing_words_or_split_numeric_phrase_times(self):
        manifest, report = self.align_qa('Over one hundred people love the big park.',
                                         ['Over', '100', 'people', 'love', 'the', 'park'])
        words = [t['text'] for t in manifest['tokens']]
        self.assertNotIn('one', words)
        self.assertNotIn('hundred', words)
        self.assertNotIn('big', words)
        self.assertEqual(report['phraseLevelTokenIds'], ['w1', 'w2'])
        self.assertTrue(report['needsReview'])

    def test_qa_does_not_reassign_spoken_introduction_or_unanchored_substitution(self):
        manifest, report = self.align_qa('Maya watered the garden.', ['A', 'Garden', 'Story', 'by', 'Jill', 'Maya', 'watered', 'the', 'garden'])
        self.assertEqual(manifest['timings'][0]['startMs'], 5000)
        manifest, report = self.align_qa('Doug Widener loves the park.', ['Doug', 'Winer', 'loves', 'the', 'park'])
        self.assertNotIn('Widener', [t['text'] for t in manifest['tokens']])

    def test_mode_changes_asset_identity_but_never_source_text(self):
        data = passage('The park is quiet.')
        speech = transcript(['The', 'park', 'is', 'quiet'])
        conservative, _ = align(data, speech, 'abc123', 'https://example.com/a.mp3')
        verified, _ = align(data, speech, 'abc123', 'https://example.com/a.mp3', qa_verified=True)
        self.assertNotEqual(conservative['assetVersion'], verified['assetVersion'])
        self.assertEqual(verified['paragraphs'], data['paragraphs'])

    def test_grouped_numeral_is_one_display_token_with_utf16_offsets(self):
        manifest, report = self.align_qa('😀 1,000 people.', ['one', 'thousand', 'people'])
        self.assertEqual(report['coverage'], 1)
        self.assertEqual(manifest['tokens'][0]['text'], '1,000')
        self.assertEqual(manifest['tokens'][0]['start'], 3)
        self.assertEqual(manifest['tokens'][0]['end'], 8)
        self.assertEqual(manifest['timings'][0]['startMs'], 0)
        self.assertEqual(manifest['timings'][0]['endMs'], 1500)

    def test_invalid_recognition_confidence_and_negative_times_are_rejected(self):
        for confidence in ['NaN', '-.1', '1.1']:
            with self.assertRaisesRegex(ValueError, 'confidence'):
                self.align_qa('Hello.', [('Hello', confidence)])
        speech = transcript(['Hello'])
        speech['results']['items'][0]['start_time'] = '-1'
        with self.assertRaisesRegex(ValueError, 'timestamps'):
            align(passage('Hello.'), speech, 'hash', 'https://example.com/a.mp3', qa_verified=True)

    def test_revised_transcript_boundaries_get_a_new_immutable_asset_version(self):
        data = passage('The park is quiet.')
        original = transcript(['The', 'park', 'is', 'quiet'])
        first, _ = align(data, original, 'same-recording', 'https://example.com/a.mp3', qa_verified=True)
        revised = transcript(['The', 'park', 'is', 'quiet'])
        revised['results']['items'][0]['end_time'] = '0.6'
        second, _ = align(data, revised, 'same-recording', 'https://example.com/a.mp3', qa_verified=True)
        self.assertNotEqual(first['assetVersion'], second['assetVersion'])
        self.assertNotEqual(first['alignment']['transcriptHash'], second['alignment']['transcriptHash'])

    def test_grouped_number_support_does_not_split_ordinals_or_include_sentence_punctuation(self):
        manifest, report = self.align_qa('On the 3rd day, 100 people came.', ['On', 'the', '3rd', 'day', '100', 'people', 'came'])
        self.assertEqual(report['coverage'], 1)
        self.assertEqual([t['text'] for t in manifest['tokens']], ['On', 'the', '3rd', 'day', '100', 'people', 'came'])

    def test_human_recording_never_inherits_synthetic_word_clips_from_input(self):
        data = {**passage('The park is quiet.'), 'wordAudio': {'baseUrl': '/generated/words/Stephen/', 'clips': {'w0': 'a'*20}}}
        manifest, _ = align(data, transcript(['The', 'park', 'is', 'quiet']), 'hash', 'https://example.com/a.mp3', qa_verified=True)
        self.assertNotIn('wordAudio', manifest)
