import test from 'node:test';
import assert from 'node:assert/strict';
import { followScrollDelta, isManualScrollKey, wordPlacement } from '../src/lib/followAlong.js';
const screen = { height: 800, topInset: 100 }; // visible area 100–800; reading band 205–625; target 310
const word = (top, height = 24) => ({ top, bottom: top + height });
test('leaves words inside the reading band alone',()=>{
  assert.equal(followScrollDelta(word(205),screen),0);
  assert.equal(followScrollDelta(word(400),screen),0);
  assert.equal(followScrollDelta(word(601),screen),0);
});
test('scrolls down when the word nears the bottom and up when it is above the band',()=>{
  assert.equal(followScrollDelta(word(700),screen),390);
  assert.equal(followScrollDelta(word(2400),screen),2090);
  assert.equal(followScrollDelta(word(150),screen),-160);
  assert.equal(followScrollDelta(word(-900),screen),-1210);
});
test('treats words hidden under the sticky console as out of view',()=>{
  assert.equal(wordPlacement(word(50),screen),'above');
  assert.equal(wordPlacement(word(90),screen),'above');
  assert.equal(wordPlacement(word(100),screen),'visible');
  assert.equal(wordPlacement(word(400),screen),'visible');
  assert.equal(wordPlacement(word(776),screen),'visible');
  assert.equal(wordPlacement(word(790),screen),'below');
  assert.equal(wordPlacement(word(800),screen),'below');
  assert.equal(followScrollDelta(word(400),{height:0,topInset:0}),0);
});
test('recognizes page-scrolling keys but not keys that operate controls',()=>{
  const key = (key, tagName = 'BODY', extra = {}) => ({ key, target: { tagName }, defaultPrevented: false, ...extra });
  assert.equal(isManualScrollKey(key('PageDown')),true);
  assert.equal(isManualScrollKey(key(' ')),true);
  assert.equal(isManualScrollKey(key('ArrowDown','BUTTON')),true);
  assert.equal(isManualScrollKey(key(' ','BUTTON')),false);
  assert.equal(isManualScrollKey(key('ArrowDown','INPUT')),false);
  assert.equal(isManualScrollKey(key('ArrowDown','SELECT')),false);
  assert.equal(isManualScrollKey(key('End','BUTTON',{defaultPrevented:true})),false);
  assert.equal(isManualScrollKey(key('a')),false);
});
