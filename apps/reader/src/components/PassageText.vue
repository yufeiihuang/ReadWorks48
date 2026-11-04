<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue';
import { definitionGesture } from '../lib/definitionGesture.js';
import { nextWordIndex } from '../lib/wordCursor.js';
import { splitSentences } from '../lib/readingParts.js';
const props = defineProps({
  definitionsEnabled: { type: Boolean, default: true },
  officialTokenIds: { type: Array, default: () => [] },
  heading: { type: Boolean, default: false },
  paragraphs: { type: Array, required: true },
  tokens: { type: Array, default: () => [] },
  activeTokenId: { type: String, default: null },
  replayEnabled: { type: Boolean, default: true },
  // False for a word with nothing to play: no clip of its own and no timing in the recording.
  canHear: { type: Function, default: () => true },
  // Color Focus: other paragraphs fade while this one is read, and the sentence being read is
  // highlighted. readingTokenId is the last word spoken, held through pauses between words.
  focusParagraphId: { type: String, default: null },
  sentenceHighlight: { type: Boolean, default: false },
  readingTokenId: { type: String, default: null },
});
const emit = defineEmits(['replay', 'hear', 'define', 'word-leave', 'word-enter']);
// Screen readers read the passage as ordinary sentences, so words are plain text, not buttons.
// Mouse and touch select a word directly. Keyboard users Tab to the passage once, move a word
// cursor with the arrow keys (announced politely), and press Enter or Space to read from it, or H
// to hear just that word.
const instructionsId = useId();
const container = ref(null);
const cursorId = ref(null);
const announcement = ref('');
const interactive = computed(() => props.tokens.length > 0);
const rendered = computed(() => props.paragraphs.map(paragraph => ({
  id: paragraph.id,
  items: splitSentences(paragraph.text, props.tokens.filter(item => item.paragraphId === paragraph.id)),
})));
const sentenceOfToken = computed(() => {
  const map = new Map();
  for (const paragraph of rendered.value) {
    for (const item of paragraph.items) {
      if (!item.parts) continue;
      for (const part of item.parts) if (part.id) map.set(part.id, `${paragraph.id}:${item.key}`);
    }
  }
  return map;
});
const currentSentence = computed(() => (props.sentenceHighlight && props.readingTokenId ? sentenceOfToken.value.get(props.readingTokenId) : null));
const gesture = definitionGesture(value => { hideBubble(); emit('define', value); });
onBeforeUnmount(gesture.cancel);
watch(() => props.definitionsEnabled, enabled => { if (!enabled) gesture.cancel(); });
let touchPointer = false;
function pointerDown(event, token) {
  touchPointer = event.pointerType === 'touch';
  gesture.down(event, requestDefinition(token, event.currentTarget));
}
function requestDefinition(token, target, keyboard = false) { return { tokenId: token.id, target, keyboard }; }
function enter(event, token) {
  if (event.pointerType === 'touch' || !props.definitionsEnabled) return;
  emit('word-enter');
  gesture.hover(requestDefinition(token, event.currentTarget));
}
function leave(event) { gesture.cancel(); if (event.pointerType !== 'touch') emit('word-leave'); }
function select(token) {
  if (gesture.consumeClick()) return;
  if (!interactive.value) return;
  cursorId.value = token.id;
  if (!props.replayEnabled) return;
  // Touch has no hover, so a tap offers both choices instead of starting the audio.
  if (lastPointer === 'touch') { showBubble(token, 'touch'); return; }
  hideBubble();
  emit('replay', token.id);
}
function hear(token) {
  hideBubble();
  if (props.replayEnabled && props.canHear(token.id)) emit('hear', token.id);
}
function readFrom(token) {
  hideBubble();
  if (!props.replayEnabled) return;
  emit('replay', token.id);
}

// One bubble for the whole passage, kept outside the text so screen readers still get plain sentences.
const SHOW_DELAY_MS = 250; // Long enough that moving the mouse across a line doesn't flicker it.
const HIDE_DELAY_MS = 200; // Long enough to cross the gap from the word to the bubble.
const bubble = ref(null); // { token, source: 'mouse' | 'touch' | 'keyboard' }
const bubbleElement = ref(null);
const bubbleStyle = ref({});
let lastPointer = 'mouse';
let showTimer;
let hideTimer;
const wordElement = id => container.value?.querySelector(`[data-token-id="${CSS.escape(id)}"]`);

