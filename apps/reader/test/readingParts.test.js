import test from 'node:test';
import assert from 'node:assert/strict';
import { crossedPartStart, partIndexAt, partStarts, splitSentences } from '../src/lib/readingParts.js';
const tokens = [
  {id:'w0',paragraphId:'p1'},{id:'w1',paragraphId:'p1'},
  {id:'w2',paragraphId:'p2'},{id:'w3',paragraphId:'p2'},
  {id:'w4',paragraphId:'p3'},
  {id:'w5',paragraphId:'p4'},
];
const timings = [
  {tokenId:'w0',startMs:3500},{tokenId:'w1',startMs:3900},
  {tokenId:'w2',startMs:9000},{tokenId:'w3',startMs:9400},
  // p3's only word was not matched in the recording
  {tokenId:'w5',startMs:15000},
];
const parts = partStarts(tokens,timings);
test('each paragraph with a timed word becomes a part starting at its first word',()=>{
  assert.deepEqual(parts,[{paragraphId:'p1',start:3.5},{paragraphId:'p2',start:9},{paragraphId:'p4',start:15}]);
  assert.deepEqual(partStarts([],[]),[]);
});
test('detects reaching the next part only while moving forward across its start',()=>{
  assert.equal(crossedPartStart(parts,8.95,9.01),1);
  assert.equal(crossedPartStart(parts,8.9,9),1);
  assert.equal(crossedPartStart(parts,9,9.2),-1);
  assert.equal(crossedPartStart(parts,14.9,15.1),2);
  assert.equal(crossedPartStart(parts,10,9.5),-1);
});
test('starting the passage does not count as finishing a part',()=>{
  assert.equal(crossedPartStart(parts,0,3.6),-1);
});
test('finds the part playing at a time',()=>{
  assert.equal(partIndexAt(parts,0),0);
  assert.equal(partIndexAt(parts,4),0);
  assert.equal(partIndexAt(parts,9),1);
  assert.equal(partIndexAt(parts,99),2);
});
const sentenceText = 'Maya walked. “Brrr! It is cold,” she said.';
const sentenceTokens = [['Maya',0,4],['walked',5,11],['Brrr',14,18],['It',20,22],['is',23,25],['cold',26,30],['she',33,36],['said',37,41]].map(([text,start,end])=>({id:text,text,start,end}));
const shape = items => items.map(item => item.parts ? item.parts.map(part => part.text).join('|') : `(${item.text})`);
test('groups words into sentences, keeping quotes and punctuation with their sentence',()=>{
  const items = splitSentences(sentenceText,sentenceTokens);
  assert.deepEqual(shape(items),['Maya| |walked|.','( )','“|Brrr|!','( )','It| |is| |cold|,” |she| |said|.']);
  assert.deepEqual(items.filter(item => item.parts).map(item => item.key),[0,13,20]);
});
test('sentence parts rebuild the paragraph exactly',()=>{
  const items = splitSentences(sentenceText,sentenceTokens);
  assert.equal(items.map(item => item.parts ? item.parts.map(part => part.text).join('') : item.text).join(''),sentenceText);
});
test('a paragraph with no words is plain text',()=>{
  assert.deepEqual(splitSentences('Caption only.',[]),[{text:'Caption only.'}]);
});
