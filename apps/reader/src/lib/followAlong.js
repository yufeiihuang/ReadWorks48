// Rects are viewport coordinates (getBoundingClientRect). topInset is the space covered by the
// sticky console, so a word under the console counts as out of view.

// Scroll delta (px) that keeps the spoken word in a comfortable reading band, or 0 when it already is.
// Words below 75% of the visible area jump back up to 30%, so the page moves in a few calm steps
// per screen instead of on every line.
export function followScrollDelta(word, { height, topInset = 0 }) {
  const visible = height - topInset;
  if (!(visible > 0)) return 0;
  const bandTop = topInset + visible * 0.15, bandBottom = topInset + visible * 0.75;
  if (word.top >= bandTop && word.bottom <= bandBottom) return 0;
  return Math.round(word.top - (topInset + visible * 0.3));
}

// Where the spoken word is relative to what the student can see: 'above', 'below', or 'visible'.
// A word cut off by the console or the screen edge counts as out of view.
export function wordPlacement(word, { height, topInset = 0 }) {
  if (word.top < topInset) return 'above';
  if (word.bottom > height) return 'below';
  return 'visible';
}

const scrollKeys = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']);
// True when a keypress will scroll the page rather than operate a control.
export function isManualScrollKey(event) {
  if (event.defaultPrevented || !scrollKeys.has(event.key)) return false;
  const tag = event.target?.tagName;
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || event.target?.isContentEditable) return false;
  return !(event.key === ' ' && (tag === 'BUTTON' || tag === 'A'));
}
