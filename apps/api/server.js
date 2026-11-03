import express from 'express';
import { readFile } from 'node:fs/promises';
const app = express();
const fixtureUrl = new URL('../../shared/fixtures/demo.json', import.meta.url);
app.get('/api/health', (_req, res) => res.json({ status: 'ok' }));
app.get('/api/passages', async (_req, res, next) => {
  try { const passage = JSON.parse(await readFile(fixtureUrl, 'utf8')); res.json([{ id: passage.id, title: passage.title }]); } catch (error) { next(error); }
});
app.get('/api/passages/:id', async (req, res, next) => {
  if (req.params.id !== 'demo') return res.status(404).json({ error: 'Passage not found' });
  try { res.json(JSON.parse(await readFile(fixtureUrl, 'utf8'))); } catch (error) { next(error); }
});
app.use((error, _req, res, _next) => { console.error(error); res.status(500).json({ error: 'Unable to load passage' }); });
app.listen(Number(process.env.PORT || 3001), '127.0.0.1', () => console.log('SoundWorks API ready on port ' + (process.env.PORT || 3001)));
