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
import ReadingSettingsMenu from './components/ReadingSettingsMenu.vue';
import readWorksLogo from './assets/readworks-logo.svg';
import SpeedTip from './components/SpeedTip.vue';
import { findActiveToken, findLastStartedToken, findWordRange } from './lib/wordTiming.js';
import { loadGeneratedPassage, loadLatestGeneratedPassage, wordClipUrl } from './lib/generatedPassage.js';
import { loadGradeId, suggestSpeed } from './lib/speedSuggestion.js';
import { useAudioPlayer } from './composables/useAudioPlayer.js';
import { useFollowAlong } from './composables/useFollowAlong.js';
import { colorFocusDefaults, useColorFocus } from './composables/useColorFocus.js';
// Playback test passage with ReadWorks' existing recording; open /?passage=pride-and-prejudice.
// Loaded in the reader until the API passage routes (SW-10) serve more than the demo fixture.
const referencePassages = { 'pride-and-prejudice': () => import('../../../shared/fixtures/pride-and-prejudice.json') };
// Reviewed demo recordings. A published current.json never replaces these; ?latest=1 previews it
// (falling back to the pin), and promoting it means updating the pin here.
const pinnedManifests = {
  'pride-and-prejudice': '/generated/pride-and-prejudice/52ccc5bde7a7f306f197-305603da9965/manifest.json',
  demo: '/generated/demo/adbeeb10a403af4424e1-4386b7353988/manifest.json',
  'park-caretaker': '/generated/park-caretaker/human-712a36cf65895354e6b551d5/manifest.json',
};
const audioAllowed = new URLSearchParams(window.location.search).get('audio') !== 'off';
const passageId = new URLSearchParams(window.location.search).get('passage') || 'demo';
const demoPassages = [
  { id: 'demo', title: 'A Morning in the Garden' },
  { id: 'park-caretaker-qa', title: "Let's Meet a Park Caretaker" },
  { id: 'pride-and-prejudice', title: 'Excerpt from Pride and Prejudice' },
];
function openTeacher() { window.location.assign(`?view=teacher&passage=${encodeURIComponent(passageId)}`); }
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
const audioUnavailable = computed(() => !audioAllowed || ['empty', 'error'].includes(player.state.status));
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
// The audio controls only show on the Passage tab, so nothing may keep playing without them.
watch(tab, name => { if (name !== 'passage') player.pause(); });
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
function resetReadingSettings() {
  fontScale.value = 1;
  dyslexiaFont.value = false;
  Object.assign(focus, colorFocusDefaults);
}
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
const canHearWord = tokenId => Boolean(wordClipUrl(passage.value, tokenId)
  || Number.isFinite(passage.value?.timings?.find(item => item.tokenId === tokenId)?.startMs));
function restartPassage() { noteJump(); resumeFollowing(); player.restart(); }
function seekPassage(seconds) { noteJump(); resumeFollowing(); player.seek(seconds); }
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
    if (audioAllowed) player.load(passage.value.audio?.url);
    if (passage.value.audio?.url) loadGradeId(passage.value).then(id => { gradeId.value = id; });
  } catch (cause) { error.value = cause.message; }
});
</script>