function clearTimers() {
  clearTimeout(showTimer);
  clearTimeout(hideTimer);
}
function hideBubble() {
  clearTimers();
  bubble.value = null;
}
async function showBubble(token, source) {
  clearTimers();
  if (!props.replayEnabled || !props.canHear(token.id)) { bubble.value = null; return; }
  bubbleStyle.value = { visibility: 'hidden' };
  bubble.value = { token, source };
  await nextTick();
  positionBubble();
}
function positionBubble() {
  const word = bubble.value && wordElement(bubble.value.token.id);
  if (!word || !bubbleElement.value) return;
  const box = word.getBoundingClientRect();
  const { width, height } = bubbleElement.value.getBoundingClientRect();
  const left = Math.min(Math.max(8, box.left + box.width / 2 - width / 2), window.innerWidth - width - 8);
  // Above the word, unless that would put it behind the pinned audio console.
  const consoleBottom = document.querySelector('.audio-toolbar')?.getBoundingClientRect().bottom ?? 0;
  const below = box.top - height - 10 < consoleBottom;
  bubbleStyle.value = { left: `${left}px`, top: `${below ? box.bottom + 10 : box.top - height - 10}px` };
}
function tokenFromEvent(event) {
  const id = event.target.closest?.('[data-token-id]')?.dataset.tokenId;
  return id ? props.tokens.find(item => item.id === id) : null;
}
function onPointerOver(event) {
  if (event.pointerType !== 'mouse' || !props.replayEnabled || props.definitionsEnabled || !interactive.value) return;
  const token = tokenFromEvent(event);
  if (!token) return;
  clearTimers();
  if (bubble.value?.token.id === token.id) return;
  showTimer = setTimeout(() => showBubble(token, 'mouse'), SHOW_DELAY_MS);
}
function scheduleHide(event) {
  if (event.pointerType !== 'mouse' || bubble.value?.source === 'keyboard') { clearTimeout(showTimer); return; }
  clearTimers();
  hideTimer = setTimeout(hideBubble, HIDE_DELAY_MS);
}
function onScroll() {
  if (bubble.value?.source === 'keyboard') positionBubble();
  else if (bubble.value) hideBubble();
}
function onDocumentPointerDown(event) {
  if (bubble.value?.source !== 'touch' || bubbleElement.value?.contains(event.target)) return;
  if (!container.value?.contains(event.target)) hideBubble();
}
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true, capture: true });
  document.addEventListener('pointerdown', onDocumentPointerDown);
});
onBeforeUnmount(() => {
  clearTimers();
  window.removeEventListener('scroll', onScroll, { capture: true });
  document.removeEventListener('pointerdown', onDocumentPointerDown);
});
function placeCursor() {
  cursorId.value = props.activeTokenId || cursorId.value || props.tokens[0]?.id || null;
}
function onKeydown(event) {
  if (!interactive.value) return;
  const index = Math.max(0, props.tokens.findIndex(item => item.id === cursorId.value));
  if (event.key === 'Enter' && event.shiftKey) {
    event.preventDefault();
    const token = props.tokens[index];
    hideBubble();
    if (token) emit('define', requestDefinition(token, container.value.querySelector(`[data-token-id="${CSS.escape(token.id)}"]`), true));
    return;
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    readFrom(props.tokens[index]);
    return;
  }
  if (event.key === 'Escape') { hideBubble(); return; }
  if (event.key.toLowerCase() === 'h' && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
    hear(props.tokens[index]);
    return;
  }
  const next = nextWordIndex(event.key, index, props.tokens.length);
  if (next === null) return;
  event.preventDefault();
  const token = props.tokens[next];
  cursorId.value = token.id;
  // A trailing space makes repeated words ("the", "the") announce again.
  announcement.value = announcement.value === token.text ? `${token.text} ` : token.text;
  wordElement(token.id)?.scrollIntoView({ block: 'nearest' });
  showBubble(token, 'keyboard');
}
</script>

