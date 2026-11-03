# SoundWorks architecture

Vue reader → Express read-only API → versioned passage manifest and assets in S3.

Python preparation → Polly Neural audio + separate word speech marks → validated assets → manifest published last.

## Ownership

- A: shared playback controller, highlighting, seeking, integration.
- B: Python generation, timing conversion, pronunciation validation.
- C: reader presentation and console controls.
- D: source JSON adapter, passage contract, Express routes.
- E: CDK, deployment, accessibility and browser checks.

## Contract rules

Times use milliseconds. Token offsets use JavaScript UTF-16 string indices into each paragraph; convert Polly UTF-8 byte offsets during preparation. Word IDs are unique within a passage revision. Preserve whitespace and punctuation. Timings reference token IDs. Audio, text, and timings share one asset version. No timings are supplied until a matching recording exists.

Audio currentTime is the synchronization source of truth. All controls operate one audio element. No per-student narration generation. Existing human recordings are reference material only for this MVP.

## Follow-up implementation

The scaffold has no audio playback or generated timing yet. Implement Lambda invocation, Polly calls, chunk handling, validation, asset publishing, ReadWorks JSON adaptation, production asset delivery, and frontend hosting in the corresponding tickets. The initial CDK stack creates only a private, versioned asset bucket; it does not deploy the reader or API.
