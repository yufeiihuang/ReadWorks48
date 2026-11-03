<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';

const manifestUrl = '/generated/demo/efbf8d68f9ca6f777630-4386b7353988/manifest.json';
const passage = ref(null);
const audio = ref(null);
const error = ref('');
const playbackError = ref('');
const activeId = ref(null);
const focusId = ref(null);
const wordButtons = new Map();
let frame;

const paragraphs = computed(() => (passage.value?.paragraphs || []).map(paragraph => {
  const tokens = passage.value.tokens.filter(token => token.paragraphId === paragraph.id);
  let cursor = 0;
  const parts = [];
  for (const token of tokens) {
    if (token.start > cursor) parts.push({ text: paragraph.text.slice(cursor, token.start) });
    parts.push({ ...token });
    cursor = token.end;
  }
  if (cursor < paragraph.text.length) parts.push({ text: paragraph.text.slice(cursor) });
  return { id: paragraph.id, parts };
}));

function sync() {
  if (!audio.value || !passage.value || audio.value.ended) { activeId.value = null; return; }
  const now = audio.value.currentTime * 1000;
  const timings = passage.value.timings;
  let low = 0, high = timings.length - 1, index = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (timings[middle].startMs <= now) { index = middle; low = middle + 1; }
    else high = middle - 1;
  }
  activeId.value = index < 0 ? null : timings[index].tokenId;
}
function tick() { sync(); if (audio.value && !audio.value.paused) frame = requestAnimationFrame(tick); }
function playing() { cancelAnimationFrame(frame); playbackError.value = ''; tick(); }
function paused() { cancelAnimationFrame(frame); sync(); }
async function replay(token) {
  const timing = passage.value.timings.find(item => item.tokenId === token.id);
  if (!timing || !audio.value) return;
  focusId.value = token.id;
  audio.value.currentTime = timing.startMs / 1000;
  sync();
  try { await audio.value.play(); } catch { playbackError.value = 'Playback could not start. Try the audio play button.'; }
}
function moveFocus(event, token) {
  const tokens = passage.value.tokens;
  const index = tokens.findIndex(item => item.id === token.id);
  const next = event.key === 'ArrowRight' ? index + 1 : event.key === 'ArrowLeft' ? index - 1 : event.key === 'Home' ? 0 : event.key === 'End' ? tokens.length - 1 : null;
  if (next === null) return;
  event.preventDefault();
  const target = tokens[Math.max(0, Math.min(tokens.length - 1, next))];
  focusId.value = target.id;
  wordButtons.get(target.id)?.focus();
}
onMounted(async () => {
  try {
    const response = await fetch(manifestUrl);
    if (!response.ok) throw new Error('The generated passage could not be loaded.');
    const data = await response.json();
    if (!data.audio?.url || !data.tokens?.length || data.timings?.length !== data.tokens.length) throw new Error('This passage has incomplete audio or timing data.');
    passage.value = data;
    focusId.value = data.tokens[0].id;
  } catch (cause) { error.value = cause.message; }
});
onBeforeUnmount(() => { cancelAnimationFrame(frame); audio.value?.pause(); });
</script>

<template>
  <header class="site-header">
    <a href="/" class="brand">Read<span>Works</span><sup>®</sup></a>
    <span class="preview-label">SoundWorks · Stephen read along</span>
  </header>
  <main>
    <section v-if="error" class="error" role="alert"><h1>Unable to load preview</h1><p>{{ error }}</p><a href="/preview.html">Try again</a></section>
    <p v-else-if="!passage" class="error" role="status">Loading Stephen’s recording…</p>
    <template v-else>
      <section class="article-heading"><div class="heading-inner">
        <h1>{{ passage.title }}</h1>
        <nav class="article-tabs" aria-label="Passage sections"><span class="active" aria-current="page">Passage</span></nav>
      </div></section>
      <div class="article-layout">
        <article aria-label="Read along passage">
          <section class="preview-audio" aria-label="Stephen audio preview">
            <p class="preview-caption">Stephen · Polly Neural</p>
            <audio ref="audio" :src="passage.audio.url" controls preload="metadata" aria-label="Play Stephen narration"
              @play="playing" @pause="paused" @ended="paused" @seeked="sync" @timeupdate="sync" @ratechange="sync"
              @error="playbackError = 'Audio could not load. Reload the preview to try again.'" />
            <p class="preview-hint">Press play to follow along. Select any word to hear it again.</p>
            <p v-if="playbackError" role="alert">{{ playbackError }}</p>
          </section>
          <div class="passage preview-passage">
            <p v-for="paragraph in paragraphs" :key="paragraph.id"><template v-for="(part, index) in paragraph.parts" :key="part.id || `gap-${index}`"><button v-if="part.id" :ref="el => el ? wordButtons.set(part.id, el) : wordButtons.delete(part.id)" :data-token-id="part.id" :class="{ 'spoken-word': activeId === part.id }" :tabindex="focusId === part.id ? 0 : -1" :aria-label="`Read from ${part.text}`" @click="replay(part)" @focus="focusId = part.id" @keydown="moveFocus($event, part)">{{ part.text }}</button><template v-else>{{ part.text }}</template></template></p>
          </div>
          <p class="passage-credit">Original demonstration passage · SoundWorks</p>
        </article>
        <aside class="details" aria-labelledby="preview-details"><h2 id="preview-details">DETAILS</h2>
          <ul><li>Words: {{ passage.tokens.length }}</li><li>Language: English</li><li>Fiction</li></ul>
          <h3>Audio</h3><p>Stephen · Polly Neural</p><p class="muted">Generated in the AWS sandbox</p>
          <h3>Read along preview</h3><p>Native audio controls for this preview. The custom player is being built separately.</p>
          <p><a href="/">Back to main reader</a></p>
        </aside>
      </div>
    </template>
  </main>
  <footer>ReadWorks SoundWorks <span>Read along preview</span></footer>
</template>

<style scoped>
.preview-audio { margin-bottom: 28px; }
.preview-caption { margin: 0 0 10px; font-size: 14px; font-weight: 600; color: #347b91; }
audio { display: block; width: 100%; height: 48px; }
.preview-hint { font-size: 13px; color: #62727c; margin: 12px 0; }
.preview-passage button { font: inherit; color: inherit; line-height: inherit; background: transparent; border: 0; border-radius: 3px; padding: 0; cursor: pointer; }
.preview-passage button:hover { background: #e7f1f4; }
.preview-passage button.spoken-word { background: #ffe28a; box-shadow: 0 0 0 3px #ffe28a; color: #202529; }
.details a { color: #347b91; }
@media (max-width: 760px) { .preview-audio { margin-top: 20px; } }
@media print { .preview-audio { display: none; } }
</style>
