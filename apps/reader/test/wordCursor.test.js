import test from 'node:test';
import assert from 'node:assert/strict';
import { nextWordIndex } from '../src/lib/wordCursor.js';
test('arrow keys move one word and stop at the passage edges',()=>{
  assert.equal(nextWordIndex('ArrowRight',3,10),4);
  assert.equal(nextWordIndex('ArrowLeft',3,10),2);
  assert.equal(nextWordIndex('ArrowRight',9,10),9);
  assert.equal(nextWordIndex('ArrowLeft',0,10),0);
});
test('Home and End jump to the first and last word',()=>{
  assert.equal(nextWordIndex('Home',6,10),0);
  assert.equal(nextWordIndex('End',2,10),9);
});
test('other keys and empty passages leave the cursor alone',()=>{
  assert.equal(nextWordIndex('ArrowDown',3,10),null);
  assert.equal(nextWordIndex('Enter',3,10),null);
  assert.equal(nextWordIndex('ArrowRight',0,0),null);
});
