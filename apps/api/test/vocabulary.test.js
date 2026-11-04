import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import { parseWikitext, cleanWiki, createDictionary, mapOfficialWords, USER_AGENT } from '../vocabulary.js';
import { vocabularyRoutes } from '../vocabularyRoutes.js';
const json = (data, status = 200) => new Response(JSON.stringify(data), { status });
test('parses learner senses, headings, labels and links without examples', () => {
  assert.deepEqual(parseWikitext("==Noun==\n# {{countable}} A [[seed|young seed]] with '''leaves'''.\n#: Example\n#* quotation\n===Verb===\n# To ''grow''."), { base: null, senses: [{ partOfSpeech: 'Noun', definition: 'A young seed with leaves.' }, { partOfSpeech: 'Verb', definition: 'To grow.' }] });
  assert.equal(parseWikitext('==Verb==\n# {{past tense and participle of|walk}}').base, 'walk');
  assert.equal(cleanWiki('[[cold]] {{uncountable}}'), 'cold');
});
test('follows an inflection once, identifies requests and shares cached lookups', async () => {
  const calls = [];
  const lookup = createDictionary(async (url, options) => {
    calls.push(url); assert.equal(options.headers['User-Agent'], USER_AGENT);
    return json({ parse: { wikitext: url.includes('page=seedlings') ? '==Noun==\n# {{plural of|seedling}}' : '==Noun==\n# A young plant.' } });
  });
  const [a,b] = await Promise.all([lookup('seedlings'), lookup('Seedlings')]);
  assert.equal(a.lemma, 'seedling'); assert.deepEqual(a,b); assert.equal(calls.length, 2);
});
test('uses English fallback, strips HTML, and reports absent words', async () => {
  const lookup = createDictionary(async url => url.includes('simple.') ? json({ error: {} }) : url.endsWith('/mulch') ? json({ en: [{ partOfSpeech: 'Noun', definitions: [{ definition: 'A <b>cover</b> &amp; layer.' }] }] }) : json({},404));
  assert.equal((await lookup('mulch')).senses[0].definition, 'A cover & layer.');
  assert.equal((await lookup('brrr')).senses.length, 0);
});
test('retries errors instead of permanently caching outages', async () => {
  let calls = 0;
  const lookup = createDictionary(async () => { if (++calls === 1) return json({},429); return json({parse:{wikitext:'==Noun==\n# A plant.'}}); });
  await assert.rejects(lookup('plant')); assert.equal((await lookup('plant')).senses.length,1);
});
const passage = { paragraphs: [{id:'p1',text:'Enjoy nature & nature.'}], tokens:[{id:'a',paragraphId:'p1',start:6,end:12},{id:'b',paragraphId:'p1',start:15,end:21}] };
const product = { content: '<figure><figcaption>Not narrated</figcaption></figure><p>Enjoy <span data-vocab-sense-id="1">nature</span> &amp; <span data-vocab-sense-id="1">nature</span>.</p>', vocab:{support:{ word_list:['nature'], get senses(){throw Error('licensed field accessed');} }} };
test('maps repeated official spans to token offsets, skips captions and decodes entities',()=> {
  assert.deepEqual(mapOfficialWords(product,passage),[{word:'nature',occurrences:[{tokenIds:['a']},{tokenIds:['b']}]}]);
  assert.deepEqual(mapOfficialWords(product,{...passage,paragraphs:[{id:'p1',text:'Changed text.'}]}),[]);
});
test('API resolves generated manifests and validates inputs; demo makes no upstream request', async t => {
  const app = express(); let calls=0;
  const uuid='2b781dab-4521-40d2-a9b6-ad5f2bb0ba98';
  vocabularyRoutes(app, async url => { calls++; return json(url.endsWith('current.json') ? {manifestUrl:'/generated/park/v1/manifest.json'} : url.endsWith('manifest.json') ? {...passage,source:{uuid}} : {content:product.content,vocab:{support:{word_list:['nature']}}}); });
  const server=app.listen(0,'127.0.0.1'); await new Promise(resolve=>server.once('listening',resolve)); t.after(()=>server.close());
  const get=path=>fetch(`http://127.0.0.1:${server.address().port}${path}`);
  assert.deepEqual(await (await get('/api/passages/demo/vocabulary')).json(),[]); assert.equal(calls,0);
  assert.equal((await (await get('/api/passages/park/vocabulary')).json())[0].word,'nature');
  await get('/api/passages/park/vocabulary'); assert.equal(calls,3);
  assert.equal((await get('/api/define/123')).status,400);
});
