<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import AudioConsole from './components/AudioConsole.vue';
import PassageText from './components/PassageText.vue';
import ReadingAppearance from './components/ReadingAppearance.vue';
import ColorFocusPanel from './components/ColorFocusPanel.vue';
import { findActiveToken, findLastStartedToken, findSentenceStartSeconds, findWordRange } from './lib/wordTiming.js';
import { loadGeneratedPassage, wordClipUrl } from './lib/generatedPassage.js';
import { useAudioPlayer } from './composables/useAudioPlayer.js';
import { useFollowAlong } from './composables/useFollowAlong.js';
import { useColorFocus } from './composables/useColorFocus.js';
// Playback test passage with ReadWorks' existing recording; open /?passage=pride-and-prejudice.
// Loaded in the reader until the API passage routes (SW-10) serve more than the demo fixture.
const referencePassages = { 'pride-and-prejudice': () => import('../../../shared/fixtures/pride-and-prejudice.json') };
const pinnedManifests = {
  demo: '/generated/demo/efbf8d68f9ca6f777630-4386b7353988/manifest.json',
  'park-caretaker': '/generated/park-caretaker/human-712a36cf65895354e6b551d5/manifest.json',
};
const passageId = new URLSearchParams(window.location.search).get('passage') || 'demo';
// Dev only: ?manifest=/generated/ID/VERSION/manifest.json tries a recording before it's pinned.
function devManifest(id) {
  if (!import.meta.env.DEV) return null;
  const url = new URLSearchParams(window.location.search).get('manifest');
  return url && url.startsWith(`/generated/${id}/`) && url.endsWith('/manifest.json') ? url : null;
}
const passage = ref(null);
const generationWarning = ref('');
const highlightDismissed = ref(false);
const highlightEnabled = ref((() => {
  try { return localStorage.getItem('soundworks.highlightEnabled') !== 'false'; } catch { return true; }
})());
watch(highlightEnabled, enabled => {
  try { localStorage.setItem('soundworks.highlightEnabled', String(enabled)); } catch {}
});
const appearance = (() => {
  try { return JSON.parse(localStorage.getItem('soundworks.readingAppearance')) || {}; } catch { return {}; }
})();
const fontScale = ref([0.75, 1, 1.25, 1.5, 1.75, 2].includes(appearance.scale) ? appearance.scale : 1);
const dyslexiaFont = ref(appearance.dyslexia === true);
watch([fontScale, dyslexiaFont], ([scale, dyslexia]) => {
  try { localStorage.setItem('soundworks.readingAppearance', JSON.stringify({ scale, dyslexia })); } catch {}
});
const readingStyle = computed(() => ({
  '--reading-scale': fontScale.value,
  '--reading-font-family': dyslexiaFont.value ? 'OpenDyslexic, sans-serif' : 'inherit',
}));
const error = ref('');
const saved = ref(false);
const projector = ref(false);
const player = useAudioPlayer();
const audioUnavailable = computed(() => ['empty', 'error'].includes(player.state.status));
const activeTokenId = computed(() => {
  if (highlightDismissed.value || audioUnavailable.value || (!player.state.playing && player.state.currentTime === 0)) return null;
  return findActiveToken(passage.value?.timings || [], player.state.currentTime, player.state.duration);
});
const highlightedTokenId = computed(() => highlightEnabled.value ? activeTokenId.value : null);
function toggleHighlighting() {
  highlightEnabled.value = !highlightEnabled.value;
  if (highlightEnabled.value) { highlightDismissed.value = false; resumeFollowing(); }
}
watch(() => player.state.playing, playing => { if (playing) highlightDismissed.value = false; });
function dismissWordSelection(event) {
  if (event.target.closest('.audio-toolbar')) { highlightDismissed.value = false; return; }
  if (event.target.closest('button, a, input, select, label, [data-token-id]')) return;
  highlightDismissed.value = true;
  document.activeElement?.closest('.read-along-text')?.blur();
}
// Space under the sticky console; capped so a tall console on small screens can't hide the band.
const consoleInset = () => Math.min(Math.max(0, document.querySelector('.audio-toolbar')?.getBoundingClientRect().bottom ?? 0), window.innerHeight * 0.4);
const { following, placement: wordPlacement, resume: resumeFollowing } = useFollowAlong(highlightedTokenId, () => player.state.playing, { topInset: consoleInset, frozen: () => player.state.wordOnly });
// Color Focus: calm tint, reading guide, fewer distractions, and reading one paragraph at a time.
const { settings: focus, parts: focusParts, currentPart, finishedPart, jumped: noteJump, keepGoing } = useColorFocus(passage, player);
// The sentence highlight follows the last word spoken and stays on through pauses between words.
const readingTokenId = computed(() => {
  if (!focus.on || highlightDismissed.value || audioUnavailable.value || (!player.state.playing && player.state.currentTime === 0)) return null;
  return findLastStartedToken(passage.value?.timings || [], player.state.currentTime, player.state.duration);
});
const focusParagraphId = computed(() => {
  if (!focus.on || !focus.dim || audioUnavailable.value || (!player.state.playing && player.state.currentTime === 0)) return null;
  return focusParts.value[currentPart.value]?.paragraphId ?? null;
});
// What tapping a word does: 'read' continues the passage from it, 'say' plays just that word.
// Remembered per browser; storage can be unavailable, so it falls back to 'read'.
const wordAction = ref((() => { try { return localStorage.getItem('soundworks.wordAction') === 'say' ? 'say' : 'read'; } catch { return 'read'; } })());
watch(wordAction, value => { try { localStorage.setItem('soundworks.wordAction', value); } catch {} });
const canSelectWords = computed(() => !audioUnavailable.value && (passage.value?.timings?.length || 0) > 0);
function replayWord(tokenId) {
  highlightDismissed.value = false;
  const timing = passage.value?.timings?.find(item => item.tokenId === tokenId);
  if (timing && !audioUnavailable.value) { noteJump(); resumeFollowing(); player.playFrom(timing.startMs / 1000); }
}
// A separately recorded clip of the word when the passage has one (QA-1); otherwise, or if the clip
// can't play, a slice of the passage recording.
async function sayWord(tokenId) {
  highlightDismissed.value = false;
  if (audioUnavailable.value) return;
  const clipUrl = wordClipUrl(passage.value, tokenId);
  if (clipUrl && await player.playClip(clipUrl)) return;
  const range = findWordRange(passage.value?.timings || [], tokenId);
  if (range) player.playWord(range.start, range.end);
}
const selectWord = tokenId => (wordAction.value === 'say' ? sayWord(tokenId) : replayWord(tokenId));
function restartPassage() { noteJump(); resumeFollowing(); player.restart(); }
function seekPassage(seconds) { noteJump(); resumeFollowing(); player.seek(seconds); }
// Sentence replay needs word timings; without them a sentence cannot be located.
const canReplaySentence = computed(() =>
  !audioUnavailable.value
  && (passage.value?.timings?.length || 0) > 0
  && (passage.value?.tokens?.length || 0) > 0
);
// Seek to the start of the sentence at the current playback position, then keep
// playing. Reuses the single audio controller via playFrom (seek + play), and
// re-engages follow-along scrolling like the other transport controls.
function replaySentence() {
  if (!canReplaySentence.value) return;
  const seconds = findSentenceStartSeconds(
    passage.value?.paragraphs || [],
    passage.value?.tokens || [],
    passage.value?.timings || [],
    player.state.currentTime,
    player.state.duration,
  );
  if (Number.isFinite(seconds)) { noteJump(); resumeFollowing(); player.playFrom(seconds); }
}
const hasTimings = computed(() => Boolean(passage.value?.timings?.length));
const hasIncompleteTimings = computed(() => Boolean(passage.value?.alignment?.needsReview));
const isReference = computed(() => passage.value?.generation?.status === 'reference');
const isReadWorks = computed(() => passage.value?.source?.provider?.toLowerCase() === 'readworks');
const hasAudio = computed(() => Boolean(passage.value?.audio?.url));
const reload = () => window.location.reload();
const printPassage = () => window.print();
const wordCount = computed(() => passage.value?.paragraphs.reduce((count, p) => count + p.text.trim().split(/\s+/).length, 0) || 0);
async function loadPassage(id) {
  if (referencePassages[id]) return (await referencePassages[id]()).default;
  try {
    const manifest = await loadGeneratedPassage(id, devManifest(id) || pinnedManifests[id]);
    if (manifest) return manifest;
  } catch { generationWarning.value = 'Audio is temporarily unavailable. The passage is still available to read.'; }
  const response = await fetch(`/api/passages/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error('The passage could not be loaded.');
  return response.json();
}
onBeforeUnmount(() => document.removeEventListener('click', dismissWordSelection));
onMounted(async () => {
  document.addEventListener('click', dismissWordSelection);
  try {
    passage.value = await loadPassage(passageId);
    player.load(passage.value.audio?.url);
  } catch (cause) { error.value = cause.message; }
});
</script>

<template>
  <div :class="{ projector, 'color-focus': focus.on }" :style="readingStyle">
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
            <button type="button" class="focus-switch" role="switch" :aria-checked="focus.on" @click="focus.on = !focus.on"><span class="switch-track" aria-hidden="true"><span class="switch-knob"></span></span>Color Focus</button>
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
            :can-replay-sentence="canReplaySentence"
            @toggle-play="player.toggle"
            @restart="restartPassage"
            @replay-sentence="replaySentence"
            @seek="seekPassage"
            @volume-change="player.setVolume"
            @speed-change="player.setPlaybackRate"
          />
          <p v-if="finishedPart !== null || generationWarning || audioUnavailable || player.state.error || player.state.status === 'loading' || player.state.buffering || hasIncompleteTimings || !hasTimings" class="audio-status">
            <span role="status">
              <template v-if="generationWarning">{{ generationWarning }}</template>
              <template v-else-if="player.state.status === 'empty'">Audio isn't ready for this passage yet. You can still read it.</template>
              <template v-else-if="player.state.status === 'error' || player.state.error">{{ player.state.error }}</template>
              <template v-else-if="player.state.status === 'loading'">Loading audio…</template>
              <template v-else-if="player.state.buffering">Buffering audio…</template>
              <template v-else-if="finishedPart !== null">Part {{ finishedPart + 1 }} of {{ focusParts.length }} done. Select Keep going when you're ready.</template>
              <template v-else-if="hasIncompleteTimings">Some words are not available for highlighting.</template>
              <template v-else>Press play to listen. Word highlighting is not available for this passage.</template>
            </span>
            <button v-if="player.state.status === 'error'" type="button" @click="player.retry">Try again</button>
          </p>
          <div class="reading-settings" aria-label="Reading settings" role="group">
            <label v-if="canSelectWords" class="word-action">
              <span>Tap a word to</span>
              <select v-model="wordAction" aria-label="Tap a word to">
                <option value="read">Read from there</option>
                <option value="say">Hear just that word</option>
              </select>
            </label>
            <ReadingAppearance v-model:scale="fontScale" v-model:dyslexia="dyslexiaFont">
              <label v-if="hasTimings" class="highlight-control">
                <span>Highlight</span>
                <input class="highlight-switch" type="checkbox" role="switch" :checked="highlightEnabled" @change="toggleHighlighting">
                <span class="highlight-track" aria-hidden="true"><span class="highlight-thumb"></span></span>
                <span class="highlight-state" aria-hidden="true">{{ highlightEnabled ? 'On' : 'Off' }}</span>
              </label>
            </ReadingAppearance>
          </div>
          <ColorFocusPanel v-if="focus.on" :settings="focus" :part-count="focusParts.length" :current-part="currentPart" :has-timings="canSelectWords" />
          <div class="passage-frame" :class="focus.on && `tint-${focus.tint}`">
            <PassageText :key="passage.assetVersion" :paragraphs="passage.paragraphs" :tokens="passage.tokens || []" :active-token-id="highlightedTokenId" :replay-enabled="!audioUnavailable" :select-action="wordAction === 'say' ? 'hear that word' : 'read from that word'" :focus-paragraph-id="focusParagraphId" :sentence-highlight="focus.on && focus.guide" :reading-token-id="readingTokenId" @replay="selectWord" />
          </div>
          <p class="passage-credit"><template v-if="isReadWorks || isReference">Passage from <a v-if="passage.source?.url" :href="passage.source.url">ReadWorks</a><template v-else>ReadWorks</template><template v-if="passage.source?.author"> · {{ passage.source.author }}</template></template><template v-else>Original demonstration passage · SoundWorks</template></p>
        </article>
        <aside class="details" aria-labelledby="details-title">
          <h2 id="details-title">DETAILS</h2>
          <ul><li>Words: {{ wordCount }}</li><li>Language: English</li><li v-if="!isReadWorks">Fiction</li></ul>
          <h3>Audio</h3>
          <p>{{ hasAudio ? 'Available' : 'Not available yet' }}</p>
          <p v-if="hasIncompleteTimings" class="muted">Some words are not highlighted.</p>
          <h3>About this passage</h3><p>{{ isReadWorks || isReference ? 'A reading passage from ReadWorks.' : 'Original sample text for the SoundWorks reader preview.' }}</p>
        </aside>
      </div>
      <div class="floating-actions">
        <button v-if="finishedPart !== null" type="button" class="part-break" @click="keepGoing">
          <span class="part-done"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>Part {{ finishedPart + 1 }} of {{ focusParts.length }} done</span>
          <span class="keep-going">Keep going<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7z"/></svg></span>
        </button>
        <button v-if="highlightEnabled && !following && activeTokenId && wordPlacement !== 'visible'" type="button" class="follow-return" @click="resumeFollowing">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path v-if="wordPlacement === 'above'" d="M12 19V5M6 11l6-6 6 6"/><path v-else d="M12 5v14M6 13l6 6 6-6"/></svg>
          Back to where we're reading
        </button>
      </div>
    </main>
    <footer>ReadWorks SoundWorks <span>Hackathon reader preview</span></footer>
  </div>
</template>
