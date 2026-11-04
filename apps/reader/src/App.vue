<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import SettingSwitch from './components/SettingSwitch.vue';
import VocabularyActivity from './components/VocabularyActivity.vue';
import VocabularyWord from './components/VocabularyWord.vue';
import { useVocabulary } from './composables/useVocabulary.js';
import { ensureTokens } from './lib/vocabulary.js';
import AudioConsole from './components/AudioConsole.vue';
import PassageText from './components/PassageText.vue';
import ReadingAppearance from './components/ReadingAppearance.vue';
import ColorFocusPanel from './components/ColorFocusPanel.vue';
import SpeedTip from './components/SpeedTip.vue';
import { findActiveToken, findLastStartedToken, findSentenceStartSeconds, findWordRange } from './lib/wordTiming.js';
import { loadGeneratedPassage, loadLatestGeneratedPassage, wordClipUrl } from './lib/generatedPassage.js';
import { loadGradeId, suggestSpeed } from './lib/speedSuggestion.js';
import { useAudioPlayer } from './composables/useAudioPlayer.js';
import { useFollowAlong } from './composables/useFollowAlong.js';
import { useColorFocus } from './composables/useColorFocus.js';
// Playback test passage with ReadWorks' existing recording; open /?passage=pride-and-prejudice.
// Loaded in the reader until the API passage routes (SW-10) serve more than the demo fixture.
const referencePassages = { 'pride-and-prejudice': () => import('../../../shared/fixtures/pride-and-prejudice.json') };
// Reviewed demo recordings. A published current.json never replaces these; ?latest=1 previews it
// (falling back to the pin), and promoting it means updating the pin here.
const pinnedManifests = {
  demo: '/generated/demo/adbeeb10a403af4424e1-4386b7353988/manifest.json',
  'park-caretaker': '/generated/park-caretaker/human-712a36cf65895354e6b551d5/manifest.json',
};
const passageId = new URLSearchParams(window.location.search).get('passage') || 'demo';
const demoPassages = [
  { id: 'demo', title: 'A Morning in the Garden' },
  { id: 'park-caretaker-qa', title: "Let's Meet a Park Caretaker" },
  { id: 'pride-and-prejudice', title: 'Excerpt from Pride and Prejudice' },
];
function switchPassage(event) {
  const id = event.target.value;
  if (id === passageId || !demoPassages.some(item => item.id === id)) return;
  const url = new URL(window.location.href);
  url.searchParams.set('passage', id);
  url.searchParams.delete('manifest');
  // Navigation resets playback and passage-specific state and supports browser Back.
  window.location.assign(url.href);
}
// Dev only: ?manifest=/generated/ID/VERSION/manifest.json tries a recording before it's pinned.
function devManifest(id) {
  if (!import.meta.env.DEV) return null;
  const url = new URLSearchParams(window.location.search).get('manifest');
  return url && url.startsWith(`/generated/${id}/`) && url.endsWith('/manifest.json') ? url : null;
}
const passage = ref(null);
const { tab, official, officialTokenIds, vocabularyStatus, myWords, hoverEnabled, isSaved, toggleWord, loadVocabulary, card, cardElement, cardStyle, openCard, closeCard, keepCard, leaveCard, tabKey } = useVocabulary(passage, passageId);
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
const { following, placement: wordPlacement, resume: resumeFollowing } = useFollowAlong(computed(() => tab.value === 'passage' ? highlightedTokenId.value : null), () => player.state.playing, { topInset: consoleInset, frozen: () => player.state.wordOnly || tab.value !== 'passage' });
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
    [ ...(passage.value?.narrationTitle ? [passage.value.narrationTitle] : []), ...(passage.value?.paragraphs || []) ],
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
// A first-visit tip, remembered per browser once the student answers it. Playing without
// answering only closes it for now, so it doesn't sit over the text being read.
const gradeId = ref(null);
const speedTipClosed = ref((() => { try { return localStorage.getItem('soundworks.speedTipSeen') === 'true'; } catch { return false; } })());
const speedSuggestion = computed(() => (speedTipClosed.value || player.state.status !== 'ready'
  ? null
  : suggestSpeed(gradeId.value)));
