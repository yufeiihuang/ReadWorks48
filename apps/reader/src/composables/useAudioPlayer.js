import { onBeforeUnmount, reactive, readonly } from 'vue';

// The one audio element for a passage. The console, word clicks, and highlighting all go
// through this controller, so there is never a second recording or an independent timer.
//
// Hooks for synchronization (SW-06/SW-07):
// - state.currentTime follows the audio clock every animation frame while playing; compare
//   it with timing startMs / 1000 to find the active word.
// - playFrom(seconds) seeks and plays; call it with a word's startMs / 1000 on click.
export function useAudioPlayer() {
  const audio = new Audio();
  audio.preload = 'metadata';

  const state = reactive({
    status: 'empty', // empty | loading | ready | error
    playing: false,
    currentTime: 0,
    duration: 0,
    volume: 1,
    playbackRate: 1,
    error: '',
  });

  let source = '';
  let frame = 0;

  const syncTime = () => { state.currentTime = audio.currentTime; };
  const syncDuration = () => { state.duration = Number.isFinite(audio.duration) ? audio.duration : 0; };
  const tick = () => { syncTime(); frame = requestAnimationFrame(tick); };
  const stopTicking = () => { cancelAnimationFrame(frame); frame = 0; };
  const stopped = () => { state.playing = false; stopTicking(); syncTime(); };

  const listeners = {
    loadedmetadata: () => { syncDuration(); if (state.status === 'loading') state.status = 'ready'; },
    durationchange: syncDuration,
    play: () => { state.playing = true; if (!frame) tick(); },
    pause: stopped,
    ended: stopped,
    seeked: syncTime,
    // Animation frames pause in background tabs; timeupdate keeps the clock moving there.
    timeupdate: syncTime,
    volumechange: () => { state.volume = audio.volume; },
    ratechange: () => { state.playbackRate = audio.playbackRate; },
    error: () => {
      if (!audio.getAttribute('src')) return;
      stopped();
      state.status = 'error';
      state.error = 'The audio could not be loaded.';
    },
  };
  for (const [name, listener] of Object.entries(listeners)) audio.addEventListener(name, listener);

  function load(url) {
    stopTicking();
    Object.assign(state, { playing: false, currentTime: 0, duration: 0, error: '' });
    source = url || '';
    if (!source) {
      audio.removeAttribute('src');
      audio.load();
      state.status = 'empty';
      return;
    }
    state.status = 'loading';
    audio.src = source;
    audio.load();
  }

  async function play() {
    if (state.status === 'empty' || state.status === 'error') return;
    try {
      await audio.play();
      state.error = '';
    } catch (error) {
      // AbortError means a newer pause/seek/load interrupted this play request.
      if (error.name !== 'AbortError') state.error = 'The audio could not start. Press play to try again.';
    }
  }

  function pause() {
    audio.pause();
  }

  function toggle() {
    return audio.paused ? play() : pause();
  }

  function seek(seconds) {
    if (!Number.isFinite(seconds)) return;
    const end = state.duration || Infinity;
    audio.currentTime = Math.min(Math.max(0, seconds), end);
    syncTime();
  }

  function playFrom(seconds) {
    seek(seconds);
    return play();
  }

  function restart() {
    return playFrom(0);
  }

  function setVolume(value) {
    if (Number.isFinite(value)) audio.volume = Math.min(Math.max(0, value), 1);
  }

  function setPlaybackRate(rate) {
    if (!Number.isFinite(rate) || rate <= 0) return;
    // defaultPlaybackRate keeps the chosen speed when a new recording loads.
    audio.defaultPlaybackRate = rate;
    audio.playbackRate = rate;
  }

  function retry() {
    if (source) load(source);
  }

  onBeforeUnmount(() => {
    stopTicking();
    audio.pause();
    for (const [name, listener] of Object.entries(listeners)) audio.removeEventListener(name, listener);
    audio.removeAttribute('src');
    audio.load();
  });

  return {
    state: readonly(state),
    load,
    retry,
    play,
    pause,
    toggle,
    seek,
    playFrom,
    restart,
    setVolume,
    setPlaybackRate,
  };
}
