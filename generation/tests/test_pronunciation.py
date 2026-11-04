"""Tests for the optional Bedrock pronunciation layer.

All AWS calls are mocked. Anything that still needs REAL credentials to confirm is
called out in README_PRONUNCIATION.md and summarized at the bottom of this file.

The SSML speech-mark fakes below emulate Amazon Polly's DOCUMENTED behavior:
word marks are substrings of the SSML input, with byte offsets INTO THE SSML
string (verified from the AWS "Speech marks with SSML example" docs). Because the
docs do not pin down what Polly emits for text inside <sub alias>, the offset tests
run under BOTH plausible behaviors (the mark's value is the spoken alias, or the
original) to prove the mapping never depends on that detail.
"""
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

import pronunciation
from pronunciation import (detect_pronunciations, validate_suggestions, build_ssml,
                           build_segments, make_detector)
from pipeline import (map_ssml_marks, map_marks, generate, UnsupportedSSMLMapping,
                      word_clip_id, utf16_length)


# --------------------------------------------------------------------------- #
# Fake Bedrock client (Converse API)
# --------------------------------------------------------------------------- #
class FakeBedrock:
    def __init__(self, text_reply=None, error=None):
        self._text_reply = text_reply
        self._error = error
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return {'output': {'message': {'content': [{'text': self._text_reply}]}}}


def brrr_reply(text):
    start = text.index('Brrr')
    return json.dumps({'suggestions': [
        {'original': 'Brrr', 'start': start, 'end': start + 4, 'pronunciation': 'burr'}]})


# --------------------------------------------------------------------------- #
# Fake Polly that emulates DOCUMENTED SSML speech-mark offsets
# --------------------------------------------------------------------------- #
class FakeSSMLPolly:
    """Emulates Polly for both plain text and SSML input.

    For SSML, marks are produced as substrings of the SSML with byte offsets into
    the SSML string. `sub_value` controls what the alias span's mark `value` is, so
    tests can prove the mapper ignores it.
    """
    def __init__(self, sub_value='alias'):
        self.calls = []
        self.sub_value = sub_value  # 'alias' | 'original'

    def _marks_plain(self, text):
        marks = []
        for match in re.finditer(r'\w+', text):
            marks.append({'type': 'word',
                          'start': len(text[:match.start()].encode('utf-8')),
                          'end': len(text[:match.end()].encode('utf-8')),
                          'value': match.group(),
                          'time': 0})
        # assign increasing, in-range times
        for i, mark in enumerate(marks):
            mark['time'] = int(i * 900 / max(1, len(marks)))
        return marks

    def _marks_ssml(self, ssml):
        """Emulate Polly SSML word marks. Real Polly emits a mark per SPOKEN word
        (it does not emit marks for escaped punctuation entities like &quot;). We
        walk the SSML char-by-char: inside a <sub> we emit one mark for the alias
        text; outside, we emit a mark per word of the *unescaped* visible text,
        with byte offsets into the SSML string (as the docs demonstrate)."""
        marks = []
        i = 0
        raw = ssml
        while i < len(raw):
            if raw.startswith('<sub ', i):
                alias = re.search(r'alias="([^"]*)"', raw[i:]).group(1)
                open_end = raw.index('>', i) + 1
                close = raw.index('</sub>', open_end)
                inner = raw[open_end:close]
                value = alias if self.sub_value == 'alias' else inner
                marks.append({'type': 'word',
                              'start': len(raw[:open_end].encode('utf-8')),
                              'end': len(raw[:open_end + len(inner)].encode('utf-8')),
                              'value': value, 'time': 0})
                i = close + len('</sub>')
            elif raw.startswith('<speak>', i):
                i += len('<speak>')
            elif raw.startswith('</speak>', i):
                i += len('</speak>')
            elif raw[i] == '<':
                i = raw.index('>', i) + 1
            else:
                # Visible run until next tag. Unescape entities so word detection
                # matches real speech, but keep byte offsets into the SSML by
                # advancing an entity as a single non-word unit.
                nxt = raw.find('<', i)
                if nxt == -1:
                    nxt = len(raw)
                j = i
                while j < nxt:
                    if raw[j] == '&':  # entity such as &quot; / &amp; -> punctuation, no word mark
                        semi = raw.index(';', j) + 1
                        j = semi
                        continue
                    if raw[j].isalnum():
                        word_start = j
                        while j < nxt and raw[j] != '&' and raw[j].isalnum():
                            j += 1
                        marks.append({'type': 'word',
                                      'start': len(raw[:word_start].encode('utf-8')),
                                      'end': len(raw[:j].encode('utf-8')),
                                      'value': raw[word_start:j], 'time': 0})
                    else:
                        j += 1
                i = nxt
        for k, mark in enumerate(marks):
            mark['time'] = int(k * 900 / max(1, len(marks)))
        return marks

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs['OutputFormat'] == 'pcm':
            return {'AudioStream': io.BytesIO(b'\x00\x00' * 16000), 'RequestCharacters': len(kwargs['Text'])}
        if kwargs['OutputFormat'] == 'mp3':
            return {'AudioStream': io.BytesIO(b'ID3clip'), 'RequestCharacters': len(kwargs['Text'])}
        # json speech marks
        if kwargs.get('TextType') == 'ssml':
            marks = self._marks_ssml(kwargs['Text'])
        else:
            marks = self._marks_plain(kwargs['Text'])
        payload = '\n'.join(json.dumps(m) for m in marks).encode()
        return {'AudioStream': io.BytesIO(payload), 'RequestCharacters': len(kwargs['Text'])}


