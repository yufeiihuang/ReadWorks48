// current.json has a permanent address and names the newest versioned manifest for a passage.
const VALID_ID = /^[A-Za-z0-9_-]+$/;
// current.json is never cached at the edge, so a slow origin must not hold the page on "Loading".
export const POINTER_TIMEOUT_MS = 4000;

export function isReadyManifest(manifest) {
  return Boolean(manifest?.audio?.url && manifest.tokens?.length && manifest.timings?.length === manifest.tokens.length);
}

async function fetchManifest(url, fetcher) {
  const response = await fetcher(url);
  if (!response.ok) throw new Error('Generated passage unavailable');
  const manifest = await response.json();
  if (!isReadyManifest(manifest)) throw new Error('Incomplete generated passage');
  return manifest;
}

// A pinned (reviewed) manifest wins, so publishing a pointer cannot change a demo passage.
// Passages without a pin follow the mutable completion pointer.
export async function loadGeneratedPassage(id, pinnedUrl, fetcher = (...args) => fetch(...args)) {
  if (pinnedUrl) return fetchManifest(pinnedUrl, fetcher);
  return loadLatestGeneratedPassage(id, undefined, fetcher);
}

// Follows current.json. When a pin is supplied, any pointer problem (absent, server error,
// timeout, malformed, or naming a broken manifest) serves the pin instead of dropping the audio.
export async function loadLatestGeneratedPassage(id, fallbackUrl, fetcher = (...args) => fetch(...args), timeoutMs = POINTER_TIMEOUT_MS) {
  if (!VALID_ID.test(id)) return null;
  try {
    const pointer = await readPointer(id, fetcher, timeoutMs);
    if (pointer) {
      const { manifestUrl } = pointer;
      if (typeof manifestUrl !== 'string' || !manifestUrl.startsWith(`/generated/${id}/`)) throw new Error('Invalid passage pointer');
      return await fetchManifest(manifestUrl, fetcher);
    }
  } catch (error) {
    if (!fallbackUrl) throw error;
  }
  return fallbackUrl ? fetchManifest(fallbackUrl, fetcher) : null;
}

// Resolves to the parsed pointer, or null when none has been published.
async function readPointer(id, fetcher, timeoutMs) {
  const controller = new AbortController();
  let timer;
  const timedOut = new Promise((_, reject) => {
    timer = setTimeout(() => { controller.abort(); reject(new Error('Generated passage pointer timed out')); }, timeoutMs);
  });
  const read = (async () => {
    const response = await fetcher(`/generated/${id}/current.json`, { cache: 'no-store', signal: controller.signal });
    if (!response.ok) {
      // Private S3 origins return 403 for an absent key when ListBucket is withheld.
      if ([403, 404].includes(response.status)) return null;
      throw new Error('Generated passage pointer unavailable');
    }
    return response.json();
  })();
  try {
    return await Promise.race([read, timedOut]);
  } finally {
    clearTimeout(timer);
  }
}

// URL of the separately recorded clip for one word, or null when the passage has none
// (older recordings and human narration fall back to slicing the passage audio).
export function wordClipUrl(manifest, tokenId) {
  const words = manifest?.wordAudio;
  const id = words?.clips?.[tokenId];
  if (typeof words?.baseUrl !== 'string' || !words.baseUrl.startsWith('/generated/words/')) return null;
  if (typeof id !== 'string' || !/^[a-f0-9]{20}$/.test(id)) return null;
  return `${words.baseUrl}${id}.mp3`;
}
