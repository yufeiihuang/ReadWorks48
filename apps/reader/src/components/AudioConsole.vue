<script setup>
import { computed } from 'vue';

const props = defineProps({
  disabled: { type: Boolean, default: false },
  playing: { type: Boolean, default: false },
  currentTime: { type: Number, default: 0 },
  duration: { type: Number, default: 0 },
  volume: { type: Number, default: 1 },
  playbackRate: { type: Number, default: 1 },
});

const emit = defineEmits(['toggle-play', 'restart', 'seek', 'volume-change', 'speed-change']);
const safeDuration = computed(() => Number.isFinite(props.duration) ? Math.max(0, props.duration) : 0);
const safeCurrentTime = computed(() => Number.isFinite(props.currentTime)
  ? Math.min(Math.max(0, props.currentTime), safeDuration.value)
  : 0);

function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const totalSeconds = Math.floor(seconds);
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, '0')}`;
}
</script>

<template>
  <section class="audio-toolbar" aria-label="Passage audio controls">
    <div class="audio-player">
      <button
        class="control-button play"
        type="button"
        :disabled="disabled"
        :aria-label="playing ? 'Pause passage' : 'Play passage'"
        @click="emit('toggle-play')"
      >
        <svg v-if="playing" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14" /></svg>
        <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7z" /></svg>
      </button>
      <button
        class="control-button restart"
        type="button"
        :disabled="disabled"
        aria-label="Restart passage"
        @click="emit('restart')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11a8 8 0 1 1 2 6M4 4v7h7" /></svg>
      </button>
      <span class="audio-time">{{ formatTime(safeCurrentTime) }} / {{ safeDuration ? formatTime(safeDuration) : '--:--' }}</span>
      <input
        class="audio-progress"
        type="range"
        min="0"
        :max="Math.max(safeDuration, 1)"
        step="0.1"
        :value="safeCurrentTime"
        :disabled="disabled || !safeDuration"
        aria-label="Audio position"
        :aria-valuetext="`${formatTime(safeCurrentTime)} of ${safeDuration ? formatTime(safeDuration) : 'unknown duration'}`"
        @input="emit('seek', Number($event.target.value))"
      />
      <label class="volume-control">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4zM16 8c3 2 3 6 0 8M19 5c5 4 5 10 0 14" /></svg>
        <span class="sr-only">Volume</span>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          :value="volume"
          :disabled="disabled"
          aria-label="Volume"
          @input="emit('volume-change', Number($event.target.value))"
        />
      </label>
      <label class="speed-control">
        <span>Speed</span>
        <select
          :value="playbackRate"
          :disabled="disabled"
          aria-label="Playback speed"
          @change="emit('speed-change', Number($event.target.value))"
        >
          <option :value="0.75">0.75×</option>
          <option :value="1">1×</option>
          <option :value="1.25">1.25×</option>
          <option :value="1.5">1.5×</option>
          <option :value="2">2×</option>
        </select>
      </label>
    </div>
  </section>
</template>
