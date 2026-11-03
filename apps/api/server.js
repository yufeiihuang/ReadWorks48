import express from 'express';
import passage from '../../shared/fixtures/demo.json' with { type: 'json' };
import { fetchReadWorksPassage, isReadWorksId } from './readworks.js';
const app = express();
app.get('/api/health', (_req, res) => res.json({ status: 'ok' }));
app.get('/api/passages', async (_req, res, next) => {
  try { res.json([{ id: passage.id, title: passage.title }]); } catch (error) { next(error); }
});
app.get('/api/passages/:id', async (req, res, next) => {
  try {
    const { id } = req.params;
    const found = id === 'demo' ? passage : isReadWorksId(id) ? await fetchReadWorksPassage(id) : null;
    if (!found) return res.status(404).json({ error: 'Passage not found' });
    res.json(found);
  } catch (error) { next(error); }
});
app.use((error, _req, res, _next) => { console.error(error); res.status(500).json({ error: 'Unable to load passage' }); });
export default app;
