// Index of the word a key moves the keyboard word cursor to, or null when the key doesn't move it.
export function nextWordIndex(key, index, count) {
  if (!(count > 0)) return null;
  const next = key === 'ArrowRight' ? index + 1 : key === 'ArrowLeft' ? index - 1 : key === 'Home' ? 0 : key === 'End' ? count - 1 : null;
  return next === null ? null : Math.max(0, Math.min(count - 1, next));
}