def passage(text):
    return {'id': 'test', 'revision': 1, 'title': 'T', 'language': 'en-US',
            'paragraphs': [{'id': 'p1', 'text': text}]}


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
class DetectionTests(unittest.TestCase):
    def test_disabled_returns_empty_without_calling_bedrock(self):
        client = FakeBedrock(text_reply=brrr_reply('Brrr!'))
        self.assertEqual(detect_pronunciations('Brrr!', client, enabled=False), [])
        self.assertEqual(client.calls, [])

    def test_none_client_returns_empty(self):
        self.assertEqual(detect_pronunciations('Brrr!', None, enabled=True), [])

    def test_valid_reply_parsed(self):
        client = FakeBedrock(text_reply=brrr_reply('"Brrr!" she said.'))
        out = detect_pronunciations('"Brrr!" she said.', client, enabled=True)
        self.assertEqual(out[0]['original'], 'Brrr')
        self.assertEqual(out[0]['pronunciation'], 'burr')

    def test_reply_with_prose_and_fence(self):
        reply = 'Sure!\n```json\n' + brrr_reply('Brrr!') + '\n```'
        client = FakeBedrock(text_reply=reply)
        out = detect_pronunciations('Brrr!', client, enabled=True)
        self.assertEqual(out[0]['original'], 'Brrr')

    def test_malformed_json_returns_empty(self):
        client = FakeBedrock(text_reply='not json at all')
        self.assertEqual(detect_pronunciations('Brrr!', client, enabled=True), [])

    def test_aws_error_returns_empty(self):
        client = FakeBedrock(error=RuntimeError('ThrottlingException'))
        self.assertEqual(detect_pronunciations('Brrr!', client, enabled=True), [])

    def test_make_detector_disabled_is_none(self):
        self.assertIsNone(make_detector(FakeBedrock(), enabled=False))
        self.assertIsNone(make_detector(None, enabled=True))


