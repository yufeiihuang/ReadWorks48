<script setup>
import { computed, ref } from 'vue';
const props = defineProps({
  paragraphs: { type: Array, required: true },
  tokens: { type: Array, default: () => [] },
  activeTokenId: { type: String, default: null },
  replayEnabled: { type: Boolean, default: true },
});
const emit = defineEmits(['replay']);
const focusId = ref(null);
const buttons = new Map();
const focusTarget = computed(() => focusId.value || props.tokens[0]?.id);
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
function moveFocus(event, token) {
  const index = props.tokens.findIndex(item => item.id === token.id);
  const next = event.key === 'ArrowRight' ? index + 1 : event.key === 'ArrowLeft' ? index - 1 : event.key === 'Home' ? 0 : event.key === 'End' ? props.tokens.length - 1 : null;
  if (next === null) return;
  event.preventDefault();
  const target = props.tokens[Math.max(0, Math.min(props.tokens.length - 1, next))];
  focusId.value = target.id;
  buttons.get(target.id)?.focus();
}
</script>

<template>
  <div class="passage read-along-text">
    <p v-for="paragraph in rendered" :key="paragraph.id"><template v-for="(part, index) in paragraph.parts" :key="part.id || `gap-${index}`"><button v-if="part.id" :ref="el => el ? buttons.set(part.id, el) : buttons.delete(part.id)" :data-token-id="part.id" :class="{ 'spoken-word': activeTokenId === part.id }" :disabled="!replayEnabled" :tabindex="focusTarget === part.id ? 0 : -1" :aria-label="`Read from ${part.text}`" @click="emit('replay', part.id)" @focus="focusId = part.id" @keydown="moveFocus($event, part)">{{ part.text }}</button><template v-else>{{ part.text }}</template></template></p>
  </div>
</template>

<style scoped>
button { font: inherit; color: inherit; line-height: inherit; border: 0; padding: 0; border-radius: 3px; background: transparent; }
button:hover:not(:disabled) { background: #e7f1f4; }
button.spoken-word { background: #ffe28a; box-shadow: 0 0 0 3px #ffe28a; color: #202529; }
</style>
