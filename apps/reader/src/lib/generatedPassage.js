// current.json has a permanent address and names the newest versioned manifest for a passage.
const VALID_ID = /^[A-Za-z0-9_-]+$/;

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

// Explicit dev previews remain pinned. Normal reader loads follow the mutable
// completion pointer, falling back to a demo pin only when no pointer exists yet.
export async function loadGeneratedPassage(id, pinnedUrl, fetcher = (...args) => fetch(...args)) {
  if (pinnedUrl) return fetchManifest(pinnedUrl, fetcher);
  return loadLatestGeneratedPassage(id, undefined, fetcher);
}

export async function loadLatestGeneratedPassage(id, fallbackUrl, fetcher = (...args) => fetch(...args)) {
  if (!VALID_ID.test(id)) return null;
  const pointer = await fetcher(`/generated/${id}/current.json`, { cache: 'no-store' });
  if (!pointer.ok) {
    // Private S3 origins return 403 for an absent key when ListBucket is withheld.
    if (![403, 404].includes(pointer.status)) throw new Error('Generated passage pointer unavailable');
    return fallbackUrl ? fetchManifest(fallbackUrl, fetcher) : null;
  }
  const { manifestUrl } = await pointer.json();
  if (typeof manifestUrl !== 'string' || !manifestUrl.startsWith(`/generated/${id}/`)) throw new Error('Invalid passage pointer');
  return fetchManifest(manifestUrl, fetcher);
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
