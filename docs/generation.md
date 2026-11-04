# Stephen Neural passage preparation

## Generate locally

Use Python 3.12+ locally (Lambda uses Python 3.14). Configure temporary sandbox credentials in your terminal, or pass `--profile YOUR_PROFILE`.

```sh
python3 -m venv generation/.venv
source generation/.venv/bin/activate
pip install -r generation/requirements.txt
python generation/generate.py shared/fixtures/demo.json --validate-only
python generation/generate.py shared/fixtures/demo.json
```

The default voice is Stephen, engine is always Neural, and region is `us-west-2`. Output lives under ignored `generation/output/`. The command prints the local manifest/audio paths and request character counts. When a bucket is supplied, the S3 cache is checked first. Without a bucket, matching validated local assets are reused. `--force` bypasses both caches. Text, paragraph structure, revision, title, language, voice, or pipeline setting changes invalidate the cache.

To publish to the deployed sandbox, pass the bucket name from CDK outputs:

```sh
python generation/generate.py shared/fixtures/demo.json --bucket YOUR_PASSAGE_ASSETS_BUCKET
```

Only approved/public passage text should be published. Files appear at `/generated/PASSAGE_ID/ASSET_VERSION/` on the reader's CloudFront domain. S3 uploads audio and timing files first and the manifest last. This command does not switch the Express API's fixture or implement frontend playback; those belong to builders A and D.

## Generate from ReadWorks JSON

Pass a ReadWorks UUID, product JSON URL, or saved product JSON file. A UUID downloads the public QA product JSON and needs no other setup:

```sh
python generation/generate.py 2b781dab-4521-40d2-a9b6-ad5f2bb0ba98 --validate-only
python generation/generate.py 2b781dab-4521-40d2-a9b6-ad5f2bb0ba98 --bucket YOUR_PASSAGE_ASSETS_BUCKET
```

`generation/readworks.py` uses `uuid` as the passage id, maps `lang` `EN` to `en-US`, and splits `text` on line breaks into paragraphs. `revision` is always 1 because the input hash already detects text changes. Ebook-style passages, other languages, and passages whose `content` shows words that `text` lacks (other than figures and captions) stop with an error. The reader displays paragraph text only, so images and vocabulary markup from `content` aren't shown yet.

Publishing also writes `generated/PASSAGE_ID/current.json`, including on a cache hit, which names the newest manifest. Open a passage at `/?passage=PASSAGE_ID`. If a ReadWorks passage hasn't been generated, the API reads its public product JSON and the reader shows the text with a message that audio isn't ready. Opening a passage never starts generation. The pointer is cached for 60 seconds, so a new version can take about a minute to appear. Versioned files never change.

## Output contract for the reader

- `manifest.json`: original paragraphs, unique word tokens, audio URL, timings, generation metadata.
- `audio.wav`: mono 16-bit 16 kHz recording, playable by the browser audio element.
- `timings.json`: ordered `{tokenId, startMs}` objects; word starts, not inferred word ends.
- `speech-marks.json`: raw provider marks and chunk offsets for troubleshooting.
- `wordAudio` (in the manifest): `{baseUrl, format, voice, engine, clips}`, where `clips` maps every token id to a word clip id. The clip is `baseUrl + id + '.mp3'`.

## Word clips for "Hear just that word"

Slicing a word out of the passage recording can't be clean. Neural speech runs words together, and Polly marks only word starts, so the next word's first sound leaks in (QA-1). Instead, each unique word is also synthesized on its own (same voice, Neural, MP3) and stored at `generated/words/VOICE/CLIP_ID.mp3`.

