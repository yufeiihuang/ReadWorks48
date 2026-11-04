# Cost: what it takes to narrate the ReadWorks library

*Prices checked on Nov 4, 2026 against the AWS Polly pricing page. Library figures come from the ReadWorks Vision document.*

## The short version
- Audio is generated **once per passage**, then reused. Students listening triggers **no new Polly charges** (small CloudFront and S3 delivery costs still apply).
- Polly Neural costs **$16 per million characters**, and the word-timing request (speech marks) is billed separately at the same rate. Audio plus timings is therefore **$32 per million characters**, or twice a passage's character count at $16.
- Generating the whole library once, with word timing, is roughly **$640**. Neural audio alone would be about $320.
- The Vision document asks teams to measure cost per passage and show the projected full-catalog cost. This document does that.

## Price per million characters
| Item | Price per million characters | Source |
|---|---|---|
| ReadWorks existing audio generation cost (voice and service not stated; timings not mentioned) | $4 | Vision document |
| Polly Standard voice, audio only | $4 | AWS pricing page |
| **Polly Neural, audio only** | **$16** | AWS pricing page |
| Polly Neural, word timings (speech marks) | $16 | AWS pricing page |
| **Polly Neural, audio + timings (what we built)** | **$32** | Sum of the two requests |

The complete solution is 8 times ReadWorks' stated existing figure, assuming the two figures are directly comparable.

## Other inputs
| Input | Value | Source |
|---|---|---|
| Library size | 20 million characters, 6,893 passages | Vision document |
| Passages currently using computerized audio | 64% (36% are human-read) | Vision document |
| Average passage length | about 2,900 characters (20 million / 6,893) | Derived |
| Requests per passage | 2 (audio + timings), each billed on the full text | Team generation doc (`docs/generation.md`) |

## Formula
`cost = characters x 2 requests x price per million / 1,000,000`

*Note on request size:* Polly's synchronous SynthesizeSpeech API allows up to 3,000 billed characters per request. Our pipeline splits longer passages into chunks of at most 2,800 characters and stitches them together (the 3,824-character test used two chunks). Cost is based on total characters, not the number of API calls, so chunking does not change these estimates.

## Results
| Scenario | Characters billed | Cost |
|---|---|---|
| Short demo passage (about 300 characters) | about 600 | under $0.01 |
| 3,824-character passage (our long test) | 7,648 | about $0.12 |
| Average ReadWorks passage (about 2,900 characters) | about 5,800 | about $0.09 |
| **Whole library, Neural, audio + timings** | **40,000,000** | **about $640** |
| Whole library, Neural, audio only (no highlighting) | 20,000,000 | about $320 |
| Regenerate the 64% of passages currently using computerized audio, Neural, audio + timings (assumes characters are spread evenly) | about 25,600,000 | about $410 |
| Whole library, Standard voice, audio + timings | 40,000,000 | about $160 |
| ReadWorks' existing figure, audio only | 20,000,000 | about $80 |

## Why it stays affordable
- **Generate once, reuse:** our pipeline checks a cache in S3 (keyed on the passage text and settings) before calling Polly. Unchanged text makes no new Polly calls. This is a property of our pipeline, not of S3 itself. It was verified in the sandbox: zero new characters on an unchanged re-upload.
- **Scales with passages, not listeners:** on average, 888,147 students use the audio guides each week (Vision document). Cached audio means they cost no more in Polly charges than one.
- **Only new passages, edited text, or changed generation settings (such as a different voice) require new generation.** Unchanged passages reuse their cached audio and timing data.
- **Storage is small:** the audio is WAV (about 1.9 MB per minute). Estimates for the full library range from about 40 GB (using the pace of our sample passage) to about 55 GB (using AWS's example of about 23 hours of speech per million characters). At about $0.023 per GB-month, that is roughly **$1 to $1.25 a month** in S3 storage.

## Honest caveats
- The figures assume the library matches what ReadWorks reported and that every passage is generated once.
- These figures cover Polly narration only. The experimental alignment of existing human recordings uses Amazon Transcribe, which has its own batch-transcription charge that is not included here (see the team's human audio doc). That cost is paid once per recording and cached.
- Polly's free tier (1 million Neural characters per month for 12 months, new accounts only) is not counted.
- CloudFront data transfer, Lambda, and S3 requests add small amounts that are not included above.
- Audio duration and file size depend on voice speed, sample rate, and encoding, so storage is an estimate.
- Prices come from AWS's published page and may change; check the pricing page before quoting them externally.

## Sources
- AWS Amazon Polly pricing page (Standard, Neural, and speech marks pricing).
- ReadWorks Vision document (library size, passage count, audio split, $4 benchmark, request to project full-catalog cost).
- Team generation doc, `docs/generation.md` (two billed requests per passage, cache behavior).
