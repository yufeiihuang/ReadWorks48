import test from 'node:test';
import assert from 'node:assert/strict';
import { findActiveToken, findLastStartedToken } from '../src/lib/wordTiming.js';
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

test('the last started word is held through the pause after a human word ends',()=>{
  const human = [{tokenId:'park',startMs:1000,endMs:1300},{tokenId:'next',startMs:2000,endMs:2200}];
  assert.equal(findActiveToken(human,1.5),null);
  assert.equal(findLastStartedToken(human,1.5),'park');
  assert.equal(findLastStartedToken(human,.5),null);
  assert.equal(findLastStartedToken(human,2.1),'next');
  assert.equal(findLastStartedToken(human,3,3),null);
});