# --------------------------------------------------------------------------- #
# Validation (untrusted model output)
# --------------------------------------------------------------------------- #
class ValidationTests(unittest.TestCase):
    def test_offset_must_match_text(self):
        text = '"Brrr!" she said.'
        good = [{'original': 'Brrr', 'start': text.index('Brrr'), 'end': text.index('Brrr') + 4, 'pronunciation': 'burr'}]
        self.assertEqual(len(validate_suggestions(text, good)), 1)
        # A word the model claims is present but that does not occur near the
        # reported offset (or anywhere) -> dropped, no false substitution.
        bad = [{'original': 'Zzz', 'start': 0, 'end': 3, 'pronunciation': 'zee'}]
        self.assertEqual(validate_suggestions(text, bad), [])

    def test_rejects_injection_pronunciations(self):
        text = 'Brrr!'
        for bad_pron in ['<break/>', 'a"b', 'burr<sub', 'x</speak>', '', '  ']:
            s = [{'original': 'Brrr', 'start': 0, 'end': 4, 'pronunciation': bad_pron}]
            self.assertEqual(validate_suggestions(text, s), [], bad_pron)

    def test_rejects_multiword_and_out_of_range(self):
        text = 'Brrr brrr!'
        multi = [{'original': 'Brrr brrr', 'start': 0, 'end': 9, 'pronunciation': 'burr'}]
        self.assertEqual(validate_suggestions(text, multi), [])
        # Garbage offsets for a word that is NOT present near them stay rejected
        # (offset recovery only snaps to a real, nearby, unambiguous occurrence).
        oob = [{'original': 'Zzz', 'start': 0, 'end': 999, 'pronunciation': 'zee'}]
        self.assertEqual(validate_suggestions(text, oob), [])

    def test_drops_overlaps_keeping_earliest(self):
        text = 'Brrrr!'
        s = [{'original': 'Brrrr', 'start': 0, 'end': 5, 'pronunciation': 'burr'},
             {'original': 'rrrr', 'start': 1, 'end': 5, 'pronunciation': 'rur'}]
        out = validate_suggestions(text, s)
        self.assertEqual([(x['start'], x['end']) for x in out], [(0, 5)])

    def test_rejects_boolean_offsets(self):
        text = 'Brrr!'
        s = [{'original': 'Brrr', 'start': True, 'end': 4, 'pronunciation': 'burr'}]
        self.assertEqual(validate_suggestions(text, s), [])


# --------------------------------------------------------------------------- #
# Offset recovery: snap slightly-wrong model offsets to the real word span
# --------------------------------------------------------------------------- #
class OffsetRecoveryTests(unittest.TestCase):
    def test_curly_quote_offset_off_by_one_is_recovered(self):
        # The real demo case: a leading curly quote makes the model report
        # start=0 while "Brrr" is actually at index 1.
        text = '\u201cBrrr! It is chilly today,\u201d she said.'
        self.assertEqual(text[1:5], 'Brrr')  # sanity
        s = [{'original': 'Brrr', 'start': 0, 'end': 4, 'pronunciation': 'burr'}]
        out = validate_suggestions(text, s)
        self.assertEqual(out, [{'start': 1, 'end': 5, 'original': 'Brrr', 'pronunciation': 'burr'}])

    def test_offset_off_by_a_few_is_recovered(self):
        text = 'The dog went Woof! loudly.'
        real = text.index('Woof')  # 13
        s = [{'original': 'Woof', 'start': real + 3, 'end': real + 7, 'pronunciation': 'wuff'}]
        out = validate_suggestions(text, s)
        self.assertEqual([(o['start'], o['end']) for o in out], [(real, real + 4)])

    def test_exact_offsets_still_accepted_unchanged(self):
        text = 'Say Vrooom now.'  # unique onomatopoeia, exact offsets
        i = text.index('Vrooom')
        s = [{'original': 'Vrooom', 'start': i, 'end': i + 6, 'pronunciation': 'vroom'}]
        out = validate_suggestions(text, s)
        self.assertEqual(out, [{'start': i, 'end': i + 6, 'original': 'Vrooom', 'pronunciation': 'vroom'}])

    def test_ambiguous_match_in_window_is_rejected(self):
        # Two occurrences of the word within the search window -> cannot pick one.
        text = 'Brrr Brrr!'  # indices 0 and 5, both within the +/-8 window of 0
        s = [{'original': 'Brrr', 'start': 2, 'end': 6, 'pronunciation': 'burr'}]
        self.assertEqual(validate_suggestions(text, s), [])

    def test_match_outside_window_is_rejected(self):
        # The only occurrence is far from the reported offset -> not recovered.
        text = 'x' * 40 + 'Brrr!'  # "Brrr" at index 40, reported start 0
        s = [{'original': 'Brrr', 'start': 0, 'end': 4, 'pronunciation': 'burr'}]
        self.assertEqual(validate_suggestions(text, s), [])

    def test_distant_second_occurrence_does_not_make_it_ambiguous(self):
        # One occurrence near the offset, another far away -> still recovered,
        # because only the near one is inside the window.
        text = 'Brrr! ' + 'y' * 40 + ' Brrr'
        s = [{'original': 'Brrr', 'start': 0, 'end': 4, 'pronunciation': 'burr'}]
        out = validate_suggestions(text, s)
        self.assertEqual([(o['start'], o['end']) for o in out], [(0, 4)])


