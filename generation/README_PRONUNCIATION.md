# AI pronunciation layer (prototype)

Optional Amazon Bedrock step that improves how Amazon Polly says onomatopoeia and
sound-effect words (for example "Brrr!" -> spoken as "burr"), **without changing
the displayed passage text** or the reader's word highlighting / Replay Sentence /
follow-along features.

Disabled by default. When off, generation is byte-for-byte identical to before.

## How it works

1. Per narration chunk, `pronunciation.detect_pronunciations()` asks Bedrock
   (Converse API) to find onomatopoeia and return
   `{original, start, end, pronunciation}` suggestions.
2. `pronunciation.validate_suggestions()` discards anything unsafe: offsets that
   don't match the display text, multi-word spans, overlaps, out-of-range spans,
   or pronunciations that aren't plain alphabetic words (blocks SSML injection).
3. Validated spans become `<sub alias="burr">Brrr</sub>` SSML
   (`pronunciation.build_ssml()`); everything else is XML-escaped and unchanged.
4. Polly synthesizes the SSML. `pipeline.map_ssml_marks()` maps Polly's word
   speech marks back to **display-text** tokens/timings. Inside a `<sub>` it uses
   the span position we control and takes only the timestamp — it never trusts the
   alias text or Polly's in-`<sub>` offsets.
5. Isolated word clips for substituted words are synthesized from the same `<sub>`
   SSML, so "hear just this word" matches the narration.

If detection fails, returns nothing, or the marks can't be mapped safely, the
chunk silently falls back to today's plain-text path. Narration is never lost.

## Enabling it

CLI:

```sh
python3 generation/generate.py <passage> --pronunciation [--bedrock-model <id>]
```

Lambda (`handler.py`): set `PRONUNCIATION_ENABLED=true` (and optionally
`BEDROCK_MODEL_ID`). IAM must allow `bedrock:InvokeModel` for the chosen model
(including its inference-profile ARN), in addition to the existing
`polly:SynthesizeSpeech`.

Default model id: `us.anthropic.claude-haiku-4-5-20251001-v1:0` — a cross-region
inference profile (the `us.` prefix), verified invokable in `us-west-2`. The
newer Claude models require an inference profile; a bare on-demand model id is
rejected with "on-demand throughput isn't supported". List options with
`aws bedrock list-inference-profiles --region <region>`. Override with
`--bedrock-model` / `BEDROCK_MODEL_ID`.

## Tests

`generation/tests/test_pronunciation.py` — all AWS calls mocked:
- Bedrock detection: parsing, prose/fence tolerance, malformed JSON, AWS errors,
  disabled/none-client paths.
- Suggestion validation: offset mismatch, injection pronunciations, multi-word /
  out-of-range / overlapping spans, boolean-offset rejection.
- SSML generation: `<sub alias>`, XML escaping, text preservation.
- **SSML speech-mark offset mapping** (the risky part): the fake Polly emulates
  the AWS-documented behavior (marks are SSML substrings with byte offsets into
  the SSML). The mapping is verified to be identical whether Polly reports the
  spoken alias OR the original inside `<sub>`, and the "Brrr" token is verified to
  index the display text correctly even with surrounding quotes.
- End-to-end `generate()`: display text preserved, tokens index display text,
  "Brrr" survives (not "burr"), timings ordered 1:1, alias-aware word-clip id,
  feature-off equals the plain pipeline, and mapping-failure fallback.

Run:

```sh
cd generation && python3 -m unittest tests.test_pronunciation
```

## Still requires REAL Bedrock / Polly credentials to verify

These cannot be settled with mocks and should be confirmed in the sandbox before
relying on the feature:

1. **Exact Polly `<sub>` speech-mark behavior** with the Stephen neural voice —
   what `value`/offsets Polly emits for the spoken alias. The mapper is written to
   not depend on this and both plausible behaviors are tested, but a real SSML
   `synthesize-speech` call (OutputFormat=json, SpeechMarkTypes=[word]) should
   confirm the end-to-end mapping.
2. **Bedrock output quality** — that the model returns well-formed, correctly
   offset suggestions for real passages. Only parsing/validation is mocked.
3. **Audible quality** — that "burr" (and future substitutions) actually sound
   better than the raw word in the neural voice. Requires listening.
4. **IAM / region** — `bedrock-runtime` access and model availability in the
   deployment region.

## Known limitations (prototype)

- Single-display-word substitutions only (e.g. "Brrr" -> "burr"). Multi-word
  spans are rejected and fall back to plain text.
- A substitution that would straddle a narration chunk boundary is not applied
  (falls back for that chunk).
- Enabling the feature bypasses the shared S3 cache (keyed by the plain
  fingerprint) to avoid serving non-pronunciation audio; local re-synthesis still
  reuses matching output via the pronunciation-aware fingerprint.
