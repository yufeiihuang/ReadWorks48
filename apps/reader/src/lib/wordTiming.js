// Timing arrays are ordered word-start timestamps from the matching recording.
export function findActiveToken(timings, seconds, duration = 0) {
  if (!Number.isFinite(seconds) || seconds < 0 || (duration > 0 && seconds >= duration)) return null;
  let low = 0, high = timings.length - 1, result = null;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (timings[middle].startMs <= seconds * 1000) { result = timings[middle].tokenId; low = middle + 1; }
    else high = middle - 1;
  }
  return result;
}
