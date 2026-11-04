import test from 'node:test';
import assert from 'node:assert/strict';
import { definitionGesture } from '../src/lib/definitionGesture.js';
import { ensureTokens, wordContext, readMyWords } from '../src/lib/vocabulary.js';
function setup() {
  let now=0, sequence=0; const jobs=new Map(), opened=[];
  const gesture=definitionGesture(value=>opened.push(value),{set:(fn,delay)=>{jobs.set(++sequence,{at:now+delay,fn});return sequence;},clear:id=>jobs.delete(id)});
  const tick=ms=>{now+=ms;for(const [id,job] of jobs) if(job.at<=now){jobs.delete(id);job.fn();}};
  return {gesture,tick,opened};
}
test('hover opens only after 600ms at rest and cancellation prevents flashes',()=>{
  const {gesture,tick,opened}=setup();gesture.hover('bird');tick(599);assert.deepEqual(opened,[]);gesture.cancel();tick(10);assert.deepEqual(opened,[]);
  gesture.hover('sun');tick(600);assert.deepEqual(opened,['sun']);assert.equal(gesture.consumeClick(),false);
});
test('touch hold opens at 500ms and suppresses only its following click',()=>{
  const {gesture,tick,opened}=setup();gesture.down({pointerType:'touch',clientX:2,clientY:3},'bird');tick(499);assert.deepEqual(opened,[]);tick(1);gesture.up();assert.deepEqual(opened,['bird']);assert.equal(gesture.consumeClick(),true);assert.equal(gesture.consumeClick(),false);
});
test('movement over 10px, pointer cancellation, short taps and mouse down do not open',()=>{
  const {gesture,tick,opened}=setup();const event={pointerType:'touch',clientX:0,clientY:0};
  gesture.down(event,'bird');gesture.move({clientX:11,clientY:0});tick(500);
  gesture.down(event,'sun');tick(200);gesture.up();tick(500);assert.equal(gesture.consumeClick(),false);
  gesture.down({...event,pointerType:'mouse'},'mouse');tick(600);assert.deepEqual(opened,[]);
});
test('context preserves sentence punctuation and storage survives bad or unavailable data',()=>{
  const passage={paragraphs:[{id:'p1',text:'A bird sings. The bird rests.'}],tokens:[]};ensureTokens(passage);
  const word=wordContext(passage,'p1-18');assert.equal(word.sentence,'The bird rests.');assert.equal(word.before,'The ');assert.equal(word.after,' rests.');assert.equal(word.midSentence,true);
  assert.deepEqual(readMyWords({getItem:()=>'{broken'},'demo'),[]);assert.deepEqual(readMyWords({getItem:()=>{throw Error();}},'demo'),[]);
  const entry={word:'bird',sentence:'A bird sings.',definition:'An animal.'};assert.deepEqual(readMyWords({getItem:()=>JSON.stringify([entry,null,{}])},'demo'),[entry]);
});