# --------------------------------------------------------------------------- #
# No-op guard: ignore suggestions equal to the original word (case-insensitive)
# --------------------------------------------------------------------------- #
class NoOpGuardTests(unittest.TestCase):
    def _suggest(self, text, original, pronunciation):
        start = text.index(original)
        return [{'original': original, 'start': start, 'end': start + len(original),
                 'pronunciation': pronunciation}]

    def test_vroom_to_vroom_is_ignored(self):
        text = '"Vroom!" went the car.'
        out = validate_suggestions(text, self._suggest(text, 'Vroom', 'vroom'))
        self.assertEqual(out, [])

    def test_identical_case_is_ignored(self):
        text = 'Vroom!'
        self.assertEqual(validate_suggestions(text, self._suggest(text, 'Vroom', 'Vroom')), [])

    def test_brrr_to_burr_is_preserved(self):
        text = '"Brrr!" she said.'
        out = validate_suggestions(text, self._suggest(text, 'Brrr', 'burr'))
        self.assertEqual([s['pronunciation'] for s in out], ['burr'])

    def test_achoo_to_ahchoo_is_preserved(self):
        text = '"Achoo!" she sneezed.'
        out = validate_suggestions(text, self._suggest(text, 'Achoo', 'ah-choo'))
        self.assertEqual([s['pronunciation'] for s in out], ['ah-choo'])

    def test_ignored_suggestion_uses_plain_polly_path_no_ssml(self):
        # When the only detected suggestion is a no-op, generate() must synthesize
        # via the normal text path -- no SSML request at all -- and record no
        # pronunciation on the manifest.
        item = passage('"Vroom!" went the car.')
        # detect is called once per narrated chunk (which may include the title);
        # only suggest when the word is actually present, like real detection.
        detect = lambda t: ([{'original': 'Vroom', 'start': t.index('Vroom'),
                              'end': t.index('Vroom') + 5, 'pronunciation': 'vroom'}]
                             if 'Vroom' in t else [])
        with tempfile.TemporaryDirectory() as tmp:
            polly = FakeSSMLPolly()
            manifest, _, _ = generate(item, tmp, polly, detect=detect, pronunciation_enabled=True)
            # No SSML was ever requested.
            self.assertTrue(all(call.get('TextType') != 'ssml' for call in polly.calls))
            self.assertTrue(any(call.get('TextType') == 'text' for call in polly.calls))
            # No pronunciation recorded; "Vroom" present as a normal display token.
            self.assertNotIn('pronunciation', manifest['generation'])
            self.assertIn('Vroom', [t['text'] for t in manifest['tokens']])
            # Isolated word clip uses the plain (non-alias) id.
            vroom = next(t for t in manifest['tokens'] if t['text'] == 'Vroom')
            self.assertEqual(manifest['wordAudio']['clips'][vroom['id']],
                             word_clip_id('Vroom', 'Stephen', 'en-US'))

    def test_useful_correction_still_uses_ssml(self):
        # Contrast: a real correction DOES take the SSML path.
        item = passage('"Achoo!" she sneezed.')
        detect = lambda t: ([{'original': 'Achoo', 'start': t.index('Achoo'),
                              'end': t.index('Achoo') + 5, 'pronunciation': 'ah-choo'}]
                             if 'Achoo' in t else [])
        with tempfile.TemporaryDirectory() as tmp:
            polly = FakeSSMLPolly()
            manifest, _, _ = generate(item, tmp, polly, detect=detect, pronunciation_enabled=True)
            self.assertTrue(any(call.get('TextType') == 'ssml' for call in polly.calls))
            self.assertEqual(manifest['generation']['pronunciation'],
                             [{'original': 'Achoo', 'pronunciation': 'ah-choo'}])


