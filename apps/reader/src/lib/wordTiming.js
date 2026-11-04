// Timing arrays are ordered word-start timestamps from the matching recording.
function lastStartedTiming(timings, seconds, duration) {
  if (!Number.isFinite(seconds) || seconds < 0 || (duration > 0 && seconds >= duration)) return null;
  let low = 0, high = timings.length - 1, result = null;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (timings[middle].startMs <= seconds * 1000) { result = timings[middle]; low = middle + 1; }
    else high = middle - 1;
  }
  return result;
}

export function findActiveToken(timings, seconds, duration = 0) {
  const result = lastStartedTiming(timings, seconds, duration);
  if (result && Number.isFinite(result.endMs) && seconds * 1000 >= result.endMs) return null;
  return result?.tokenId ?? null;
}

// The most recently started word, held through the pause after it ends (where findActiveToken
// clears), so place markers such as the Color Focus sentence highlight don't flicker off.
export function findLastStartedToken(timings, seconds, duration = 0) {
  return lastStartedTiming(timings, seconds, duration)?.tokenId ?? null;
}

// Sentence terminators and the trailing characters (closing quotes/brackets) that
// belong to the same sentence as the terminator before them.
const SENTENCE_TERMINATORS = new Set(['.', '!', '?']);
const SENTENCE_TRAILERS = new Set(['"', '\u201d', '\u2019', "'", ')', ']', '\u00bb']);

// Abbreviations whose trailing period must NOT be treated as a sentence end.
// Lowercased, without the period. Covers the titles and short forms present in
// the reference passages (Mr., Mrs., Dr., etc.).
const ABBREVIATIONS = new Set([
  'mr', 'mrs', 'ms', 'dr', 'st', 'jr', 'sr', 'prof', 'rev', 'hon',
  'vs', 'etc', 'no', 'vol', 'pp',
]);

// Returns true when the period at index `periodIndex` in `text` is part of an
// abbreviation (e.g. the dot in "Mr.") rather than a real sentence terminator.
function isAbbreviationPeriod(text, periodIndex) {
  if (text[periodIndex] !== '.') return false;
  let end = periodIndex;
  let start = periodIndex - 1;
  while (start >= 0 && /[A-Za-z]/.test(text[start])) start -= 1;
  const word = text.slice(start + 1, end).toLowerCase();
  if (!word) return false;
  if (ABBREVIATIONS.has(word)) return true;
  // Single-letter initials such as "A." or "W." (e.g. "Sir William W.").
  if (word.length === 1) return true;
  return false;
}

/**
 * Find the character offset in `text` where the sentence containing `offset`
 * begins. Scans backward for the previous real sentence terminator, skips any
 * trailing quote/bracket characters and whitespace, and lands on the first
 * character of the next sentence. Returns 0 when `offset` is in the first
 * sentence of the paragraph.
 */
export function findSentenceStartOffset(text, offset) {
  if (typeof text !== 'string' || text.length === 0) return 0;
  const clamped = Math.max(0, Math.min(offset, text.length));
  // Walk backward from just before the current position looking for a
  // terminator that ends the *previous* sentence.
  let index = clamped - 1;
  // Skip trailing characters that could sit between us and a terminator is not
  // needed here; we scan every character and test terminators directly.
  while (index >= 0) {
    const char = text[index];
    if (SENTENCE_TERMINATORS.has(char) && !isAbbreviationPeriod(text, index)) {
      // Found the terminator of the previous sentence. Advance past it and any
      // trailing quotes/brackets and whitespace to reach the next sentence.
      let next = index + 1;
      while (next < text.length && SENTENCE_TRAILERS.has(text[next])) next += 1;
      while (next < text.length && /\s/.test(text[next])) next += 1;
      return next;
    }
    index -= 1;
  }
  return 0;
}

// Seconds to play when a student hears one word on its own. Human timings carry the word's end
// (plus a short tail, up to the next word, so final consonants aren't clipped). Polly marks are
// word starts only, so the clip stops leadMs before the next word starts: the next word's first
// sound and the browser's pause latency otherwise leak in ("garden ju-", QA-1). It never gets
// shorter than minMs. Capped so a sentence or paragraph pause after the word isn't played as part of it.
export function findWordRange(timings, tokenId, maxMs = 1500, tailMs = 80, leadMs = 60, minMs = 120) {
  const index = timings.findIndex(item => item.tokenId === tokenId);
  if (index < 0) return null;
  const { startMs, endMs } = timings[index];
  const nextMs = timings[index + 1]?.startMs;
  let end = startMs + maxMs;
  if (Number.isFinite(endMs) && endMs > startMs) end = endMs + Math.min(tailMs, Number.isFinite(nextMs) ? Math.max(0, nextMs - endMs) : tailMs);
  else if (Number.isFinite(nextMs) && nextMs > startMs) end = Math.max(nextMs - leadMs, Math.min(nextMs, startMs + minMs));
  return { start: startMs / 1000, end: Math.min(end, startMs + maxMs) / 1000 };
}
