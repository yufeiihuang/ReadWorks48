# Highlighting QA-approved human recordings

Keep the original human recording and use the passage text that ReadWorks already checks manually against it. We are finding times for that known text, not generating a new voice or asking a transcriber to rewrite the passage.

Amazon Transcribe supplies word starts/ends once per distinct recording. Python matches those timestamps back to the authoritative text. With `--qa-verified`, an exact text match is retained even if ASR confidence is low, and short one-to-one recognition substitutions (such as a misspelled name) can be recovered between two exact words on each side. Source text, paragraph structure, and browser offsets are preserved. Introductions are left outside passage highlighting.

This is timestamped ASR plus known-text matching, not acoustic forced alignment. Manual QA establishes that the reading matches the text; it does not manufacture the word boundaries Transcribe occasionally omits or merges. Such words remain readable and audible without fabricated individual timestamps. `needsReview` in the internal report refers to timing coverage, not to whether the human reading needs another content QA pass. These diagnostics do not expose narration type in the reader.

## Sample result

Using the existing cached caretaker transcript:

| Mode | Words with individual timestamps | Coverage |
| --- | --- | --- |
| Original confidence-filtered experiment | 347 / 360 | 96.4% |
| QA-verified known-text matching | 356 / 360 | 98.9% |

Eight exact matches with low ASR confidence and the recognition substitution `Winer` → `Widener` were recovered. No new Transcribe request, synthetic narration, manually edited timestamp, or interpolated boundary was used. Four displayed words still have no individual timestamps: `one` and `hundred` share Transcribe's single `100` span; two other words were omitted by ASR. Their audio still plays normally.

Coverage measures how many displayed words have a timestamp, not independent acoustic timing accuracy. The source recording is the exact original MP3; SHA-256 verification prevents mismatching the cached transcript and audio bytes.

The existing public demo remains at `https://d1381qenwhm2qw.cloudfront.net/?passage=park-caretaker`. The improved QA result is a local review artifact until explicitly published; merging code does not transcribe or publish that copyrighted passage automatically.

## Automatic AWS processing

The CDK stack adds a private Step Functions Standard workflow and two small Python Lambda functions. They use the existing shared passage-assets bucket and existing Boto3 dependency. There is no public processing endpoint, GPU, custom model server, or additional account required.

1. Upload the approved MP3 to `human-input/SHA256/audio.mp3`.
2. Upload its source JSON to `human-passages/PASSAGE_ID.json` **after** the MP3 is in place.
3. The S3 notification starts the workflow. A task checks the source/audio hashes, reuses a cached transcript or starts one batch Transcribe job, then returns immediately.
4. Step Functions waits 30 seconds between checks; Lambda does not sleep or stay running while Transcribe works. The execution has a 30-minute timeout.
5. The task aligns the words, copies the original audio to an immutable generated version, writes timings/report/manifest, and updates `generated/PASSAGE_ID/current.json` only after all files succeed.
6. Reload `/?passage=PASSAGE_ID` in the reader. For a passage without a pinned manifest, the reader follows `current.json`, and CloudFront does not cache that mutable pointer. Recording files remain cached at their immutable URLs. An explicit local `?manifest=` preview still overrides the pointer.

Pinned demo passages (`demo`, `park-caretaker`) keep their reviewed manifest even after a pointer is published, so a queued run cannot change a live demo. Add `&latest=1` to preview the newest published version of a pinned passage; if its pointer is missing, slow, or broken, that preview falls back to the pin. To promote it, update the pin in `apps/reader/src/App.vue`.

The human event prefix is separate from the existing `passages/*.json` Polly trigger. **Do not upload human source JSON under `passages/`: that prefix synthesizes Polly narration.** Generated outputs, private recordings, and cached transcripts cannot trigger either source workflow. Choose one authoritative source prefix per passage ID; both pipelines publish that ID’s current pointer, so do not keep updating an old Polly source after switching the same ID to human audio.

### Queue with the helper

After this PR is merged and the CDK deployment succeeds, use authorized credentials for the **same account and shared passage-assets bucket** as the reader:

```sh
python generation/human_audio.py YOUR_PASSAGE.json \
  --audio APPROVED_RECORDING.mp3 \
  --audio-url https://ORIGINAL_RECORDING_URL \
  --bucket SHARED_PASSAGE_ASSETS_BUCKET \
  --qa-verified --queue
```

For a first AWS smoke run on an already transcribed recording, add `--cached-only`. The workflow then refuses to create a new paid Transcribe job if that recording’s cached transcript is missing. This is checked in AWS, not just by the local helper.

The helper uploads the recording and source JSON in order, then exits; processing continues in AWS with the laptop closed. Unchanged recordings already uploaded by this helper are not uploaded again. The worker still verifies their actual bytes before trusting a transcript cache.

`YOUR_PASSAGE.json` may also be a ReadWorks product JSON, its HTTPS URL, or a ReadWorks UUID. Product JSON is normalized by the existing source adapter. Audio is deliberately supplied as a local approved MP3; the worker does not follow arbitrary external media URLs. `--audio-url` records provenance only.

A source object has the normalized passage fields plus:

```json
{
  "id": "approved-demo",
  "revision": 1,
  "title": "Approved demo",
  "language": "en-US",
  "paragraphs": [{"id": "p1", "text": "The approved passage text goes here."}],
  "qaVerified": true,
  "audio": {
    "key": "human-input/FULL_AUDIO_SHA256/audio.mp3",
    "sha256": "FULL_AUDIO_SHA256",
    "sourceUrl": "https://ORIGINAL_RECORDING_URL"
  }
}
```

