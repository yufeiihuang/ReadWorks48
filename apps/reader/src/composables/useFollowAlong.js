import { nextTick, onBeforeUnmount, onMounted, ref, toValue, watch } from 'vue';
import { followScrollDelta, isManualScrollKey, wordPlacement } from '../lib/followAlong.js';

// Keeps the spoken word on screen while the passage plays. Any manual scroll (trackpad/wheel,
// touch, scroll keys, scrollbar) pauses following so a student can look around; resume() turns
// it back on. Starting playback resumes it too. While frozen() is true (a single word playing on
// its own) the page holds still and playback changes don't count as the student pressing play.
export function useFollowAlong(activeTokenId, playing, { topInset = () => 0, frozen = () => false } = {}) {
  const following = ref(true);
  const placement = ref('visible');
  let frame = 0;

  const viewport = () => ({ height: window.innerHeight, topInset: topInset() });
  const activeWord = () => {
    const id = toValue(activeTokenId);
    return id ? document.querySelector(`[data-token-id="${CSS.escape(id)}"]`) : null;
  };

  function follow() {
    const word = activeWord();
    if (!word) return;
    const delta = followScrollDelta(word.getBoundingClientRect(), viewport());
    if (!delta) return;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollBy({ top: delta, behavior: reduceMotion ? 'auto' : 'smooth' });
  }

  function measure() {
    frame = 0;
    const word = activeWord();
    placement.value = word ? wordPlacement(word.getBoundingClientRect(), viewport()) : 'visible';
  }

  function resume() {
    following.value = true;
    nextTick(follow);
  }

  function pause() {
    if (!following.value) return;
    following.value = false;
    measure();
  }

  const listeners = {
    wheel: event => { if (event.deltaY && !event.ctrlKey) pause(); },
    touchmove: pause,
    keydown: event => { if (isManualScrollKey(event)) pause(); },
    pointerdown: event => {
      const root = document.documentElement;
      if (event.target === root && event.clientX >= root.clientWidth) pause();
    },
    scroll: () => { if (!following.value && !frame) frame = requestAnimationFrame(measure); },
  };

  watch(activeTokenId, () => (following.value && !frozen() ? follow() : measure()), { flush: 'post' });
  watch(playing, (now, before) => { if (now && !before && !frozen()) resume(); });

  onMounted(() => {
    for (const [name, listener] of Object.entries(listeners)) window.addEventListener(name, listener, { passive: true });
  });
  onBeforeUnmount(() => {
    cancelAnimationFrame(frame);
    for (const [name, listener] of Object.entries(listeners)) window.removeEventListener(name, listener);
  });

  return { following, placement, resume };
}
