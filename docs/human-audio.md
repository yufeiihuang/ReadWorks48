# Human audio highlighting experiment

Keep the existing human recording. Amazon Transcribe batch processing supplies recognized words, confidence scores, and start/end times. Python then matches those words in sequence to the authoritative passage text. The reader uses the resulting manifest with the same atomic console as Polly audio.

This is transcription plus text matching, not acoustic forced alignment. It does not guarantee a timestamp for every displayed word. This experiment is a builder-run command, not an automated human-audio Lambda workflow.

## Caretaker sample

Open the deployed reader at:

https://d1381qenwhm2qw.cloudfront.net/?passage=park-caretaker

Source passage: https://www.readworks.org/article/Lets-Meet-a-Park-Caretaker/2b781dab-4521-40d2-a9b6-ad5f2bb0ba98

The original human recording is copied byte-for-byte into our private S3 bucket and served through the reader's CloudFront origin. It is not re-recorded, synthesized, or transcoded. This avoids depending on an external stream during playback. The recording begins with the title and author; no passage word is highlighted during that introduction. At an 0.8 recognition-confidence threshold, 347 of 360 passage words were matched. Thirteen words require review, including two words whose numeric phrase has only a shared timestamp. Those words remain readable but unhighlighted and cannot be clicked for word replay. Their audio is still played normally.

This 96.4% figure measures matching coverage, not timestamp accuracy. No manual timestamp edits or interpolated word boundaries were used. The reader clears highlights at the end of each matched human word so uncertainty gaps do not keep the previous word highlighted.

## Prepare another sample

Use a normalized passage JSON with `id`, `revision`, `title`, `language`, and `paragraphs` containing `id` and `text`. Include `source` metadata (`url`, `author`, `provider`) for attribution in the preview. The MP3 must be the exact recording served by the audio URL, and the supplied text must correspond to that recording's passage version.

```sh
source generation/.venv/bin/activate
python generation/human_audio.py YOUR_PASSAGE.json \
  --audio YOUR_RECORDING.mp3 \
  --audio-url https://YOUR_AUDIO_URL \
  --bucket YOUR_PASSAGE_ASSETS_BUCKET
```

The command saves a local `audio.mp3`, `manifest.json`, `timings.json`, and `alignment-report.json` under ignored `generation/output/human/`. Review the report before sharing. `--publish-preview` explicitly publishes an experimental manifest to `generated/PASSAGE_ID/human-ALIGNMENT_HASH/`; a partial preview is marked `needs_review`. Adding a new selectable preview currently requires registering its immutable manifest URL in the reader.

Additional options: `--profile`, `--region` (default `us-west-2`), `--confidence` (default `0.8`), `--maximum-wait` (default 600 seconds). If the job is still running at the timeout, rerun to resume the same job. Input currently supports MP3 recordings only.

The caretaker experiment used the public product JSON's `text` field to preserve body paragraphs while excluding image captions, plus its `au` reference for the corresponding recording. Both local source files are retained in ignored `generation/output/human-audio/`; no copyrighted full-text fixture is added to GitHub.

## Cost and maintenance

- Transcription is cached in private S3 by audio SHA-256, language, and transcription-config version. An unchanged recording is not transcribed again when the passage text or matching threshold changes.
- Matching output is versioned by text/revision, audio hash, confidence threshold, and aligner version. No hosted model, GPU, or new Python package is required beyond existing Boto3 and the standard library.
- Private inputs use `human-input/`; cached transcripts use `human-transcripts/`. Neither prefix is served through CloudFront. Only the approved preview recording, manifest, and report are delivered under `generated/`.
- Do not upload human-audio inputs into `passages/`. That existing event workflow still performs Polly synthesis. Automatic human-audio processing would need a separate asynchronous Transcribe workflow.
- The first transcription incurs a batch-processing charge. Actual regional pricing and recording duration determine the charge; storage and delivery are separate. Later matching-only reruns reuse that transcript.

## Lower quality recordings

Recognition confidence does not certify timestamp accuracy. Noise, quiet speech, overlapping speakers, and deviations from the text can lower matching quality. Exact matching can also miss names or ordinary words; raising the confidence threshold trades coverage for caution.

For this prototype, publish only explicitly requested review previews. Preserve plain reading and original audio through uncertain sections. Review beginning/middle/end timing and mismatches by listening. Before production, establish acceptance thresholds for coverage and long unmatched gaps using representative recordings; do not treat a high coverage percentage as proof of accurate timing. If this managed-service approach needs frequent correction, compare a dedicated forced aligner with the known transcript before scaling it.

## Verification

```sh
PYTHONPATH=generation python -m unittest discover -s generation/tests -v
node --test apps/reader/test/*.test.js
```

Tests cover spoken introductions, numeric normalization, missing words, low confidence, repeated words, Unicode display offsets, alignment identity changes, and clearing highlights through unmatched audio gaps. The sandbox experiment reused the cached transcript on reruns.

## Playback recovery

The controller preloads audio, shows a buffering state while waiting, reports download/decoding errors, and retries playback when Try again is selected. The human preview uses a new immutable manifest URL referencing the sandbox-hosted MP3. Older previews referencing an external audio URL require a page refresh to pick up this version.
