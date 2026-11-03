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

The default voice is Stephen, engine is always Neural, and region is `us-west-2`. Output lives under ignored `generation/output/`. The command prints the local manifest/audio paths and request character counts. Run again to reuse matching validated local assets; `--force` regenerates them. Text, revision, or voice changes invalidate the cache.

To publish to the deployed sandbox, pass the bucket name from CDK outputs:

```sh
python generation/generate.py shared/fixtures/demo.json --bucket YOUR_PASSAGE_ASSETS_BUCKET
```

Only approved/public passage text should be published. Files appear at `/generated/PASSAGE_ID/ASSET_VERSION/` on the reader's CloudFront domain. S3 uploads audio and timing files first and the manifest last. This command does not switch the Express API's fixture or implement frontend playback; those belong to builders A and D.

## Output contract for the reader

- `manifest.json`: original paragraphs, unique word tokens, audio URL, timings, generation metadata.
- `audio.wav`: mono 16-bit 16 kHz recording, playable by the browser audio element.
- `timings.json`: ordered `{tokenId, startMs}` objects; word starts, not inferred word ends.
- `speech-marks.json`: raw provider marks and chunk offsets for troubleshooting.

Each token has `id`, `paragraphId`, exact spoken `text`, and `start`/`end` JavaScript UTF-16 offsets into its paragraph. Render gaps from the original paragraph to preserve punctuation and spacing. Timings reference unique token IDs even when words repeat. URLs are relative to the deployed reader origin; local preview code must serve these files under `/generated/` if using them locally.

The asset version includes input/settings and audio hashes. A fresh recording has a fresh public URL even when regenerating identical text. Don't mix timings from different asset versions.

## Passages longer than 3,000 characters

Each request uses at most 2,800 plain-text characters. Paragraphs are split at sentence boundaries when possible, otherwise at whitespace. Unusually long unsplittable words fail explicitly. Audio and speech marks use identical text, voice, language, and engine settings in separate Polly requests.

We request raw PCM audio so Python's standard library can combine it into one WAV recording without FFmpeg or an audio-processing dependency. Each chunk's timestamps are shifted by the exact number of audio samples preceding it, including a 150 ms boundary pause. Chunk duration is measured from PCM samples, never estimated from text or the last word mark.

WAV is larger than MP3 (about 1.92 MB per minute). This is an intentional MVP tradeoff for reliable concatenation with minimal dependencies. Compression can follow later without changing the word timing contract.

## Private Lambda invocation

The private Lambda accepts `{"passage": <the complete input passage object>}`. It uses Stephen Neural, generates into temporary storage, publishes to its configured asset bucket, and returns `status: ready`, `manifestUrl`, word count, and generation metadata. A passage ID alone is insufficient; S3 input discovery is not implemented.

The function has a five-minute timeout. For large batches use the local command or a later queued workflow; don't invoke generation on student playback. AWS errors propagate as failed invocations. Invalid passage input returns `status: invalid_input`. No manual timestamp editing is required.

## Verify

```sh
PYTHONPATH=generation python -m unittest discover -s generation/tests -v
```

Tests cover long-passage chunking, repeated words, accented characters and emoji offsets, cumulative timing, missing-word rejection, and cache invalidation. Provider marks must match the input text and be monotonic/in bounds before a ready manifest is written. These checks validate data integrity; listening and measuring perceived synchronization still require human review.

Polly bills audio and speech marks separately. `generation.requestCharacters` sums both requests. Cached local runs make no synthesis calls. Neural output from separate audio/mark requests must still be spot-checked for audible alignment.

## Verified sandbox samples

On November 3, 2026, Stephen Neural was confirmed available in `us-west-2`. Local generation and the deployed Lambda both generated the 49-word original garden passage successfully. The published sample manifest is:

https://d1381qenwhm2qw.cloudfront.net/generated/demo/efbf8d68f9ca6f777630-4386b7353988/manifest.json

A separate 3,824-character input generated one recording with 630 word timings over two chunks. Local cache reuse was verified. Seven unit tests and three infrastructure tests passed. These are functional checks, not a measured perceptual timing or pronunciation score; listen to the samples before demo sign-off.