- The clip id hashes the word, voice, language, engine and `WORD_CLIP_VERSION`. Words that differ only by a leading capital share a clip ("The"/"the"). ALL-CAPS words keep their own.
- Clips are shared by every passage with the same voice. A clip already on disk or in the bucket is never requested again, including from a fresh Lambda.
- Clips are uploaded before the manifest that refers to them. `generation.wordClipCount` and `generation.wordRequestCharacters` report them, and `requestCharacters` includes them.
- The reader plays the clip on a second audio element and pauses the passage in place. Manifests without `wordAudio` (generated before pipeline version 3, or human narration) fall back to slicing the passage recording.
- Words alone use their dictionary pronunciation ("the" may sound like "thee"). Polly can't tell which pronunciation of a homograph ("read", "live") was meant.

Each token has `id`, `paragraphId`, exact spoken `text`, and `start`/`end` JavaScript UTF-16 offsets into its paragraph. Render gaps from the original paragraph to preserve punctuation and spacing. Timings reference unique token IDs even when words repeat. URLs are relative to the deployed reader origin; local preview code must serve these files under `/generated/` if using them locally.

The asset version includes input/settings and audio hashes. A fresh recording has a fresh public URL even when regenerating identical text. Don't mix timings from different asset versions.

## Passages longer than 3,000 characters

Each request uses at most 2,800 plain-text characters. Paragraphs are split at sentence boundaries when possible, otherwise at whitespace. Unusually long unsplittable words fail explicitly. Audio and speech marks use identical text, voice, language, and engine settings in separate Polly requests.

We request raw PCM audio so Python's standard library can combine it into one WAV recording without FFmpeg or an audio-processing dependency. Each chunk's timestamps are shifted by the exact number of audio samples preceding it, including a 150 ms boundary pause. Chunk duration is measured from PCM samples, never estimated from text or the last word mark.

WAV is larger than MP3 (about 1.92 MB per minute). This is an intentional MVP tradeoff for reliable concatenation with minimal dependencies. Compression can follow later without changing the word timing contract.

## Private Lambda invocation

The private Lambda accepts `{"passage": <the complete input passage object>}`. It uses Stephen Neural, generates into temporary storage, publishes to its configured asset bucket, and returns `status: ready`, `manifestUrl`, word count, and generation metadata. Direct invocation still requires a complete passage object. S3 events load passage JSON from the source key described below.

The function has a five-minute timeout. For large batches use the local command or a later queued workflow; don't invoke generation on student playback. AWS errors propagate as failed invocations. Invalid passage input returns `status: invalid_input`. No manual timestamp editing is required.

## Verify

```sh
PYTHONPATH=generation python -m unittest discover -s generation/tests -v
```

Tests cover long-passage chunking, repeated words, accented characters and emoji offsets, cumulative timing, missing-word rejection, and cache invalidation. Provider marks must match the input text and be monotonic/in bounds before a ready manifest is written. These checks validate data integrity; listening and measuring perceived synchronization still require human review.

Polly bills audio and speech marks separately. `generation.requestCharacters` sums both requests. S3 and local cache hits make no synthesis calls. The response reports `cached`, `cacheSource`, and `synthesisRequestCharacters`; that last field is zero on a hit. `generation.requestCharacters` describes the original recording, not new charges for the cache hit. Neural output from separate audio/mark requests must still be spot-checked for audible alignment.

## Verified sandbox samples

On November 3, 2026, Stephen Neural was confirmed available in `us-west-2`. Local generation and the deployed Lambda both generated the 49-word original garden passage successfully. The published sample manifest is:

https://d1381qenwhm2qw.cloudfront.net/generated/demo/efbf8d68f9ca6f777630-4386b7353988/manifest.json

A separate 3,824-character input generated one recording with 630 word timings over two chunks. Local cache reuse was verified. Seven unit tests and three infrastructure tests passed. These are functional checks, not a measured perceptual timing or pronunciation score; listen to the samples before demo sign-off.

## Integrated reader and preview

The main reader now loads the published Stephen sample manifest and connects it to the team's atomic audio console through `useAudioPlayer`. `PassageText.vue` renders words using the manifest's UTF-16 offsets; its replay event calls the same controller's `playFrom` method. Highlighting derives from that controller's audio clock, including seeks and speed changes. There is only one playback controller per reader.

