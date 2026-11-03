<script setup>
import { computed, ref, useId } from 'vue';
import { nextWordIndex } from '../lib/wordCursor.js';
const props = defineProps({
  paragraphs: { type: Array, required: true },
  tokens: { type: Array, default: () => [] },
  activeTokenId: { type: String, default: null },
  replayEnabled: { type: Boolean, default: true },
});
const emit = defineEmits(['replay']);
// Screen readers read the passage as ordinary sentences, so words are plain text, not buttons.
// Mouse and touch select a word directly. Keyboard users Tab to the passage once, move a word
// cursor with the arrow keys (announced politely), and press Enter or Space to read from it.
const instructionsId = useId();
const container = ref(null);
const cursorId = ref(null);
const announcement = ref('');
const interactive = computed(() => props.replayEnabled && props.tokens.length > 0);
const rendered = computed(() => props.paragraphs.map(paragraph => {
  let cursor = 0;
  const parts = [];
  for (const token of props.tokens.filter(item => item.paragraphId === paragraph.id)) {
    if (token.start > cursor) parts.push({ text: paragraph.text.slice(cursor, token.start) });
    parts.push(token);
    cursor = token.end;
  }
  if (cursor < paragraph.text.length) parts.push({ text: paragraph.text.slice(cursor) });
  return { id: paragraph.id, parts };
}));
function select(token) {
  if (!interactive.value) return;
  cursorId.value = token.id;
  emit('replay', token.id);
}
function placeCursor() {
  cursorId.value = props.activeTokenId || cursorId.value || props.tokens[0]?.id || null;
}
function onKeydown(event) {
  if (!interactive.value) return;
  const index = Math.max(0, props.tokens.findIndex(item => item.id === cursorId.value));
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
    :role="interactive ? 'group' : undefined"
    :tabindex="interactive ? 0 : undefined"
    :aria-label="interactive ? 'Passage text' : undefined"
    :aria-describedby="interactive ? instructionsId : undefined"
    @focus="placeCursor"
    @keydown="onKeydown"
  >
    <p v-for="paragraph in rendered" :key="paragraph.id"><template v-for="(part, index) in paragraph.parts" :key="part.id || `gap-${index}`"><span v-if="part.id" :data-token-id="part.id" :class="{ 'spoken-word': activeTokenId === part.id, 'word-cursor': cursorId === part.id, replayable: interactive }" @click="select(part)">{{ part.text }}</span><template v-else>{{ part.text }}</template></template></p>
  </div>
  <p :id="instructionsId" hidden>Use the left and right arrow keys to choose a word, then press Enter to read from that word.</p>
  <span class="sr-only" aria-live="polite">{{ announcement }}</span>
</template>

<style scoped>
.read-along-text:focus { outline: none; }
.read-along-text:focus-visible { outline: 3px solid #db9d22; outline-offset: 8px; border-radius: 4px; }
[data-token-id] { border-radius: 3px; scroll-margin: 160px 0 48px; }
.replayable { cursor: pointer; }
.replayable:hover { background: #e7f1f4; }
.spoken-word { background: #ffe28a; box-shadow: 0 0 0 3px #ffe28a; color: #202529; }
.read-along-text:focus-visible .word-cursor { outline: 3px solid #db9d22; outline-offset: 2px; }
</style>
