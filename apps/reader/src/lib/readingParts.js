import { findSentenceStartOffset } from './wordTiming.js';

// Splits one paragraph into sentences for the Color Focus sentence highlight. Returns, in order,
// sentences { key, parts } and the plain spaces between them as { text }. A sentence's parts are
// its word tokens and the text around them, so opening quotes and closing punctuation stay with
// their sentence; key is the sentence's start offset in the paragraph.
export function splitSentences(text, tokens) {
  const items = [];
  let sentence = null, cursor = 0;
  for (const token of tokens) {
    const key = findSentenceStartOffset(text, token.start);
    if (!sentence || key !== sentence.key) {
      const start = Math.max(cursor, Math.min(key, token.start));
      const before = text.slice(cursor, start);
      const closing = sentence ? before.trimEnd() : '';
      if (closing) sentence.parts.push({ text: closing });
      if (before.length > closing.length) items.push({ text: before.slice(closing.length) });
      sentence = { key, parts: [] };
      items.push(sentence);
      cursor = start;
    }
    if (token.start > cursor) sentence.parts.push({ text: text.slice(cursor, token.start) });
    sentence.parts.push(token);
    cursor = token.end;
  }
  const rest = text.slice(cursor);
  if (rest) (sentence ? sentence.parts : items).push({ text: rest });
  return items;
}

// Color Focus reads a passage in parts, one paragraph each. A part starts when its first timed
// word starts; paragraphs with no timed words are read as part of the one before.
export function partStarts(tokens, timings) {
  const startMs = new Map(timings.map(item => [item.tokenId, item.startMs]));
  const seen = new Set();
  const parts = [];
  for (const token of tokens) {
    if (seen.has(token.paragraphId) || !startMs.has(token.id)) continue;
    seen.add(token.paragraphId);
    parts.push({ paragraphId: token.paragraphId, start: startMs.get(token.id) / 1000 });
  }
  return parts.sort((a, b) => a.start - b.start);
}

// Index of the part whose start playback reached while moving forward from `from` to `to`
// seconds, or -1. The first part is never "reached": starting the passage doesn't end a part.
export function crossedPartStart(parts, from, to) {
  if (!(to > from)) return -1;
  return parts.findIndex((part, index) => index > 0 && from < part.start && to >= part.start);
}

// Index of the part playing at `seconds`; 0 before the first word.
export function partIndexAt(parts, seconds) {
  let index = 0;
  parts.forEach((part, i) => { if (part.start <= seconds) index = i; });
  return index;
}
