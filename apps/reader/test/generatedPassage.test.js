import test from 'node:test';
import assert from 'node:assert/strict';
import { loadGeneratedPassage } from '../src/lib/generatedPassage.js';
const manifest = { audio: { url: '/generated/abc/v1/audio.wav' }, tokens: [{ id: 'w0' }], timings: [{ tokenId: 'w0', startMs: 0 }] };
const fetcherFor = files => async url => url in files ? { ok: true, json: async () => files[url] } : { ok: false, status: 403 };
test('follows current.json to the newest manifest', async () => {
  const fetcher = fetcherFor({ '/generated/abc/current.json': { manifestUrl: '/generated/abc/v1/manifest.json' }, '/generated/abc/v1/manifest.json': manifest });
  assert.deepEqual(await loadGeneratedPassage('abc', undefined, fetcher), manifest);
});
test('uses a pinned manifest without looking for a pointer', async () => {
  const fetcher = fetcherFor({ '/generated/demo/pin/manifest.json': manifest });
  assert.deepEqual(await loadGeneratedPassage('demo', '/generated/demo/pin/manifest.json', fetcher), manifest);
});
test('reports an ungenerated passage and rejects unsafe ids without fetching', async () => {
  assert.equal(await loadGeneratedPassage('abc', undefined, fetcherFor({})), null);
  assert.equal(await loadGeneratedPassage('../other', undefined, () => assert.fail('must not fetch')), null);
});
test('rejects pointers outside the passage and incomplete manifests', async () => {
  await assert.rejects(loadGeneratedPassage('abc', undefined, fetcherFor({ '/generated/abc/current.json': { manifestUrl: 'https://example.com/x.json' } })), /Invalid/);
  const fetcher = fetcherFor({ '/generated/abc/current.json': { manifestUrl: '/generated/abc/v1/manifest.json' }, '/generated/abc/v1/manifest.json': { ...manifest, timings: [] } });
  await assert.rejects(loadGeneratedPassage('abc', undefined, fetcher), /Incomplete/);
});
