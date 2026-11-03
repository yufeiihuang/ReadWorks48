import test from 'node:test';
import assert from 'node:assert/strict';
import { findWordRange } from '../src/lib/wordTiming.js';
const polly = [{tokenId:'w0',startMs:125},{tokenId:'w1',startMs:450},{tokenId:'w2',startMs:3000}];
const human = [{tokenId:'w0',startMs:3510,endMs:3700},{tokenId:'w1',startMs:3700,endMs:3860},{tokenId:'w2',startMs:4300,endMs:4600}];
test('Polly words end where the next word starts',()=>{
  assert.deepEqual(findWordRange(polly,'w0'),{start:.125,end:.45});
});
test('a long pause after a word is capped',()=>{
  assert.deepEqual(findWordRange(polly,'w1'),{start:.45,end:1.95});
  assert.deepEqual(findWordRange(polly,'w2'),{start:3,end:4.5});
});
test('human words use their recorded end plus a short tail that never reaches the next word',()=>{
  assert.deepEqual(findWordRange(human,'w0'),{start:3.51,end:3.7});
  assert.deepEqual(findWordRange(human,'w1'),{start:3.7,end:3.94});
  assert.deepEqual(findWordRange(human,'w2'),{start:4.3,end:4.68});
});
test('unknown words have no range',()=>{
  assert.equal(findWordRange(polly,'missing'),null);
  assert.equal(findWordRange([],'w0'),null);
});
