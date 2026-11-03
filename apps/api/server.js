import express from 'express';
import passage from '../../shared/fixtures/demo.json' with { type: 'json' };
const app = express();
app.get('/api/health', (_req, res) => res.json({ status: 'ok' }));
app.get('/api/passages', async (_req, res, next) => {
  try { res.json([{ id: passage.id, title: passage.title }]); } catch (error) { next(error); }
});
app.get('/api/passages/:id', async (req, res, next) => {
  if (req.params.id !== 'demo') return res.status(404).json({ error: 'Passage not found' });
  try { res.json(passage); } catch (error) { next(error); }
});
app.use((error, _req, res, _next) => { console.error(error); res.status(500).json({ error: 'Unable to load passage' }); });
export default app;
