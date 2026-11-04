import { computed, reactive, ref, watch } from 'vue';
import { crossedPartStart, partIndexAt, partStarts } from '../lib/readingParts.js';

export const tints = ['blue', 'green', 'cream', 'none'];
const storageKey = 'soundworks.colorFocus';
const defaults = { on: false, tint: 'blue', guide: true, dim: true, pauseParts: true };

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '{}');
    const settings = { ...defaults };
    for (const key of Object.keys(defaults)) if (typeof saved[key] === typeof defaults[key]) settings[key] = saved[key];
    if (!tints.includes(settings.tint)) settings.tint = defaults.tint;
    return settings;
  } catch { return { ...defaults }; }
}

// Color Focus settings (remembered per browser) and reading in parts. With pauseParts on, playback
// stops where the next paragraph begins and waits for keepGoing(). Only playback reaching that
// point by itself counts: call jumped() before a student's own seek (word, restart, sentence
// replay, progress bar) so moving across a paragraph never reads as finishing one.
export function useColorFocus(passage, player) {
  const settings = reactive(loadSettings());
  watch(settings, value => { try { localStorage.setItem(storageKey, JSON.stringify(value)); } catch {} });

  const parts = computed(() => partStarts(passage.value?.tokens || [], passage.value?.timings || []));
  const currentPart = computed(() => partIndexAt(parts.value, player.state.currentTime));
  const finishedPart = ref(null);
  let skipNextMove = false;

  watch(() => player.state.currentTime, (now, before) => {
    if (skipNextMove || player.state.wordOnly) { skipNextMove = false; return; }
    if (!settings.on || !settings.pauseParts || !player.state.playing || now - before > 1) return;
    const next = crossedPartStart(parts.value, before, now);
    if (next < 0) return;
    player.pause();
    skipNextMove = true;
    // Back to the exact start so "Keep going" begins the next paragraph from its first word.
    player.seek(parts.value[next].start);
    finishedPart.value = next - 1;
  });
  // Hearing one word during a break keeps the break; any other playback ends it.
  watch(() => player.state.playing, playing => { if (playing && !player.state.wordOnly) finishedPart.value = null; });
  watch(() => settings.on && settings.pauseParts, enabled => { if (!enabled) finishedPart.value = null; });

  function jumped() {
    skipNextMove = true;
    finishedPart.value = null;
  }

  function keepGoing() {
    finishedPart.value = null;
    return player.play();
  }

  return { settings, parts, currentPart, finishedPart, jumped, keepGoing };
}
