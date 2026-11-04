import test from 'node:test';
import assert from 'node:assert/strict';
import app from '../server.js';

const UUID = '2b781dab-4521-40d2-a9b6-ad5f2bb0ba98';
const product = {
  uuid: UUID, title: "Let's Meet", lang: 'EN', au: 'audio_id', features: ['au'], canonical_grade: 17,
  text: 'First paragraph.\n\n  Second paragraph.\n',
  answerMapA: { 1: { 2: 3 } }, questionSets: { 1: {} },
};

// Answers ReadWorks requests with a fake and sends requests to the local server for real.
async function request(t, id, source) {
  const realFetch = globalThis.fetch;
  t.mock.method(globalThis, 'fetch', (url, options) => (String(url).includes('readworks-media-qa') ? source(url) : realFetch(url, options)));
  const server = await new Promise(resolve => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  t.after(() => server.close());
  const response = await fetch(`http://127.0.0.1:${server.address().port}/api/passages/${id}`);
  return { status: response.status, body: await response.json() };
}
const answer = (body, status = 200) => async () => new Response(JSON.stringify(body), { status });
const silenceErrors = t => t.mock.method(console, 'error', () => {});

test('returns an ungenerated ReadWorks passage with display fields only', async t => {
  const { status, body } = await request(t, UUID, answer(product));
  assert.equal(status, 200);
  assert.deepEqual(body.paragraphs, [{ id: 'p1', text: 'First paragraph.' }, { id: 'p2', text: 'Second paragraph.' }]);
  assert.equal(body.id, UUID);
  assert.equal(body.language, 'en-US');
  assert.equal(body.audio, null);
  assert.equal(body.gradeId, 17);
  assert.deepEqual(body.tokens, []);
  assert.equal(body.generation.status, 'not_generated');
  assert.equal(body.answerMapA, undefined);
  assert.equal(body.questionSets, undefined);
});
test('reports a passage missing from the source as not found', async t => {
  const { status } = await request(t, UUID, answer({}, 403));
  assert.equal(status, 404);
});
test('reports ebook-style and unsupported-language passages as not found', async t => {
  assert.equal((await request(t, UUID, answer({ ...product, features: ['ebook'] }))).status, 404);
  assert.equal((await request(t, UUID, answer({ ...product, lang: 'ES' }))).status, 404);
});
test('reports a source outage as a server error', async t => {
  silenceErrors(t);
  assert.equal((await request(t, UUID, answer({}, 500))).status, 500);
  assert.equal((await request(t, UUID, async () => { throw new Error('offline'); })).status, 500);
});
test('never contacts the source for other ids and still serves the demo', async t => {
  const source = () => assert.fail('must not fetch');
  assert.equal((await request(t, 'missing', source)).status, 404);
  assert.equal((await request(t, 'demo', source)).body.id, 'demo');
});
