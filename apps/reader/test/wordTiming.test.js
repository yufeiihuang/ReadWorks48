import test from 'node:test';
import assert from 'node:assert/strict';
import { findActiveToken } from '../src/lib/wordTiming.js';
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
