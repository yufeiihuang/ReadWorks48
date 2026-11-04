# Listening QA: SoundWorks reader

**Tester:** Sridhar | **Date:** Nov 4, 2026 | **Build:** local run (`npm run dev`, http://127.0.0.1:5173) | **Browser:** Chrome
**Passage tested:** "A Morning in the Garden" (Stephen Neural, 49 words, 0:17)

## Summary
The core experience works: tapping a word and reading from it is accurate, and the word highlight follows the audio well.
Five issues were found. The two most visible in a demo are **QA-1** (word-only audio is cut off) and **QA-2** (audio overlaps).

## What passed
| Check | Result |
|---|---|
| "Read from there": click any word, audio starts at that word | Pass |
| Word highlight matches the spoken word | Pass |

## Not tested yet
Long chunked passage, `park-caretaker` (human narration), `pride-and-prejudice`, keyboard-only use, phone width, Safari/Firefox, and the Color Focus pull request (pending).

## Issues
| ID | Severity | What happened | Expected | Suggestion |
|---|---|---|---|---|
| QA-1 | High | **"Hear just that word"** plays a slice of the full recording, so the next word leaks in (clicking "garden" gives "garden ju-"). Happens on most words. | The single word pronounced clearly, alone. | Timings only store word *starts* (see `docs/generation.md`), so the clip end is a guess. Best fix: pre-generate a short Polly clip per unique word (same voice, cached by word). Quick mitigation: end the clip a little before the next word starts. For human recordings, Transcribe timings include end times, so the clip can stop at the real word end. |
| QA-2 | High | While the passage is playing, switching to **"Hear just that word"** and tapping a word interrupts the passage, plays the word, then the rest of the passage resumes. | Passage pauses, the word plays, and playback stays paused (or resumes only if the student chooses). | In the audio controller's word-only path: pause the main audio first and don't auto-resume. |
| QA-3 | Medium | **1x speed is too fast** for a learner. 49 words in 17 s is about 173 words per minute. | A calmer default for students. | Default to about 0.85x (about 147 wpm) or add 0.75x/0.85x options (0.75x is about 130 wpm). Reader setting only, no regeneration needed. |
| QA-4 | Medium | **Vocabulary Activity** and **Question Set** tabs do nothing when clicked. | Either work or clearly not part of the demo. | Show "Coming soon", or hide them, so a judge doesn't think the app is broken. |
| QA-5 | Low | **"Brrr!"** sounds robotic. | Natural-sounding interjection. | Known Polly Neural limitation for sound words. Options: test a Polly pronunciation lexicon (confirm it keeps text and timings aligned), or avoid such words in demo passages and list it as a known limit. |
