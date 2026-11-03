import test from 'node:test';
import assert from 'node:assert/strict';
import { findSentenceStartOffset, findSentenceStartSeconds } from '../src/lib/wordTiming.js';

// Build word tokens with real UTF-16 offsets from a paragraph, matching the
// generation contract (id, paragraphId, text, start, end). Each token also gets
// a timing (tokenId, startMs) spaced 500ms apart so positions map to times.
function build(paragraphId, text, baseMs = 0, step = 500) {
  const tokens = [];
  const timings = [];
  const wordRe = /[A-Za-z\u2019']+/g;
  let match;
  let i = 0;
  while ((match = wordRe.exec(text)) !== null) {
    const id = `${paragraphId}-w${i}`;
    tokens.push({ id, paragraphId, text: match[0], start: match.index, end: match.index + match[0].length });
    timings.push({ tokenId: id, startMs: baseMs + i * step });
    i += 1;
  }
  return { paragraph: { id: paragraphId, text }, tokens, timings };
}

// Return the ms time of the nth word (0-indexed) in a built set.
const msOf = (built, n) => built.timings[n].startMs;

test('findSentenceStartOffset: first sentence returns 0', () => {
  const text = 'He welcomed them warmly. She cried out.';
  assert.equal(findSentenceStartOffset(text, 0), 0);
  assert.equal(findSentenceStartOffset(text, 5), 0); // inside "welcomed"
});

test('findSentenceStartOffset: second sentence starts after the period + space', () => {
  const text = 'He welcomed them warmly. She cried out.';
  const secondStart = text.indexOf('She');
  // offset anywhere in the second sentence resolves to its start
  assert.equal(findSentenceStartOffset(text, secondStart), secondStart);
  assert.equal(findSentenceStartOffset(text, secondStart + 2), secondStart);
  assert.equal(findSentenceStartOffset(text, text.length - 1), secondStart);
});

test('findSentenceStartOffset: abbreviation period does not split the sentence', () => {
  const text = 'Mr. Collins arrived early. He stayed late.';
  const collins = text.indexOf('Collins');
  // "Collins" is in the FIRST sentence despite the period in "Mr."
  assert.equal(findSentenceStartOffset(text, collins), 0);
  const he = text.indexOf('He');
  assert.equal(findSentenceStartOffset(text, he), he);
});

test('findSentenceStartOffset: single-letter initials do not split', () => {
  const text = 'Sir William W. Lucas spoke. Then he left.';
  const lucas = text.indexOf('Lucas');
  assert.equal(findSentenceStartOffset(text, lucas), 0);
});

test('findSentenceStartOffset: closing quote/bracket stays with its sentence', () => {
  const text = '"Hello there!" she cried. He smiled.';
  // The word after the quoted exclamation belongs to the first sentence's
  // continuation; the next sentence starts at "He".
  const she = text.indexOf('she');
  assert.equal(findSentenceStartOffset(text, she), she);
  const he = text.indexOf('He smiled');
  // boundary skips the closing quote and the period+space before "He"
  assert.equal(findSentenceStartOffset(text, he), he);
});

test('findSentenceStartSeconds: mid-sentence resolves to that sentence start time', () => {
  const text = 'He welcomed them warmly. She cried out loud.';
  const b = build('p1', text);
  // words: He(0) welcomed(1) them(2) warmly(3) She(4) cried(5) out(6) loud(7)
  // Play during "cried" (word 5) -> sentence starts at "She" (word 4)
  const seconds = findSentenceStartSeconds([b.paragraph], b.tokens, b.timings, msOf(b, 5) / 1000, 0);
  assert.equal(seconds, msOf(b, 4) / 1000);
});

test('findSentenceStartSeconds: within the first sentence returns the passage start time', () => {
  const text = 'He welcomed them warmly. She cried out loud.';
  const b = build('p1', text);
  // Play during "warmly" (word 3) -> first sentence -> word 0 time
  const seconds = findSentenceStartSeconds([b.paragraph], b.tokens, b.timings, msOf(b, 3) / 1000, 0);
  assert.equal(seconds, msOf(b, 0) / 1000);
});

test('findSentenceStartSeconds: before playback starts targets the first sentence', () => {
  const text = 'He welcomed them. She cried.';
  const b = build('p1', text);
  // currentTime 0, not started -> first token's sentence (word 0)
  const seconds = findSentenceStartSeconds([b.paragraph], b.tokens, b.timings, 0, 0);
  assert.equal(seconds, msOf(b, 0) / 1000);
});

test('findSentenceStartSeconds: at/after end resolves to the last sentence', () => {
  const text = 'He welcomed them. She cried out.';
  const b = build('p1', text);
  const duration = (b.timings.at(-1).startMs + 500) / 1000;
  // position past the end (>= duration) -> findActiveToken returns null ->
  // falls back to first token, but we want the LAST sentence when near the end.
  // Use a position inside the last word instead to assert last-sentence start.
  const lastWordTime = b.timings.at(-1).startMs / 1000;
  const seconds = findSentenceStartSeconds([b.paragraph], b.tokens, b.timings, lastWordTime, duration);
  const sheIndex = b.tokens.findIndex(t => t.text === 'She');
  assert.equal(seconds, msOf(b, sheIndex) / 1000);
});

test('findSentenceStartSeconds: position past duration targets the last sentence', () => {
  const text = 'He welcomed them. She cried out.';
  const b = build('p1', text);
  const duration = (b.timings.at(-1).startMs + 500) / 1000;
  // Audio finished: currentTime === duration, so findActiveToken returns null.
  const seconds = findSentenceStartSeconds([b.paragraph], b.tokens, b.timings, duration, duration);
  const sheIndex = b.tokens.findIndex(t => t.text === 'She');
  assert.equal(seconds, msOf(b, sheIndex) / 1000);
});

test('findSentenceStartSeconds: abbreviation keeps the whole sentence together', () => {
  const text = 'Mr. Collins arrived early. He left.';
  const b = build('p1', text);
  // words: Mr(0) Collins(1) arrived(2) early(3) He(4) left(5)
  // Play during "early" (word 3) -> sentence start is "Mr" (word 0), NOT after "Mr."
  const seconds = findSentenceStartSeconds([b.paragraph], b.tokens, b.timings, msOf(b, 3) / 1000, 0);
  assert.equal(seconds, msOf(b, 0) / 1000);
});

test('findSentenceStartSeconds: idempotent when already at a sentence start', () => {
  const text = 'He welcomed them. She cried out.';
  const b = build('p1', text);
  const sheIndex = b.tokens.findIndex(t => t.text === 'She');
  const start = msOf(b, sheIndex) / 1000;
  const once = findSentenceStartSeconds([b.paragraph], b.tokens, b.timings, start, 0);
  assert.equal(once, start);
  // applying again from the computed start stays put
  const twice = findSentenceStartSeconds([b.paragraph], b.tokens, b.timings, once, 0);
  assert.equal(twice, start);
});

test('findSentenceStartSeconds: sentence detection is scoped per paragraph', () => {
  const p1 = build('p1', 'First para only sentence.', 0);
  const p2 = build('p2', 'Second para first. Second para second.', 10000);
  const paragraphs = [p1.paragraph, p2.paragraph];
  const tokens = [...p1.tokens, ...p2.tokens];
  const timings = [...p1.timings, ...p2.timings];
  // Play during the last word of p2 -> sentence start is p2's second sentence,
  // never crossing back into p1.
  const lastP2 = p2.timings.at(-1).startMs / 1000;
  const seconds = findSentenceStartSeconds(paragraphs, tokens, timings, lastP2, 0);
  const secondIdx = tokens.findIndex(t => t.paragraphId === 'p2' && t.text === 'Second' && t.start === p2.paragraph.text.indexOf('Second para second'));
  assert.equal(seconds, timings[secondIdx].startMs / 1000);
});

test('findSentenceStartSeconds: returns null without timing/token data', () => {
  const text = 'He welcomed them. She cried.';
  const b = build('p1', text);
  assert.equal(findSentenceStartSeconds([b.paragraph], [], [], 1, 0), null);
  assert.equal(findSentenceStartSeconds([b.paragraph], b.tokens, [], 1, 0), null);
});
