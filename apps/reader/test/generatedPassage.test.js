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
  const files = fetcherFor({ '/generated/demo/pin/manifest.json': manifest });
  const fetcher = async url => url.endsWith('/current.json') ? assert.fail('a pinned demo must not consult current.json') : files(url);
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

const pin = '/generated/abc/old/manifest.json';
test('latest preview prefers a newly published pointer over the pin, and never edge-caches the pointer', async () => {
  const latest = { ...manifest, assetVersion: 'human-latest' };
  const files = fetcherFor({ '/generated/abc/current.json': { manifestUrl: '/generated/abc/new/manifest.json' }, '/generated/abc/new/manifest.json': latest, [pin]: manifest });
  const pointerOptions = [];
  const fetcher = async (url, options) => { if (url.endsWith('/current.json')) pointerOptions.push(options); return files(url); };
  assert.deepEqual(await loadLatestGeneratedPassage('abc', pin, fetcher), latest);
  assert.equal(pointerOptions[0].cache, 'no-store');
  assert.ok(pointerOptions[0].signal instanceof AbortSignal);
});
test('any pointer problem serves the pin instead of dropping the audio', async () => {
  const withPin = pointer => async url => url === pin ? { ok: true, json: async () => manifest } : pointer(url);
  const problems = {
    absent: async () => ({ ok: false, status: 403 }),
    'server error': async () => ({ ok: false, status: 502 }),
    'network error': async () => { throw new TypeError('Failed to fetch'); },
    'non-JSON body': async () => ({ ok: true, json: async () => { throw new SyntaxError('Unexpected token <'); } }),
    'pointer outside passage': async () => ({ ok: true, json: async () => ({ manifestUrl: 'https://example.com/x.json' }) }),
    'missing manifest': async url => url.endsWith('/current.json') ? { ok: true, json: async () => ({ manifestUrl: '/generated/abc/gone/manifest.json' }) } : { ok: false, status: 403 },
  };
  for (const [problem, pointer] of Object.entries(problems)) {
    assert.deepEqual(await loadLatestGeneratedPassage('abc', pin, withPin(pointer)), manifest, problem);
  }
});
test('a hung pointer times out: the pin is served, and without a pin the reader is told', async () => {
  let aborted = false;
  const hang = async (url, options) => url === pin ? { ok: true, json: async () => manifest }
    : new Promise(() => options.signal.addEventListener('abort', () => { aborted = true; }));
  assert.deepEqual(await loadLatestGeneratedPassage('abc', pin, hang, 20), manifest);
  assert.ok(aborted, 'the stalled pointer request is aborted');
  await assert.rejects(loadLatestGeneratedPassage('abc', undefined, hang, 20), /timed out/);
});
test('without a pin, server failures still surface instead of reading as ungenerated', async () => {
  await assert.rejects(loadLatestGeneratedPassage('abc', undefined, async () => ({ ok: false, status: 500 })), /pointer unavailable/);
});