`/preview.html` remains a compatible alias of this same reader. Temporary native browser controls have been removed. Locally, the `/generated` proxy reads the approved demo assets from CloudFront. If generated assets are unavailable, the reader falls back to the plain API passage and explains that audio is temporarily unavailable.

The reference route `/?passage=pride-and-prejudice` still loads the teammate's existing ReadWorks recording. It intentionally has no word highlighting until timing data is prepared for that exact human/existing recording. Polly timestamps from a different recording must never be reused for it.

Run synchronization boundary tests with `node --test apps/reader/test/*.test.js`.

## Shared S3 cache

Both the private Lambda and CLI with `--bucket` check a stable completion index at `generated/PASSAGE_ID/cache/INPUT_HASH.json` before synthesis. The hash includes the passage identity, revision, title, language, exact paragraphs, voice, Neural engine, sample rate, and pipeline version.

The cache reuses only a matching ready manifest with audio metadata and complete matching timing/diagnostic objects. Missing or malformed cache data is a miss. Access errors fail explicitly instead of silently incurring new Polly calls. Immutable assets and the versioned manifest are published before the completion index. Existing recordings created before this cache was introduced will populate the index on their next preparation.

`{"passage": <input>, "force": true}` bypasses caches for a direct Lambda invocation. Failed uploads never create a new completion index. S3 duplicate notifications arriving after a completed generation reuse the cache; simultaneous cache misses can still generate duplicate work. This MVP does not provide an exactly-once distributed lock.

## Automatic regeneration after S3 edits

Upload our normalized passage JSON to the private passage bucket at **`passages/PASSAGE_ID.json`**. The filename must match the JSON `id`. Use `shared/fixtures/demo.json` as the input format: `id`, positive integer `revision`, `title`, `language`, and `paragraphs` containing unique `id` and `text` fields. To use this route for ReadWorks JSON, convert it first; the CLI command above converts and publishes directly.

```sh
aws s3 cp shared/fixtures/demo.json s3://YOUR_PASSAGE_ASSETS_BUCKET/passages/demo.json
```

Overwriting that key triggers the generation Lambda automatically. A changed passage produces new audio and timing assets; an unchanged re-upload reuses the shared cache. JSON whitespace or unrelated metadata changes do not trigger fresh synthesis. Bump `revision` for deliberate new content versions. The source JSON is private and is not served through CloudFront.

S3 notifications filter on `passages/` plus `.json`, while generated assets live under `generated/`, preventing a recursive generation loop. The handler reads the current object even if the notification refers to an older version. Every completed event writes its result (including source version, cache-hit flag, and output manifest URL) to `generated/PASSAGE_ID/events/PASSAGE_ID-INPUT_HASH.json` and logs it in CloudWatch. Invalid input fails the invocation and follows AWS's normal asynchronous retry behavior.

Generation is automatic. Other passages load through `current.json`, while the `demo` passage remains pinned to its approved manifest. Existing open recordings keep their matching text/timings rather than silently changing underneath playback.

## Clear a selected word

Click blank space in the reader to clear the selected-word highlight without stopping playback. Selecting another word or resuming playback restores highlighting. The audio console remains connected to the same controller.

## Cache and update verification

Verified in the sandbox on November 3, 2026:

- Direct Lambda generation followed by a second invocation returned `cached: true`, `cacheSource: s3`, and zero new synthesis characters.
- Uploading `passages/automation-check.json` automatically generated narration (58 synthesis request characters). An unchanged re-upload returned the same version with zero new synthesis characters. Editing the text/revision automatically produced a different version (122 synthesis request characters).
- The CLI with `--bucket` also reuses the shared S3 cache.
- Blank-space clicks clear the highlight in the deployed reader; playback controls remain usable.
- Seventeen Python tests, four infrastructure checks, and three timing tests pass.
