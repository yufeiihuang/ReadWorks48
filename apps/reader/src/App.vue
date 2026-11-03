<script setup>
import { computed, onMounted, ref } from 'vue';
import AudioConsole from './components/AudioConsole.vue';
import PassageText from './components/PassageText.vue';
import { findActiveToken } from './lib/wordTiming.js';
import { useAudioPlayer } from './composables/useAudioPlayer.js';
// Playback test passage with ReadWorks' existing recording; open /?passage=pride-and-prejudice.
// Loaded in the reader until the API passage routes (SW-10) serve more than the demo fixture.
const referencePassages = { 'pride-and-prejudice': () => import('../../../shared/fixtures/pride-and-prejudice.json') };
const passageId = new URLSearchParams(window.location.search).get('passage') || 'demo';
const passage = ref(null);
const generationWarning = ref('');
const error = ref('');
const saved = ref(false);
const projector = ref(false);
const player = useAudioPlayer();
const audioUnavailable = computed(() => ['empty', 'error'].includes(player.state.status));
const activeTokenId = computed(() => {
  if (audioUnavailable.value || (!player.state.playing && player.state.currentTime === 0)) return null;
  return findActiveToken(passage.value?.timings || [], player.state.currentTime, player.state.duration);
});
function replayWord(tokenId) {
  const timing = passage.value?.timings?.find(item => item.tokenId === tokenId);
  if (timing && !audioUnavailable.value) player.playFrom(timing.startMs / 1000);
}
const isReference = computed(() => passage.value?.generation?.status === 'reference');
const reload = () => window.location.reload();
const printPassage = () => window.print();
const wordCount = computed(() => passage.value?.paragraphs.reduce((count, p) => count + p.text.trim().split(/\s+/).length, 0) || 0);
async function loadPassage(id) {
  if (id === 'demo') {
    try {
      const generated = await fetch('/generated/demo/efbf8d68f9ca6f777630-4386b7353988/manifest.json');
      if (!generated.ok) throw new Error('Generated passage unavailable');
      const manifest = await generated.json();
      if (!manifest.audio?.url || !manifest.tokens?.length || manifest.timings?.length !== manifest.tokens.length) throw new Error('Incomplete generated passage');
      return manifest;
    } catch { generationWarning.value = 'Generated audio is temporarily unavailable. The passage is still available to read.'; }
  }
  if (referencePassages[id]) return (await referencePassages[id]()).default;
  const response = await fetch(`/api/passages/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error('The passage could not be loaded.');
  return response.json();
}
onMounted(async () => {
  try {
    passage.value = await loadPassage(passageId);
    player.load(passage.value.audio?.url);
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
          <AudioConsole
            :disabled="audioUnavailable"
            :playing="player.state.playing"
            :current-time="player.state.currentTime"
            :duration="player.state.duration"
            :volume="player.state.volume"
            :playback-rate="player.state.playbackRate"
            @toggle-play="player.toggle"
            @restart="player.restart"
            @seek="player.seek"
            @volume-change="player.setVolume"
            @speed-change="player.setPlaybackRate"
          />
          <p class="audio-status">
            <span role="status">
              <template v-if="generationWarning">{{ generationWarning }}</template>
              <template v-else-if="player.state.status === 'empty'">Audio will be available once this passage is generated.</template>
              <template v-else-if="player.state.status === 'error' || player.state.error">{{ player.state.error }}</template>
              <template v-else-if="player.state.status === 'loading'">Loading audio…</template>
              <template v-else-if="isReference">Existing ReadWorks recording. Word highlighting arrives with generated timings.</template>
              <template v-else>Stephen · Polly Neural. Select any word to hear it again.</template>
            </span>
            <button v-if="player.state.status === 'error'" type="button" @click="player.retry">Try again</button>
          </p>
          <PassageText :key="passage.assetVersion" :paragraphs="passage.paragraphs" :tokens="passage.tokens || []" :active-token-id="activeTokenId" :replay-enabled="!audioUnavailable" @replay="replayWord" />
          <p class="passage-credit">{{ isReference ? 'Passage text and recording from ReadWorks · used to test playback' : 'Original demonstration passage · SoundWorks' }}</p>
        </article>
        <aside class="details" aria-labelledby="details-title">
          <h2 id="details-title">DETAILS</h2>
          <ul><li>Words: {{ wordCount }}</li><li>Language: English</li><li>Fiction</li></ul>
          <h3>Audio</h3>
          <template v-if="isReference"><p>Existing ReadWorks recording</p><p class="muted">Reference audio for testing the player</p></template>
          <template v-else><p>{{ passage.audio?.voice ? `${passage.audio.voice} · Polly Neural` : 'Polly Neural' }}</p><p class="muted">{{ passage.generation?.status === 'ready' ? 'Generated in the AWS sandbox' : 'Not generated yet' }}</p></template>
          <h3>About this passage</h3><p>{{ isReference ? 'A public ReadWorks passage used to test playback before generated audio is ready.' : 'Original sample text for the SoundWorks reader preview.' }}</p>
        </aside>
      </div>
    </main>
    <footer>ReadWorks SoundWorks <span>Hackathon reader preview</span></footer>
  </div>
</template>