Replace the placeholders; the hash must contain exactly 64 lowercase hexadecimal characters and match the MP3 bytes. The source filename must match `id`. Current support is MP3, en-US, and recordings up to 100 MB. This does not change the existing Polly input format.

### Updating and retrying

- An edited `human-passages/ID.json` starts a new execution. If audio bytes are unchanged, alignment is recomputed using the cached transcript, without another transcription charge.
- Changed audio gets a new SHA-256/key and transcript cache entry. Upload that MP3 first, then update the source JSON.
- Duplicate S3 notifications use the same execution name. Concurrent runs reuse the same deterministic Transcribe job. An older execution stops when the source changes; conditional pointer writes prevent it from overwriting a newer publication.
- A failed job, malformed input, or timeout leaves the previous working pointer intact. Step Functions execution history records the failure and output; use the `HumanAudioWorkflowArn` stack output to find it. API errors are not mistaken for cache misses.
- To retry after resolving an infrastructure/access issue, invoke the `HumanAudioStarterName` output with `{"sourceKey":"human-passages/ID.json"}`. This creates a fresh workflow execution and resumes the deterministic job. If Transcribe itself has marked that job `FAILED`, inspect its `FailureReason`; an authorized operator must delete that specific failed Transcribe job before retrying unchanged audio. The worker intentionally cannot delete jobs or silently incur repeated transcription charges.
- `HumanAudioStarterName` and `HumanAudioWorkflowArn` are CDK outputs alongside the existing bucket/function outputs. No direct console edits to deployed function code are needed.

## Local/offline review

Reusing a saved Transcribe JSON requires no AWS credentials or service calls:

```sh
python generation/human_audio.py YOUR_PASSAGE.json \
  --audio APPROVED_RECORDING.mp3 \
  --audio-url https://ORIGINAL_RECORDING_URL \
  --transcript SAVED_TRANSCRIBE_RESULT.json \
  --qa-verified
```

The command writes `audio.mp3`, `manifest.json`, `timings.json`, and `alignment-report.json` under ignored `generation/output/human/ID/HASH/`. It prints the exact manifest path. The developer server serves those local assets and byte ranges, so the normal reader can preview them:

```text
http://127.0.0.1:5173/?passage=ID&manifest=/generated/ID/human-HASH/manifest.json
```

The `manifest` query override is available only in development. The production reader uses the published completion pointer for unpinned passages, and `&latest=1` for pinned ones.

Without `--transcript` or `--queue`, the original builder-run mode remains available: provide `--bucket` and the command waits for Transcribe (default maximum 600 seconds). Rerun to resume an in-progress job. `--publish-preview` explicitly uploads the immutable local version but does not change the current pointer. `--qa-verified` is opt-in; without it, the original recognition-confidence filtering remains in place.

Install `generation/requirements.txt` before running the helper. Its Boto3 minimum supports the conditional S3 writes used to prevent stale pointer updates. Lambda uses the Boto3 SDK supplied by the Python 3.14 runtime.

Other options: `--cached-only` (queue mode), `--profile`, `--region` (default `us-west-2`), `--confidence` (default `0.8`, a filter only in unverified mode), `--output`, and `--maximum-wait`.

## Cost and maintenance

- Transcription cache: private `human-transcripts/AUDIO_SHA256/en-US-v1.json`. A text edit, threshold edit, QA flag change, or aligner upgrade does not retranscribe unchanged audio.
- Alignment assets: immutable version includes text/revision, attribution, recording hash, transcript contents, source URL, QA mode, and aligner version. Corrected transcript boundaries therefore get new URLs instead of overwriting cached timing files. The original MP3 is reused byte-for-byte; there is no Polly/ElevenLabs call in this workflow.
- Private source/audio/transcript prefixes are not served by CloudFront. The public `generated/` assets must contain only approved demonstration/ReadWorks content. Do not commit full copyrighted source fixtures to GitHub.
- Step Functions is billed per transition, with S3, Lambda, transcription, and delivery billed separately. Waiting avoids a paid Lambda invocation sitting idle for the transcription duration. There is no continuously running worker. Use a small representative batch before scaling.
- The new workflow is tested locally with fake AWS clients and synthesized infrastructure. Real AWS transcription and workflow execution still need a sandbox smoke run after deployment; the cached local sample is not evidence of a new live Transcribe run.

Transcribe start permission uses the wildcard resource required by AWS, constrained to this bucket and the `human-transcripts/*` output prefix. Reading job status is restricted to the `soundworks-human-*` job names. See the [AWS authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_transcribe.html).

References: [Transcribe batch API](https://docs.aws.amazon.com/transcribe/latest/APIReference/API_StartTranscriptionJob.html), [CDK Step Functions](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_stepfunctions-readme.html).

## Verification

```sh
PYTHONPATH=generation python -m unittest discover -s generation/tests -v
node --test apps/reader/test/*.test.js
npm test -w @soundworks/infra
```

Tests cover QA/recognition confidence, bounded name recovery, introductions, repeated words, numeric phrases, UTF-16 offsets, invalid timestamps, cache reuse, actual audio hash checks, asynchronous polling, duplicate starts, failed jobs, source edits, concurrent pointer publication, and separate private source triggers. Browser verification checks click-to-seek and highlighting on the actual cached caretaker recording.
