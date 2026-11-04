import { onBeforeUnmount, reactive, readonly } from 'vue';

// The one audio element for a passage. The console, word clicks, and highlighting all go
// through this controller, so there is never a second recording or an independent timer.
//
// Hooks for synchronization (SW-06/SW-07):
// - state.currentTime follows the audio clock every animation frame while playing; compare
//   it with timing startMs / 1000 to find the active word.
// - playFrom(seconds) seeks and plays; call it with a word's startMs / 1000 on click.
// - playWord(start, end) plays one word on its own, then returns to where the passage was and
//   stays paused there, even if the passage had been playing (QA-2); the student presses play to
//   continue. state.wordOnly is true until that return completes. This slices the passage
//   recording, so it's the fallback for passages without word clips.
// - playClip(url) plays a separately recorded word (QA-1) on a small second element. The passage
//   pauses where it is and stays paused. state.wordOnly is true while the clip plays.
export function useAudioPlayer() {
  const audio = new Audio();
  audio.preload = 'auto';
  // Keep the one media element in the DOM for browser media lifecycle and diagnostics.
  audio.hidden = true;
  audio.dataset.soundworksAudio = 'true';
  document.body.appendChild(audio);
  // Word clips are whole files, so they get their own element; the passage keeps its place.
  const clip = new Audio();
  clip.preload = 'auto';
  clip.hidden = true;
  clip.dataset.soundworksWordClip = 'true';
  document.body.appendChild(clip);

  const state = reactive({
    status: 'empty', // empty | loading | ready | error
    playing: false,
    buffering: false,
    currentTime: 0,
    duration: 0,
    volume: 1,
    playbackRate: 1,
    wordOnly: false,
    error: '',
  });

  let source = '';
  let frame = 0;
  let word = null; // { end, returnTo } while playWord is playing one word
  let wordTimer = 0;
  let clipRequest = 0; // increases on every new clip or cancel, so a stale clip's events are ignored

  const syncTime = () => { state.currentTime = audio.currentTime; };
  const syncDuration = () => { state.duration = Number.isFinite(audio.duration) ? audio.duration : 0; };
  const tick = () => { syncTime(); checkWordEnd(); frame = requestAnimationFrame(tick); };
  const stopTicking = () => { cancelAnimationFrame(frame); frame = 0; };
  const stopped = () => { state.buffering = false; state.playing = false; stopTicking(); syncTime(); };

  const listeners = {
    loadedmetadata: () => { syncDuration(); if (state.status === 'loading') state.status = 'ready'; },
    durationchange: syncDuration,
    play: () => { state.playing = true; if (!frame) tick(); },
    playing: () => { state.buffering = false; checkWordEnd(); },
    waiting: () => { state.buffering = !audio.paused; },
    canplay: () => { state.buffering = false; },
    pause: () => {
      // Reaching the end of the recording finishes a word; any other pause cancels it in place.
      if (word) { if (audio.ended) finishWord(); else endWord(); }
      stopped();
    },
    ended: stopped,
    seeked: syncTime,
    // Animation frames pause in background tabs; timeupdate keeps the clock moving there.
    timeupdate: () => { syncTime(); checkWordEnd(); },
    volumechange: () => { state.volume = audio.volume; },
    ratechange: () => { state.playbackRate = audio.playbackRate; },
    error: () => {
      if (!audio.getAttribute('src')) return;
      stopped();
      state.status = 'error';
      state.error = audio.error?.code === 2
        ? 'The audio download was interrupted. Try again.'
        : audio.error?.code === 3
          ? 'The recording could not be decoded. Try again.'
          : 'The audio could not be loaded. Try again.';
    },
  };
  for (const [name, listener] of Object.entries(listeners)) audio.addEventListener(name, listener);

  function load(url) {
    endWord();
    stopTicking();
    Object.assign(state, { buffering: false, playing: false, currentTime: 0, duration: 0, error: '' });
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

  async function startPlayback() {
    if (state.status === 'empty' || state.status === 'error') return;
    try {
      await audio.play();
      state.error = '';
    } catch (error) {
      // AbortError means a newer pause/seek/load interrupted this play request.
      if (error.name !== 'AbortError') state.error = 'The audio could not start. Press play to try again.';
    }
  }

  function seekTo(seconds) {
    if (!Number.isFinite(seconds)) return;
    const end = state.duration || Infinity;
    audio.currentTime = Math.min(Math.max(0, seconds), end);
    syncTime();
  }

  // Every student action other than playWord cancels a word in progress and stays where it is.
  function play() {
    endWord();
    return startPlayback();
  }

  function pause() {
    endWord();
    audio.pause();
  }

  function toggle() {
    return audio.paused ? play() : pause();
  }

  function seek(seconds) {
    endWord();
    seekTo(seconds);
  }

  function playFrom(seconds) {
    seek(seconds);
    return play();
  }

  function playWord(start, end) {
    if (state.status === 'empty' || state.status === 'error' || !(end > start)) return;
    // Tapping another word mid-word keeps the original place to return to.
    const returnTo = word ? word.returnTo : audio.currentTime;
    stopClip();
    clearTimeout(wordTimer);
    word = { end, returnTo };
    state.wordOnly = true;
    seekTo(start);
    if (audio.paused) return startPlayback();
    checkWordEnd();
  }

  // Stops at the word's end using the audio clock: animation frames and timeupdate check it,
  // and a timer aimed at the remaining duration catches the end between frames.
  function checkWordEnd() {
    if (!word) return;
    clearTimeout(wordTimer);
    const remaining = (word.end - audio.currentTime) / (audio.playbackRate || 1);
    if (remaining <= 0.005) { finishWord(); return; }
    if (!audio.paused) wordTimer = setTimeout(checkWordEnd, Math.max(5, remaining * 1000 - 5));
  }

  // QA-2: the passage never restarts on its own after a single word; it waits paused at its place.
  function finishWord() {
    const { returnTo } = word;
    word = null;
    clearTimeout(wordTimer);
    audio.pause();
    seekTo(returnTo);
    // Released a moment later so watchers see the return as part of the word, not a new seek/play.
    setTimeout(() => { if (!word) state.wordOnly = false; });
  }

  // Resolves true once the clip starts, or false if it couldn't play (the caller can fall back).
  async function playClip(url) {
    if (state.status === 'empty' || state.status === 'error' || !url) return false;
    if (word) endWord();
    const request = ++clipRequest;
    if (!audio.paused) audio.pause();
    state.wordOnly = true;
    clip.volume = audio.volume;
    clip.defaultPlaybackRate = audio.playbackRate;
    clip.playbackRate = audio.playbackRate;
    clip.src = url;
    try {
      await clip.play();
      return true;
    } catch (error) {
      if (request === clipRequest) state.wordOnly = false;
      // AbortError means a newer clip or another action replaced this one; nothing to fall back to.
      return error.name === 'AbortError';
    }
  }

  function stopClip() {
    clipRequest += 1;
    if (!clip.paused) clip.pause();
  }

  const clipDone = () => { state.wordOnly = false; };
  clip.addEventListener('ended', clipDone);
  clip.addEventListener('error', clipDone);

  function endWord() {
    stopClip();
    if (!word && !state.wordOnly) return;
    word = null;
    clearTimeout(wordTimer);
    state.wordOnly = false;
  }

  function restart() {
    return playFrom(0);
  }

  function setVolume(value) {
    if (Number.isFinite(value)) clip.volume = audio.volume = Math.min(Math.max(0, value), 1);
  }

  function setPlaybackRate(rate) {
    if (!Number.isFinite(rate) || rate <= 0) return;
    // defaultPlaybackRate keeps the chosen speed when a new recording loads.
    audio.defaultPlaybackRate = rate;
    audio.playbackRate = rate;
    clip.defaultPlaybackRate = rate;
    clip.playbackRate = rate;
  }

  function retry() {
    if (source) { load(source); return play(); }
  }

  onBeforeUnmount(() => {
    endWord();
    stopTicking();
    audio.pause();
    for (const [name, listener] of Object.entries(listeners)) audio.removeEventListener(name, listener);
    audio.removeAttribute('src');
    audio.load();
    audio.remove();
    clip.removeEventListener('ended', clipDone);
    clip.removeEventListener('error', clipDone);
    clip.removeAttribute('src');
    clip.load();
    clip.remove();
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
    playWord,
    playClip,
    restart,
    setVolume,
    setPlaybackRate,
  };
}
