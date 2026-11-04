import test from 'node:test';
import assert from 'node:assert/strict';
import { loadGeneratedPassage, loadLatestGeneratedPassage, wordClipUrl } from '../src/lib/generatedPassage.js';
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
test('builds word clip URLs only from a well-formed word audio section', () => {
  const withClips = { ...manifest, wordAudio: { baseUrl: '/generated/words/Stephen/', format: 'mp3', clips: { w0: 'a'.repeat(20) } } };
  assert.equal(wordClipUrl(withClips, 'w0'), `/generated/words/Stephen/${'a'.repeat(20)}.mp3`);
  assert.equal(wordClipUrl(withClips, 'w9'), null);
  assert.equal(wordClipUrl(manifest, 'w0'), null);
  assert.equal(wordClipUrl({ wordAudio: { ...withClips.wordAudio, baseUrl: 'https://example.com/' } }, 'w0'), null);
  assert.equal(wordClipUrl({ wordAudio: { ...withClips.wordAudio, clips: { w0: '../x' } } }, 'w0'), null);
});

test('normal reader prefers a newly published pointer over an old demo pin', async () => {
  const latest = { ...manifest, assetVersion: 'human-latest' };
  const fetcher = fetcherFor({ '/generated/abc/current.json': { manifestUrl: '/generated/abc/new/manifest.json' }, '/generated/abc/new/manifest.json': latest, '/generated/abc/old/manifest.json': manifest });
  assert.deepEqual(await loadLatestGeneratedPassage('abc', '/generated/abc/old/manifest.json', fetcher), latest);
});
test('absent pointer uses the demo fallback, but server failures do not silently serve an old recording', async () => {
  assert.deepEqual(await loadLatestGeneratedPassage('abc', '/generated/abc/old/manifest.json', fetcherFor({ '/generated/abc/old/manifest.json': manifest })), manifest);
  await assert.rejects(loadLatestGeneratedPassage('abc', '/generated/abc/old/manifest.json', async () => ({ ok: false, status: 500 })), /pointer unavailable/);
});
