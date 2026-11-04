import { ref, watch, nextTick, onBeforeUnmount } from 'vue';
import { wordContext, readMyWords } from '../lib/vocabulary.js';
export function useVocabulary(passage, passageId) {
  const tab = ref('passage'), official = ref([]), officialTokenIds = ref([]), vocabularyStatus = ref('');
  const myWords = ref((() => { try { return readMyWords(localStorage, passageId); } catch { return []; } })());
  const hoverEnabled = ref(true);
  try { hoverEnabled.value = localStorage.getItem('soundworks.definitionsOnHover') !== 'false'; } catch {}
  watch(hoverEnabled, value => { try { localStorage.setItem('soundworks.definitionsOnHover', String(value)); } catch {} if (!value) closeCard(); });
  watch(myWords, value => { try { localStorage.setItem(`soundworks.myWords.${passageId}`, JSON.stringify(value)); } catch {} }, { deep: true });
  const cache = new Map();
  async function entryFor(tokenId) {
    const context = wordContext(passage.value, tokenId);
    if (!context) return null;
    const key = context.word.toLowerCase();
    if (!cache.has(key)) cache.set(key, fetch(`/api/define/${encodeURIComponent(key)}`).then(async response => { if (!response.ok) throw new Error(); return response.json(); }).catch(error => { cache.delete(key); throw error; }));
    try {
      const data = await cache.get(key);
      const sense = data.senses[0];
      return { ...context, lemma: data.lemma, partOfSpeech: sense?.partOfSpeech || '', definition: sense?.definition || (/^[A-Z]/.test(context.word) && context.midSentence ? 'This may be the name of a person or place.' : 'No simple definition was found.'), source: data.source };
    } catch { return { ...context, definition: 'Definitions are temporarily unavailable. Please try again.', unavailable: true }; }
  }
  function isSaved(entry) { return myWords.value.some(item => item.word.toLowerCase() === entry.word.toLowerCase()); }
  function toggleWord(entry) {
    if (entry.unavailable) return;
    myWords.value = isSaved(entry) ? myWords.value.filter(item => item.word.toLowerCase() !== entry.word.toLowerCase()) : [...myWords.value, { ...entry }];
  }
  async function loadVocabulary() {
    vocabularyStatus.value = 'Loading word list…';
    try {
      const response = await fetch(`/api/passages/${encodeURIComponent(passageId)}/vocabulary`);
      if (!response.ok) throw new Error();
      const words = await response.json();
      officialTokenIds.value = words.flatMap(word => word.occurrences.flatMap(item => item.tokenIds));
      const entries = await Promise.all(words.map(word => entryFor(word.occurrences[0].tokenIds[0])));
      official.value = entries.filter(Boolean);
      vocabularyStatus.value = '';
    } catch { vocabularyStatus.value = 'The official word list is temporarily unavailable. Please try again later.'; }
  }
  const card = ref(null), cardElement = ref(null), cardStyle = ref({});
  let closeTimer, origin, request = 0;
  function keepCard() { clearTimeout(closeTimer); }
  function leaveCard() { if (card.value?.keyboard || cardElement.value?.contains(document.activeElement)) return; keepCard(); closeTimer = setTimeout(() => closeCard(), 250); }
  function closeCard() {
    keepCard(); request++;
    const returnFocus = card.value?.keyboard;
    card.value = null;
    if (returnFocus && origin?.isConnected) origin.closest('.read-along-text')?.focus();
  }
  async function openCard({ tokenId, target, keyboard }) {
    keepCard();
    const version = ++request;
    origin = target;
    const rect = target.getBoundingClientRect();
    cardStyle.value = { left: `${Math.max(8, Math.min(rect.left, window.innerWidth - 348))}px`, top: `${Math.max(8, Math.min(rect.bottom + 8, window.innerHeight - 360))}px` };
    card.value = { ...wordContext(passage.value, tokenId), definition: 'Loading definition…', keyboard, unavailable: true };
    await nextTick();
    if (keyboard) cardElement.value?.focus();
    const entry = await entryFor(tokenId);
    if (version === request && card.value) card.value = { ...entry, keyboard };
  }
  function escape(event) { if (event.key === 'Escape' && card.value) { event.preventDefault(); closeCard(); } }
  document.addEventListener('keydown', escape);
  watch(tab, closeCard);
  onBeforeUnmount(() => { keepCard(); document.removeEventListener('keydown', escape); });
  function tabKey(event) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    tab.value = event.key === 'Home' ? 'passage' : event.key === 'End' ? 'vocabulary' : tab.value === 'passage' ? 'vocabulary' : 'passage';
    nextTick(() => document.getElementById(`tab-${tab.value}`)?.focus());
  }
  return { tab, official, officialTokenIds, vocabularyStatus, myWords, hoverEnabled, isSaved, toggleWord, loadVocabulary, card, cardElement, cardStyle, openCard, closeCard, keepCard, leaveCard, tabKey };
}