function answerSpeedTip() {
  speedTipClosed.value = true;
  try { localStorage.setItem('soundworks.speedTipSeen', 'true'); } catch {}
}
function acceptSpeedSuggestion() {
  player.setPlaybackRate(speedSuggestion.value.speed);
  answerSpeedTip();
}
function changeSpeed(speed) {
  player.setPlaybackRate(speed);
  answerSpeedTip();
}
watch(() => player.state.playing, playing => { if (playing) speedTipClosed.value = true; });
async function loadPassage(id) {
  try {
    const preview = devManifest(id);
    const followLatest = !preview && new URLSearchParams(window.location.search).get('latest') === '1';
    const manifest = followLatest ? await loadLatestGeneratedPassage(id, pinnedManifests[id])
      : await loadGeneratedPassage(id, preview || pinnedManifests[id]);
    if (manifest) return manifest;
  } catch { generationWarning.value = 'Audio is temporarily unavailable. The passage is still available to read.'; }
  if (referencePassages[id]) return (await referencePassages[id]()).default;
  const response = await fetch(`/api/passages/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error('The passage could not be loaded.');
  return response.json();
}
onBeforeUnmount(() => document.removeEventListener('click', dismissWordSelection));
onMounted(async () => {
  document.addEventListener('click', dismissWordSelection);
  try {
    passage.value = await loadPassage(passageId);
    ensureTokens(passage.value);
    loadVocabulary();
    player.load(passage.value.audio?.url);
    if (passage.value.audio?.url) loadGradeId(passage.value).then(id => { gradeId.value = id; });
  } catch (cause) { error.value = cause.message; }
});
</script>

<template>
  <div :class="{ projector, 'color-focus': focus.on }" :style="readingStyle">
    <header class="site-header">
      <a class="brand" href="/" aria-label="ReadWorks SoundWorks home">Read<span>Works</span><sup>®</sup></a>
      <label class="passage-picker">
        <span>Passage</span>
        <select aria-label="Choose a passage" :value="passageId" @change="switchPassage">
          <option v-if="!demoPassages.some(item => item.id === passageId)" :value="passageId">{{ passage?.title || 'Current passage' }}</option>
          <option v-for="item in demoPassages" :key="item.id" :value="item.id">{{ item.title }}</option>
        </select>
      </label>
    </header>
    <main v-if="error" class="error" role="alert"><h1>Unable to open this passage</h1><p>{{ error }}</p><button @click="reload">Try again</button></main>
    <main v-else-if="!passage"><p role="status">Loading passage…</p></main>
    <main v-else class="article-page">
      <section class="article-heading">
        <div class="heading-inner">
          <div class="narrated-title" v-if="passage.narrationTitle"><PassageText heading :paragraphs="[passage.narrationTitle]" :tokens="(passage.tokens || []).filter(t => t.paragraphId === passage.narrationTitle.id)" :active-token-id="highlightedTokenId" :replay-enabled="!audioUnavailable" :definitions-enabled="hoverEnabled" :official-token-ids="officialTokenIds" @define="openCard" @word-enter="keepCard" @word-leave="leaveCard" @replay="selectWord" /></div>
          <h1 v-else>{{ passage.title }}</h1>
          <div class="article-actions" aria-label="Passage actions">
            <button disabled title="Assignments are not available in this preview">Assign</button>
            <button @click="printPassage">Print</button>
            <button class="icon-button" :aria-pressed="projector" :aria-label="projector ? 'Exit projector view' : 'Enter whiteboard or projector view'" @click="projector = !projector"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="12" rx="1"/><path d="M9 20h6M12 16v4"/></svg></button>
            <button class="icon-button" :aria-pressed="saved" :aria-label="saved ? 'Remove bookmark' : 'Bookmark passage for this session'" @click="saved = !saved"><svg viewBox="0 0 24 24" aria-hidden="true" :class="{ filled: saved }"><path d="M6 3h12v18l-6-4-6 4z"/></svg></button>
          </div>
          <nav class="article-tabs" role="tablist" aria-label="Passage sections" @keydown="tabKey">
            <button v-for="name in ['passage', 'vocabulary']" :key="name" :id="`tab-${name}`" role="tab" :class="{ active: tab === name }" :aria-selected="tab === name" :aria-controls="`panel-${name}`" :tabindex="tab === name ? 0 : -1" @click="tab = name">{{ name === 'passage' ? 'Passage' : 'Vocabulary' }}</button>
          </nav>
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
            :speed-tip-open="Boolean(speedSuggestion)"
            @toggle-play="player.toggle"
            @restart="restartPassage"
            @replay-sentence="replaySentence"
            @seek="seekPassage"
            @volume-change="player.setVolume"
            @speed-change="changeSpeed"
          >
            <template #speed-tip>
              <SpeedTip v-if="speedSuggestion" :question="speedSuggestion.question" :speed="speedSuggestion.speed" @accept="acceptSpeedSuggestion" @dismiss="answerSpeedTip" />
            </template>
          </AudioConsole>
          <span class="sr-only" role="status"><template v-if="speedSuggestion">{{ speedSuggestion.question }} Change to {{ speedSuggestion.speed }}× speed for better listening. The options follow the speed menu.</template></span>
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
              <SettingSwitch v-model="hoverEnabled" label="Definitions on hover" />
              <label v-if="hasTimings" class="highlight-control">
                <span>Highlight</span>
                <input class="highlight-switch" type="checkbox" role="switch" :checked="highlightEnabled" @change="toggleHighlighting">
                <span class="highlight-track" aria-hidden="true"><span class="highlight-thumb"></span></span>
                <span class="highlight-state" aria-hidden="true">{{ highlightEnabled ? 'On' : 'Off' }}</span>
              </label>
            </ReadingAppearance>
            <ColorFocusPanel :settings="focus" :part-count="focusParts.length" :current-part="currentPart" :has-timings="canSelectWords" />
          </div>
          <div id="panel-passage" role="tabpanel" aria-labelledby="tab-passage" v-show="tab === 'passage'" class="passage-panel passage-frame" :class="focus.on && `tint-${focus.tint}`">
            <PassageText :key="passage.assetVersion" :paragraphs="passage.paragraphs" :tokens="(passage.tokens || []).filter(t => t.paragraphId !== passage.narrationTitle?.id)" :active-token-id="highlightedTokenId" :replay-enabled="!audioUnavailable" :select-action="wordAction === 'say' ? 'hear that word' : 'read from that word'" :focus-paragraph-id="focusParagraphId" :sentence-highlight="focus.on && focus.guide" :reading-token-id="readingTokenId" :definitions-enabled="hoverEnabled" :official-token-ids="officialTokenIds" @define="openCard" @word-enter="keepCard" @word-leave="leaveCard" @replay="selectWord" />
          </div>
          <section v-show="tab === 'vocabulary'" id="panel-vocabulary" class="vocabulary-view" role="tabpanel" aria-labelledby="tab-vocabulary">
            <VocabularyActivity :words="official" :can-hear="canSelectWords" @hear="sayWord" />
            <h2>Words to learn (official)</h2>
            <p v-if="vocabularyStatus" role="status">{{ vocabularyStatus }}</p>
            <p v-else-if="!official.length">This passage has no official word list.</p>
            <VocabularyWord collapsible v-for="entry in official" :key="entry.tokenId" :entry="entry" :saved="isSaved(entry)" :can-hear="canSelectWords" @hear="sayWord" @toggle="toggleWord" />
            <h2>My words (personal)</h2>
            <p v-if="!myWords.length">Add words with the star in a definition card.</p>
            <VocabularyWord collapsible v-for="entry in myWords" :key="entry.word" :entry="entry" saved :can-hear="canSelectWords" @hear="sayWord" @toggle="toggleWord" />
            <small><a href="https://simple.wiktionary.org/" target="_blank" rel="noopener">Definitions from Simple English Wiktionary (CC BY-SA 4.0)</a></small>
          </section>
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
        <button v-if="tab === 'passage' && highlightEnabled && !following && activeTokenId && wordPlacement !== 'visible'" type="button" class="follow-return" @click="resumeFollowing">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path v-if="wordPlacement === 'above'" d="M12 19V5M6 11l6-6 6 6"/><path v-else d="M12 5v14M6 13l6 6 6-6"/></svg>
          Back to where we're reading
        </button>
      </div>
    </main>
    <Teleport to="body"><section v-if="card" ref="cardElement" class="definition-card" :style="cardStyle" role="dialog" aria-label="Word definition" tabindex="-1" @pointerenter="keepCard" @pointerleave="leaveCard" @focusin="keepCard" @focusout="!$event.currentTarget.contains($event.relatedTarget) && leaveCard()">
      <button class="definition-close" aria-label="Close definition" @click="closeCard">×</button>
      <VocabularyWord :entry="card" :saved="isSaved(card)" :can-hear="canSelectWords" @hear="sayWord" @toggle="toggleWord" />
    </section></Teleport>
    <footer>ReadWorks SoundWorks <span>Hackathon reader preview</span></footer>
  </div>
</template>

<style scoped>
.narrated-title { margin: 0 0 14px; }
.narrated-title :deep(.read-along-text) { font-family: inherit; font-size: 29.75px; font-weight: 600; line-height: 1.25; text-align: left; }
</style>
