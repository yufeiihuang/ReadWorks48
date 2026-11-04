<script setup>
import { computed, ref, useId, onBeforeUnmount, watch } from 'vue';
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
  selectAction: { type: String, default: 'read from that word' },
  // Color Focus: other paragraphs fade while this one is read, and the sentence being read is
  // highlighted. readingTokenId is the last word spoken, held through pauses between words.
  focusParagraphId: { type: String, default: null },
  sentenceHighlight: { type: Boolean, default: false },
  readingTokenId: { type: String, default: null },
});
const emit = defineEmits(['replay', 'define', 'word-leave', 'word-enter']);
// Screen readers read the passage as ordinary sentences, so words are plain text, not buttons.
// Mouse and touch select a word directly. Keyboard users Tab to the passage once, move a word
// cursor with the arrow keys (announced politely), and press Enter or Space to read from it.
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
const gesture = definitionGesture(value => emit('define', value));
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
  if (props.replayEnabled) emit('replay', token.id);
}
function placeCursor() {
  cursorId.value = props.activeTokenId || cursorId.value || props.tokens[0]?.id || null;
}
function onKeydown(event) {
  if (!interactive.value) return;
  const index = Math.max(0, props.tokens.findIndex(item => item.id === cursorId.value));
  if (event.key === 'Enter' && event.shiftKey) {
    event.preventDefault();
    const token = props.tokens[index];
    if (token) emit('define', requestDefinition(token, container.value.querySelector(`[data-token-id="${CSS.escape(token.id)}"]`), true));
    return;
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    select(props.tokens[index]);
    return;
  }
  const next = nextWordIndex(event.key, index, props.tokens.length);
  if (next === null) return;
  event.preventDefault();
  const token = props.tokens[next];
  cursorId.value = token.id;
  // A trailing space makes repeated words ("the", "the") announce again.
  announcement.value = announcement.value === token.text ? `${token.text} ` : token.text;
  container.value?.querySelector(`[data-token-id="${CSS.escape(token.id)}"]`)?.scrollIntoView({ block: 'nearest' });
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
    @keydown="onKeydown"
  >
    <component :is="heading ? 'h1' : 'p'" v-for="paragraph in rendered" :key="paragraph.id" :class="{ 'current-part': paragraph.id === focusParagraphId }"><template v-for="(item, itemIndex) in paragraph.items" :key="item.parts ? `s-${item.key}` : `t-${itemIndex}`"><span v-if="item.parts" class="sentence" :class="{ 'current-sentence': currentSentence === `${paragraph.id}:${item.key}` }"><template v-for="(part, index) in item.parts" :key="part.id || `gap-${index}`"><span v-if="part.id" :data-token-id="part.id" :class="{ 'spoken-word': activeTokenId === part.id, 'word-cursor': cursorId === part.id, replayable: interactive, 'official-word': officialTokenIds.includes(part.id) }" @click="select(part)" @pointerenter="enter($event, part)" @pointerleave="leave" @pointerdown="pointerDown($event, part)" @pointermove="gesture.move" @pointerup="gesture.up" @pointercancel="gesture.up" @contextmenu="touchPointer && $event.preventDefault()">{{ part.text }}</span><template v-else>{{ part.text }}</template></template></span><template v-else>{{ item.text }}</template></template></component>
  </div>
  <p :id="instructionsId" hidden>Use the left and right arrow keys to choose a word, then press Enter to {{ selectAction }}. Press Shift+Enter for a definition. Escape closes the definition card.</p>
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
.read-along-text p { transition: opacity .3s ease; }
.has-focus-part p:not(.current-part) { opacity: .4; }
/* The sentence highlight wraps across lines; clone gives each line its own rounded box. */
.sentence { border-radius: 6px; -webkit-box-decoration-break: clone; box-decoration-break: clone; transition: background-color .25s ease, box-shadow .25s ease; }
.current-sentence { background: rgb(255 255 255 / .85); box-shadow: 0 0 0 4px rgb(255 255 255 / .85); }
:global(.tint-none) .current-sentence { background: #e6f0f3; box-shadow: 0 0 0 4px #e6f0f3; }
@media (prefers-reduced-motion: reduce) { .read-along-text p, .sentence { transition: none; } }
@media print { .current-sentence { background: none; box-shadow: none; } .has-focus-part p:not(.current-part) { opacity: 1; } }
</style>