<template>
  <div
    ref="container"
    class="passage read-along-text"
    :class="{ 'has-focus-part': !!focusParagraphId }"
    :role="interactive ? 'group' : undefined"
    :tabindex="interactive ? 0 : undefined"
    :aria-label="interactive ? 'Passage text' : undefined"
    :aria-describedby="interactive ? instructionsId : undefined"
    @focus="placeCursor"
    @blur="bubble?.source === 'keyboard' && hideBubble()"
    @keydown="onKeydown"
    @pointerdown="lastPointer = $event.pointerType"
    @pointerover="onPointerOver"
    @pointerout="scheduleHide"
  >
    <component :is="heading ? 'h1' : 'p'" v-for="paragraph in rendered" :key="paragraph.id" :class="{ 'current-part': paragraph.id === focusParagraphId }"><template v-for="(item, itemIndex) in paragraph.items" :key="item.parts ? `s-${item.key}` : `t-${itemIndex}`"><span v-if="item.parts" class="sentence" :class="{ 'current-sentence': currentSentence === `${paragraph.id}:${item.key}` }"><template v-for="(part, index) in item.parts" :key="part.id || `gap-${index}`"><span v-if="part.id" :data-token-id="part.id" :class="{ 'spoken-word': activeTokenId === part.id, 'word-cursor': cursorId === part.id, replayable: interactive, 'official-word': officialTokenIds.includes(part.id) }" @click="select(part)" @pointerenter="enter($event, part)" @pointerleave="leave" @pointerdown="pointerDown($event, part)" @pointermove="gesture.move" @pointerup="gesture.up" @pointercancel="gesture.up" @contextmenu="touchPointer && $event.preventDefault()">{{ part.text }}</span><template v-else>{{ part.text }}</template></template></span><template v-else>{{ item.text }}</template></template></component>
  </div>
  <p :id="instructionsId" hidden>Use the left and right arrow keys to choose a word. Press Enter to read from that word, or H to hear just that word. Press Shift+Enter for a definition. Escape closes the definition card.</p>
  <div
    v-if="bubble"
    ref="bubbleElement"
    class="word-bubble"
    :style="bubbleStyle"
    :aria-hidden="bubble.source === 'keyboard' ? 'true' : undefined"
    @mousedown.prevent
    @pointerenter="clearTimers"
    @pointerleave="scheduleHide"
  >
    <button v-if="bubble.source === 'touch'" type="button" tabindex="-1" @click="readFrom(bubble.token)">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7z" /></svg>
      Read from here
    </button>
    <button type="button" tabindex="-1" @click="hear(bubble.token)">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4zM16 8c3 2 3 6 0 8" /></svg>
      Hear this word<template v-if="bubble.source === 'keyboard'"> (press H)</template>
    </button>
  </div>
  <span class="sr-only" aria-live="polite">{{ announcement }}</span>
</template>

<style scoped>
.read-along-text h1 { margin: 0; font: inherit; }
.read-along-text:focus { outline: none; }
.read-along-text:focus-visible { outline: 3px solid #db9d22; outline-offset: 8px; border-radius: 4px; }
.official-word { text-decoration: underline dotted; text-underline-offset: 5px; }
[data-token-id] { -webkit-touch-callout: none; user-select: none; -webkit-user-select: none; border-radius: 3px; scroll-margin: 160px 0 48px; }
.replayable { cursor: pointer; }
.replayable:hover { background: #e7f1f4; }
.spoken-word { background: #ffe28a; box-shadow: 0 0 0 3px #ffe28a; color: #202529; }
.read-along-text:focus-visible .word-cursor { outline: 3px solid #db9d22; outline-offset: 2px; }
.word-bubble { position: fixed; z-index: 40; display: flex; gap: 2px; padding: 4px; border-radius: 8px; background: #235b6e; box-shadow: 0 4px 14px rgb(0 0 0 / .25); white-space: nowrap; }
.word-bubble button { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 4px 12px 4px 8px; border: 0; border-radius: 5px; background: none; color: white; font-size: 14px; font-weight: 500; }
.word-bubble button:hover { background: rgb(255 255 255 / .18); }
.word-bubble svg { width: 18px; height: 18px; }
@media (pointer: coarse) { .word-bubble button { min-height: 44px; } }
@media print { .word-bubble { display: none; } }
.read-along-text p { transition: opacity .3s ease; }
.has-focus-part p:not(.current-part) { opacity: .4; }
/* The sentence highlight wraps across lines; clone gives each line its own rounded box. */
.sentence { border-radius: 6px; -webkit-box-decoration-break: clone; box-decoration-break: clone; transition: background-color .25s ease, box-shadow .25s ease; }
.current-sentence { background: rgb(255 255 255 / .85); box-shadow: 0 0 0 4px rgb(255 255 255 / .85); }
@media (prefers-reduced-motion: reduce) { .read-along-text p, .sentence { transition: none; } }
@media print { .current-sentence { background: none; box-shadow: none; } .has-focus-part p:not(.current-part) { opacity: 1; } }
</style>
