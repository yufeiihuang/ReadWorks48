<script setup>
import { computed, onMounted, ref } from 'vue';
const passage = ref(null);
const error = ref('');
const saved = ref(false);
const projector = ref(false);
const reload = () => window.location.reload();
const printPassage = () => window.print();
const wordCount = computed(() => passage.value?.paragraphs.reduce((count, p) => count + p.text.trim().split(/\s+/).length, 0) || 0);
onMounted(async () => {
  try {
    const response = await fetch('/api/passages/demo');
    if (!response.ok) throw new Error('The passage could not be loaded.');
    passage.value = await response.json();
  } catch (cause) { error.value = cause.message; }
});
</script>

<template>
  <div :class="{ projector }">
    <header class="site-header">
      <a class="brand" href="/" aria-label="ReadWorks SoundWorks home">Read<span>Works</span><sup>®</sup></a>
      <span class="preview-label">SoundWorks · Reader preview</span>
    </header>
    <main v-if="error" class="error" role="alert"><h1>Unable to open this passage</h1><p>{{ error }}</p><button @click="reload">Try again</button></main>
    <main v-else-if="!passage"><p role="status">Loading passage…</p></main>
    <main v-else class="article-page">
      <section class="article-heading">
        <div class="heading-inner">
          <h1>{{ passage.title }}</h1>
          <div class="article-actions" aria-label="Passage actions">
            <button disabled title="Assignments are not available in this preview">Assign</button>
            <button @click="printPassage">Print</button>
            <button class="icon-button" :aria-pressed="projector" :aria-label="projector ? 'Exit projector view' : 'Enter whiteboard or projector view'" @click="projector = !projector"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="12" rx="1"/><path d="M9 20h6M12 16v4"/></svg></button>
            <button class="icon-button" :aria-pressed="saved" :aria-label="saved ? 'Remove bookmark' : 'Bookmark passage for this session'" @click="saved = !saved"><svg viewBox="0 0 24 24" aria-hidden="true" :class="{ filled: saved }"><path d="M6 3h12v18l-6-4-6 4z"/></svg></button>
          </div>
          <nav class="article-tabs" aria-label="Passage sections"><span class="active" aria-current="page">Passage</span><button disabled>Vocabulary Activity</button><button disabled>Question Set</button></nav>
        </div>
      </section>
      <div class="article-layout">
        <article aria-label="Passage">
          <section class="audio-toolbar" aria-label="Passage audio controls">
            <div class="audio-player">
              <button disabled class="play" aria-label="Play passage">▶</button>
              <span class="audio-time">0:00 / --:--</span>
              <input type="range" disabled value="0" aria-label="Audio position" />
              <button disabled class="speaker" aria-label="Volume"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4zM16 8c3 2 3 6 0 8M19 5c5 4 5 10 0 14"/></svg></button>
            </div>
            <label class="speed"><span class="sr-only">Playback speed</span><select disabled aria-label="Playback speed"><option>1×</option></select></label>
          </section>
          <p class="audio-status">Audio will be available once this passage is generated.</p>
          <div class="passage"><p v-for="paragraph in passage.paragraphs" :key="paragraph.id">{{ paragraph.text }}</p></div>
          <p class="passage-credit">Original demonstration passage · SoundWorks</p>
        </article>
        <aside class="details" aria-labelledby="details-title">
          <h2 id="details-title">DETAILS</h2>
          <ul><li>Words: {{ wordCount }}</li><li>Language: English</li><li>Fiction</li></ul>
          <h3>Audio</h3><p>Polly Neural</p><p class="muted">Not generated yet</p>
          <h3>About this passage</h3><p>Original sample text for the SoundWorks reader preview.</p>
        </aside>
      </div>
    </main>
    <footer>ReadWorks SoundWorks <span>Hackathon reader preview</span></footer>
  </div>
</template>
