import test from 'node:test';
import assert from 'node:assert/strict';
import { findActiveToken, findSentenceStartSeconds } from '../src/lib/wordTiming.js';
const timings = [{tokenId:'first-maya',startMs:100},{tokenId:'walked',startMs:500},{tokenId:'second-maya',startMs:1500}];
test('selects exact boundaries and unique repeated-word identities',()=>{
  assert.equal(findActiveToken(timings,.099),null);
  assert.equal(findActiveToken(timings,.1),'first-maya');
  assert.equal(findActiveToken(timings,.5),'walked');
  assert.equal(findActiveToken(timings,1.5),'second-maya');
});
test('recalculates correctly after backward seeking without cached progress',()=>{
  assert.equal(findActiveToken(timings,1.8),'second-maya');
  assert.equal(findActiveToken(timings,.2),'first-maya');
});
test('clears on completion and handles empty/invalid times',()=>{
  assert.equal(findActiveToken(timings,2,2),null);
  assert.equal(findActiveToken([],1),null);
  assert.equal(findActiveToken(timings,NaN),null);
});

test('human timing gaps clear the highlight instead of carrying it over uncertain words',()=>{
  const human=[{tokenId:'first',startMs:100,endMs:300},{tokenId:'next',startMs:1000,endMs:1400}];
  assert.equal(findActiveToken(human,.2),'first');
  assert.equal(findActiveToken(human,.4),null);
  assert.equal(findActiveToken(human,1.1),'next');
});

test('sentence replay in a human timing gap stays in the current sentence',()=>{
  const paragraphs=[{id:'p',text:'First ends. Second starts.'}];
  const tokens=[{id:'a',paragraphId:'p',start:0,end:5},{id:'b',paragraphId:'p',start:6,end:10},{id:'c',paragraphId:'p',start:12,end:18},{id:'d',paragraphId:'p',start:19,end:25}];
  const times=[{tokenId:'a',startMs:0,endMs:400},{tokenId:'b',startMs:500,endMs:800},{tokenId:'c',startMs:1000,endMs:1300},{tokenId:'d',startMs:1500,endMs:1900}];
  assert.equal(findActiveToken(times,1.4),null);
  assert.equal(findSentenceStartSeconds(paragraphs,tokens,times,1.4),1);
});
