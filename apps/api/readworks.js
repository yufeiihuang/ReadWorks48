// Reads public ReadWorks product JSON so a passage can be displayed before its audio exists.
const PRODUCT_URL = 'https://s3.us-west-2.amazonaws.com/readworks-media-qa/data/p/';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const LANGUAGES = { EN: 'en-US' };

export const isReadWorksId = id => UUID.test(id);

// Returns only display fields, or null for passages this reader doesn't support.
export function toReaderPassage(product) {
  const language = LANGUAGES[String(product?.lang).toUpperCase()];
  if (!language || product.features?.includes('ebook') || !product.title || !product.text) return null;
  const lines = product.text.split('\n').map(line => line.trim()).filter(Boolean);
  return {
    schemaVersion: 1,
    id: product.uuid,
    revision: 1,
    title: product.title,
    language,
    source: { provider: 'readworks', uuid: product.uuid, au: product.au },
    gradeId: product.canonical_grade ?? null,
    paragraphs: lines.map((text, index) => ({ id: `p${index + 1}`, text })),
    tokens: [],
    audio: null,
    timings: [],
    generation: { status: 'not_generated', engine: 'neural', voice: null, textHash: null },
  };
}

export async function fetchReadWorksPassage(id, fetcher = fetch) {
  const response = await fetcher(PRODUCT_URL + id, { signal: AbortSignal.timeout(8000) });
  // The source bucket answers 403 for an object that doesn't exist.
  if (response.status === 403 || response.status === 404) return null;
  if (!response.ok) throw new Error(`ReadWorks passage request failed: ${response.status}`);
  return toReaderPassage(await response.json());
}
