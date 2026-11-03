<script setup>
import { computed } from 'vue';

const props = defineProps({
  disabled: { type: Boolean, default: false },
  playing: { type: Boolean, default: false },
  currentTime: { type: Number, default: 0 },
  duration: { type: Number, default: 0 },
  volume: { type: Number, default: 1 },
  playbackRate: { type: Number, default: 1 },
  // Sentence replay needs word timings; hidden/disabled when unavailable.
  canReplaySentence: { type: Boolean, default: false },
});

const emit = defineEmits(['toggle-play', 'restart', 'replay-sentence', 'seek', 'volume-change', 'speed-change']);
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
        class="control-button play has-tooltip"
        type="button"
        :disabled="disabled"
        :aria-label="playing ? 'Pause passage' : 'Play passage'"
        :data-tooltip="playing ? 'Pause' : 'Play'"
        @click="emit('toggle-play')"
      >
        <svg v-if="playing" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14" /></svg>
        <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7z" /></svg>
      </button>
      <button
        class="control-button restart has-tooltip"
        type="button"
        :disabled="disabled"
        aria-label="Restart passage"
        data-tooltip="Restart passage"
        @click="emit('restart')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11a8 8 0 1 1 2 6M4 4v7h7" /></svg>
      </button>
      <button
        v-if="canReplaySentence"
        class="control-button replay-sentence has-tooltip"
        type="button"
        :disabled="disabled"
        aria-label="Replay current sentence"
        data-tooltip="Replay current sentence"
        @click="emit('replay-sentence')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 7H6a3 3 0 0 0-3 3v1a3 3 0 0 0 3 3h3M12 4 8 7l4 3M15 17h3a3 3 0 0 0 3-3v-1a3 3 0 0 0-3-3h-3M12 20l4-3-4-3" /></svg>
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
      <label class="volume-control has-tooltip" data-tooltip="Volume">
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
      <label class="speed-control has-tooltip" data-tooltip="Playback speed">
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

<style scoped>
/* Hover/focus tooltips for the audio controls. Driven by data-tooltip so the
   same label is announced visually; aria-label still carries it to screen
   readers. Shown on hover and on keyboard focus, and suppressed when the
   control is disabled. */
.has-tooltip {
  position: relative;
}

.has-tooltip::after {
  content: attr(data-tooltip);
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%) translateY(-2px);
  z-index: 20;
  padding: 5px 9px;
  border-radius: 6px;
  background: #235b6e; /* matches the existing dark-teal button hover */
  color: #fff;
  font-size: 12px;
  line-height: 1.2;
  white-space: nowrap;
  letter-spacing: normal;
  box-shadow: 0 4px 14px rgb(0 0 0 / 0.18);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease, transform 0.12s ease;
}

/* Small pointer triangle above the bubble. */
.has-tooltip::before {
  content: "";
  position: absolute;
  top: calc(100% + 3px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 20;
  border: 5px solid transparent;
  border-bottom-color: #235b6e;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}

/* Reveal on hover or keyboard focus. :focus-within covers the volume/speed
   labels whose focusable control is a child input/select. */
.has-tooltip:hover::after,
.has-tooltip:focus-visible::after,
.has-tooltip:focus-within::after {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.has-tooltip:hover::before,
.has-tooltip:focus-visible::before,
.has-tooltip:focus-within::before {
  opacity: 1;
}

/* No tooltip when the control is unavailable. */
.has-tooltip:disabled::after,
.has-tooltip:disabled::before {
  content: none;
}

@media (prefers-reduced-motion: reduce) {
  .has-tooltip::after,
  .has-tooltip::before {
    transition: none;
  }
}

@media print {
  .has-tooltip::after,
  .has-tooltip::before {
    display: none;
  }
}
</style>