<template>
  <div :class="{ projector, 'color-focus': focus.on }" :style="readingStyle">
    <header class="site-header">
      <a class="brand" href="/" aria-label="ReadWorks SoundWorks home"><img :src="readWorksLogo" alt="" width="190" height="29"></a>
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
          <div class="narrated-title" v-if="passage.narrationTitle"><PassageText heading :paragraphs="[passage.narrationTitle]" :tokens="(passage.tokens || []).filter(t => t.paragraphId === passage.narrationTitle.id)" :active-token-id="highlightedTokenId" :replay-enabled="!audioUnavailable" :definitions-enabled="hoverEnabled" :official-token-ids="officialTokenIds" @define="openCard" @word-enter="keepCard" @word-leave="leaveCard" :can-hear="canHearWord" @replay="replayWord" @hear="sayWord" /></div>
          <h1 v-else>{{ passage.title }}</h1>
          <div class="article-actions" aria-label="Passage actions">
            <button @click="openTeacher">Assign</button>
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
          <AudioConsole v-if="audioAllowed" v-show="tab === 'passage'"
            :disabled="audioUnavailable"
            :playing="player.state.playing"
            :current-time="player.state.currentTime"
            :duration="player.state.duration"
            :volume="player.state.volume"
            :playback-rate="player.state.playbackRate"
            :speed-tip-open="Boolean(speedSuggestion)"
            @toggle-play="player.toggle"
            @restart="restartPassage"
            @seek="seekPassage"
            @volume-change="player.setVolume"
            @speed-change="changeSpeed"
          >
            <template #speed-tip>
              <SpeedTip v-if="speedSuggestion" :question="speedSuggestion.question" :speed="speedSuggestion.speed" @accept="acceptSpeedSuggestion" @dismiss="answerSpeedTip" />
            </template>
            <template #settings>
              <ReadingSettingsMenu @reset="resetReadingSettings">
                <ReadingAppearance v-model:scale="fontScale" v-model:dyslexia="dyslexiaFont" />
                <SettingSwitch v-model="hoverEnabled" label="Definitions on hover" />
                <ColorFocusPanel :settings="focus" :has-timings="canSelectWords" />
              </ReadingSettingsMenu>
            </template>
            <template #options>
            <label v-if="hasTimings" class="highlight-control">
              <span>Highlight</span>
              <input class="highlight-switch" type="checkbox" role="switch" :checked="highlightEnabled" @change="toggleHighlighting">
              <span class="highlight-track" aria-hidden="true"><span class="highlight-thumb"></span></span>
              <span class="highlight-state" aria-hidden="true">{{ highlightEnabled ? 'On' : 'Off' }}</span>
            </label>
            <p v-if="focus.on && canSelectWords && focusParts.length > 1" class="part-progress">
              <span>Part {{ currentPart + 1 }} of {{ focusParts.length }}</span>
              <span v-if="focusParts.length <= 20" class="part-dots" aria-hidden="true"><i v-for="n in focusParts.length" :key="n" :class="{ done: n - 1 < currentPart, current: n - 1 === currentPart }"></i></span>
            </p>
            </template>
          </AudioConsole>
          <!-- Screen-reader announcements that must not affect layout. The paragraph-pause
               message lives here (not in the in-flow .audio-status) so showing/hiding it never
               shifts the passage; the visible pause UI is the fixed-position "Keep going" button. -->
          <span class="sr-only" role="status">
            <template v-if="tab === 'passage' && speedSuggestion">{{ speedSuggestion.question }} Change to {{ speedSuggestion.speed }}× speed for better listening. The options follow the speed menu.</template>
            <template v-else-if="finishedPart !== null">Part {{ finishedPart + 1 }} of {{ focusParts.length }} done. Select Keep going when you're ready.</template>
          </span>
          <p v-if="audioAllowed && tab === 'passage' && (generationWarning || audioUnavailable || player.state.error || player.state.status === 'loading' || player.state.buffering || hasIncompleteTimings || !hasTimings)" class="audio-status">
            <span role="status">
              <template v-if="generationWarning">{{ generationWarning }}</template>
              <template v-else-if="player.state.status === 'empty'">Audio isn't ready for this passage yet. You can still read it.</template>
              <template v-else-if="player.state.status === 'error' || player.state.error">{{ player.state.error }}</template>
              <template v-else-if="player.state.status === 'loading'">Loading audio…</template>
              <template v-else-if="player.state.buffering">Buffering audio…</template>
              <template v-else-if="hasIncompleteTimings">Some words are not available for highlighting.</template>
              <template v-else>Press play to listen. Word highlighting is not available for this passage.</template>
            </span>
            <button v-if="player.state.status === 'error'" type="button" @click="player.retry">Try again</button>
          </p>
          <div v-if="!audioAllowed" class="reading-settings"><ReadingAppearance v-model:scale="fontScale" v-model:dyslexia="dyslexiaFont" /><SettingSwitch v-model="hoverEnabled" label="Definitions on hover" /></div>
          <div id="panel-passage" role="tabpanel" aria-labelledby="tab-passage" v-show="tab === 'passage'" class="passage-panel passage-frame" :class="focus.on && `tint-${focus.tint}`">
            <PassageText :key="passage.assetVersion" :paragraphs="passage.paragraphs" :tokens="(passage.tokens || []).filter(t => t.paragraphId !== passage.narrationTitle?.id)" :active-token-id="highlightedTokenId" :replay-enabled="!audioUnavailable" :can-hear="canHearWord" :focus-paragraph-id="focusParagraphId" :sentence-highlight="focus.on && focus.guide" :reading-token-id="readingTokenId" :definitions-enabled="hoverEnabled" :official-token-ids="officialTokenIds" @define="openCard" @word-enter="keepCard" @word-leave="leaveCard" @replay="replayWord" @hear="sayWord" />
          </div>
          <section v-show="tab === 'vocabulary'" id="panel-vocabulary" class="vocabulary-view" role="tabpanel" aria-labelledby="tab-vocabulary">
            <VocabularyActivity :words="official" :can-hear="canSelectWords" @hear="sayWord" />
            <h2>Passage words</h2>
            <p class="vocabulary-description">Words to explore in this reading.</p>
            <p v-if="vocabularyStatus" role="status">{{ vocabularyStatus }}</p>
            <p v-else-if="!official.length">This passage has no word list.</p>
            <VocabularyWord collapsible v-for="entry in official" :key="entry.tokenId" :entry="entry" :saved="isSaved(entry)" :can-hear="canSelectWords" @hear="sayWord" @toggle="toggleWord" />
            <h2>My words</h2>
            <p class="vocabulary-description">Words you’ve saved.</p>
            <p v-if="!myWords.length">Add words with the star in a definition card.</p>
            <VocabularyWord collapsible v-for="entry in myWords" :key="entry.word" :entry="entry" saved :can-hear="canSelectWords" @hear="sayWord" @toggle="toggleWord" />
          </section>
          <p class="passage-credit"><template v-if="isReadWorks || isReference">Passage from <a v-if="passage.source?.url" :href="passage.source.url">ReadWorks</a><template v-else>ReadWorks</template><template v-if="passage.source?.author"> · {{ passage.source.author }}</template></template><template v-else>Original demonstration passage · SoundWorks</template></p>
        </article>
        <aside class="details" aria-labelledby="details-title">
          <h2 id="details-title">DETAILS</h2>
          <ul><li>Words: {{ wordCount }}</li><li>Language: English</li><li v-if="!isReadWorks">Fiction</li></ul>
          <h3 v-if="audioAllowed">Audio</h3>
          <p v-if="audioAllowed">{{ hasAudio ? 'Available' : 'Not available yet' }}</p>
          <p v-if="audioAllowed && hasIncompleteTimings" class="muted">Some words are not highlighted.</p>
          <h3>About this passage</h3><p>{{ isReadWorks || isReference ? 'A reading passage from ReadWorks.' : 'Original sample text for the SoundWorks reader preview.' }}</p>
        </aside>
      </div>
      <div class="floating-actions">
        <button v-if="tab === 'passage' && finishedPart !== null" type="button" class="part-break" @click="keepGoing">
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
