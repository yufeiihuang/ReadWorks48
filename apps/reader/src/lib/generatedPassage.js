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

// Returns null when this passage has not been generated. Throws if its published files are broken.
export async function loadGeneratedPassage(id, pinnedUrl, fetcher = (...args) => fetch(...args)) {
  if (pinnedUrl) return fetchManifest(pinnedUrl, fetcher);
  if (!VALID_ID.test(id)) return null;
  const pointer = await fetcher(`/generated/${id}/current.json`);
  if (!pointer.ok) return null;
  const { manifestUrl } = await pointer.json();
  if (typeof manifestUrl !== 'string' || !manifestUrl.startsWith(`/generated/${id}/`)) throw new Error('Invalid passage pointer');
  return fetchManifest(manifestUrl, fetcher);
}
