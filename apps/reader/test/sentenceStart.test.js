import test from 'node:test';
import assert from 'node:assert/strict';
import { findSentenceStartOffset } from '../src/lib/wordTiming.js';

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
