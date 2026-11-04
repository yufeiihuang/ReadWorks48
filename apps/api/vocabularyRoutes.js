import { createDictionary, mapOfficialWords } from './vocabulary.js';
import { isReadWorksId, toReaderPassage } from './readworks.js';
const ORIGIN = 'https://d1381qenwhm2qw.cloudfront.net';
export function vocabularyRoutes(app, fetcher = fetch) {
  const define = createDictionary(fetcher);
  app.get('/api/define/:word', async (req, res, next) => {
    if (!/^[\p{L}][\p{L}'’-]{0,79}$/u.test(req.params.word)) return res.status(400).json({ error: 'Invalid word' });
    try { res.set('Cache-Control', 'public, max-age=86400').json(await define(req.params.word)); } catch (error) { next(error); }
  });
  const cache = new Map();
  app.get('/api/passages/:id/vocabulary', async (req, res, next) => {
    const { id } = req.params;
    if (!/^[\w-]{1,100}$/.test(id)) return res.status(400).json({ error: 'Invalid passage' });
    try {
      if (cache.has(id)) return res.set('Cache-Control', 'public, max-age=3600').json(cache.get(id));
      let passage, uuid = isReadWorksId(id) ? id : null;
      const get = async url => {
        const response = await fetcher(url, { signal: AbortSignal.timeout(8000) });
        if ([403, 404].includes(response.status)) return null;
        if (!response.ok) throw new Error('Vocabulary source unavailable');
        return response.json();
      };
      if (!uuid && id !== 'demo') {
        const pointer = await get(`${ORIGIN}/generated/${id}/current.json`);
        if (pointer?.manifestUrl?.startsWith(`/generated/${id}/`) && !pointer.manifestUrl.includes('..')) passage = await get(ORIGIN + pointer.manifestUrl);
        uuid = passage?.source?.uuid;
      }
      if (!uuid || !isReadWorksId(uuid)) return res.json([]);
      const product = await get(`https://s3.us-west-2.amazonaws.com/readworks-media-qa/data/p/${uuid}`);
      if (!product) return res.json([]);
      passage ||= toReaderPassage(product);
      if (!passage) return res.json([]);
      // Unrecorded passages have no tokens yet; match the reader's fallback tokenizer.
      if (!passage.tokens?.length) passage.tokens = passage.paragraphs.flatMap(p => [...p.text.matchAll(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu)].map(m => ({ id: `${p.id}-${m.index}`, paragraphId: p.id, text: m[0], start: m.index, end: m.index + m[0].length })));
      const result = mapOfficialWords(product, passage);
      if (cache.size >= 100) cache.delete(cache.keys().next().value);
      cache.set(id, result);
      res.set('Cache-Control', 'public, max-age=3600').json(result);
    } catch (error) { next(error); }
  });
}