# --------------------------------------------------------------------------- #
# SSML generation
# --------------------------------------------------------------------------- #
class SSMLTests(unittest.TestCase):
    def test_sub_alias_and_escaping(self):
        text = 'Say "Brrr" & <go>.'
        start = text.index('Brrr')
        s = [{'original': 'Brrr', 'start': start, 'end': start + 4, 'pronunciation': 'burr'}]
        ssml = build_ssml(text, s)
        self.assertTrue(ssml.startswith('<speak>') and ssml.endswith('</speak>'))
        self.assertIn('<sub alias="burr">Brrr</sub>', ssml)
        # surrounding text is XML-escaped and preserved
        self.assertIn('&amp;', ssml)
        self.assertIn('&lt;go&gt;', ssml)
        self.assertIn('&quot;', ssml)

    def test_no_suggestions_wraps_plain(self):
        self.assertEqual(build_ssml('Hello world.', []), '<speak>Hello world.</speak>')

    def test_segments_reproduce_text(self):
        text = 'A Brrr B'
        s = [{'original': 'Brrr', 'start': 2, 'end': 6, 'pronunciation': 'burr'}]
        segments = build_segments(text, s)
        self.assertEqual(''.join(seg['text'] for seg in segments), text)


# --------------------------------------------------------------------------- #
# SSML speech-mark offset mapping (the risky part, verified both ways)
# --------------------------------------------------------------------------- #
class SSMLMarkMappingTests(unittest.TestCase):
    def _run(self, sub_value):
        text = '"Brrr!" she said.'
        start = text.index('Brrr')
        suggestions = [{'original': 'Brrr', 'start': start, 'end': start + 4, 'pronunciation': 'burr'}]
        segments = build_segments(text, suggestions)
        ssml = build_ssml(text, suggestions)
        polly = FakeSSMLPolly(sub_value=sub_value)
        marks = json.loads('[' + ','.join(
            json.dumps(m) for m in polly._marks_ssml(ssml)) + ']')
        para = {'id': 'p1', 'text': text}
        tokens, timings = map_ssml_marks(text, marks, segments, para, 0, 0.0, 2000.0, 0)
        return text, tokens, timings

    def test_mapping_is_identical_regardless_of_sub_value(self):
        text_a, tokens_a, timings_a = self._run('alias')
        text_b, tokens_b, timings_b = self._run('original')
        self.assertEqual(tokens_a, tokens_b)
        self.assertEqual(timings_a, timings_b)

    def test_brrr_token_points_at_display_text(self):
        text, tokens, timings = self._run('alias')
        brrr = next(t for t in tokens if t['text'] == 'Brrr')
        # offsets index the DISPLAY text, so slicing reproduces "Brrr"
        self.assertEqual(text[brrr['start']:brrr['end']], 'Brrr')
        self.assertEqual(utf16_length(text[:text.index('Brrr')]), brrr['start'])
        # the words around it are present and correctly spelled
        self.assertEqual([t['text'] for t in tokens], ['Brrr', 'she', 'said'])
        # timings are ordered
        times = [t['startMs'] for t in timings]
        self.assertEqual(times, sorted(times))

    def test_fallback_when_substitution_is_silent(self):
        # A <sub> that yields no spoken word must raise so the pipeline falls back.
        text = 'Brrr!'
        suggestions = [{'original': 'Brrr', 'start': 0, 'end': 4, 'pronunciation': 'burr'}]
        segments = build_segments(text, suggestions)
        para = {'id': 'p1', 'text': text}
        # no marks at all inside the sub span
        with self.assertRaises(UnsupportedSSMLMapping):
            map_ssml_marks(text, [], segments, para, 0, 0.0, 2000.0, 0)


# --------------------------------------------------------------------------- #
# End-to-end: highlighting / replay compatibility
# --------------------------------------------------------------------------- #
class EndToEndTests(unittest.TestCase):
    def test_generate_with_pronunciation_preserves_display_and_timings(self):
        item = passage('"Brrr!" said the child. The wind blew.')
        detect = lambda text: ([{'original': 'Brrr', 'start': text.index('Brrr'),
                                  'end': text.index('Brrr') + 4, 'pronunciation': 'burr'}]
                                if 'Brrr' in text else [])
        with tempfile.TemporaryDirectory() as tmp:
            polly = FakeSSMLPolly(sub_value='alias')
            manifest, directory, cached = generate(item, tmp, polly, detect=detect, pronunciation_enabled=True)
            self.assertFalse(cached)
            # Display text untouched.
            self.assertEqual(manifest['paragraphs'][0]['text'], item['paragraphs'][0]['text'])
            # Every token offset indexes ITS OWN paragraph's text and slices back to
            # its word. Resolve by paragraphId so this holds whether or not the
            # pipeline also narrates the title paragraph (a separate feature).
            para_text = {p['id']: p['text'] for p in manifest['paragraphs']}
            if manifest.get('narrationTitle'):
                para_text[manifest['narrationTitle']['id']] = manifest['narrationTitle']['text']
            for token in manifest['tokens']:
                # start/end are UTF-16 units; for this ASCII text they equal indices
                source = para_text[token['paragraphId']]
                self.assertEqual(source[token['start']:token['end']], token['text'])
            # "Brrr" survived as a display token (not "burr").
            self.assertIn('Brrr', [t['text'] for t in manifest['tokens']])
            self.assertNotIn('burr', [t['text'] for t in manifest['tokens']])
            # tokens and timings line up 1:1 and are time-ordered (needed for
            # highlighting, Replay Sentence, and follow-along).
            self.assertEqual(len(manifest['tokens']), len(manifest['timings']))
            times = [t['startMs'] for t in manifest['timings']]
            self.assertEqual(times, sorted(times))
            # Isolated word clip for Brrr was synthesized via SSML <sub> and has the
            # alias-aware id, distinct from a plain "Brrr" clip.
            brrr_token = next(t for t in manifest['tokens'] if t['text'] == 'Brrr')
            clip_id = manifest['wordAudio']['clips'][brrr_token['id']]
            self.assertEqual(clip_id, word_clip_id('Brrr', 'Stephen', 'en-US', 'burr'))
            self.assertNotEqual(clip_id, word_clip_id('Brrr', 'Stephen', 'en-US'))
            # The pronunciation that was applied is recorded on the manifest.
            self.assertEqual(manifest['generation']['pronunciation'],
                             [{'original': 'Brrr', 'pronunciation': 'burr'}])

    def test_feature_off_matches_plain_pipeline(self):
        item = passage('"Brrr!" said the child.')
        with tempfile.TemporaryDirectory() as tmp:
            off, _, _ = generate(item, tmp, FakeSSMLPolly(), pronunciation_enabled=False)
        with tempfile.TemporaryDirectory() as tmp:
            # detect supplied but feature disabled -> no Bedrock use, plain output
            also_off, _, _ = generate(item, tmp, FakeSSMLPolly(),
                                      detect=lambda t: [{'original': 'Brrr', 'start': 1, 'end': 5, 'pronunciation': 'burr'}],
                                      pronunciation_enabled=False)
        self.assertEqual(off['tokens'], also_off['tokens'])
        self.assertEqual(off['timings'], also_off['timings'])
        self.assertNotIn('pronunciation', off['generation'])
        # "Brrr" present as display token; no alias clip id used.
        brrr = next(t for t in off['tokens'] if t['text'] == 'Brrr')
        self.assertEqual(off['wordAudio']['clips'][brrr['id']], word_clip_id('Brrr', 'Stephen', 'en-US'))

    def test_mapping_failure_falls_back_to_plain_text(self):
        # Force map_ssml_marks to fail by handing generate a detect result that,
        # once validated, points at a span whose <sub> produces a silent result.
        item = passage('Brrr!')

        class SilentSubPolly(FakeSSMLPolly):
            def _marks_ssml(self, ssml):
                # Emulate a <sub> that Polly spoke but reported NO word marks for;
                # plain text still yields marks on fallback.
                return []

        detect = lambda text: [{'original': 'Brrr', 'start': 0, 'end': 4, 'pronunciation': 'burr'}]
        with tempfile.TemporaryDirectory() as tmp:
            manifest, _, _ = generate(item, tmp, SilentSubPolly(), detect=detect, pronunciation_enabled=True)
            # Fell back to plain text: "Brrr" still a token, no pronunciation recorded.
            self.assertIn('Brrr', [t['text'] for t in manifest['tokens']])
            self.assertNotIn('pronunciation', manifest['generation'])


# Items that STILL require real AWS credentials to verify (cannot be mocked):
#  * The exact speech-mark `value`/offsets Polly emits inside <sub alias> with the
#    Stephen neural voice. The mapper is written to not depend on this, and both
#    plausible behaviors are covered above, but a real Polly SSML call should
#    confirm the assumption end to end.
#  * That the Bedrock model (Converse API) returns well-formed, correctly-offset
#    suggestions for real passages; only the parsing/validation is mocked here.
#  * Audible quality of the corrected pronunciation ("burr") in the neural voice.
if __name__ == '__main__':
    unittest.main()
