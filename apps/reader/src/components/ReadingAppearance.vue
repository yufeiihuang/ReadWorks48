<script setup>
import '@fontsource/opendyslexic/latin-400.css';
import '@fontsource/opendyslexic/latin-700.css';

defineProps({ scale: { type: Number, default: 1 }, dyslexia: Boolean });
const emit = defineEmits(['update:scale', 'update:dyslexia']);
</script>

<template>
  <div class="reading-appearance" role="group" aria-label="Reading appearance">
    <div class="text-size" role="group" aria-label="Text size">
      <span>Text size</span>
      <div class="size-stepper">
      <button type="button" aria-label="Decrease font size" :disabled="scale <= 0.75" @click="emit('update:scale', Math.max(0.75, scale - 0.25))">A−</button>
      <output aria-live="polite" aria-label="Font size">{{ Math.round(scale * 100) }}%</output>
      <button type="button" aria-label="Increase font size" :disabled="scale >= 2" @click="emit('update:scale', Math.min(2, scale + 0.25))">A+</button>
      </div>
    </div>
    <label class="highlight-control font-control">
      <span>Dyslexia font</span>
      <input class="highlight-switch" type="checkbox" role="switch" :checked="dyslexia" @change="emit('update:dyslexia', $event.target.checked)">
      <span class="highlight-track" aria-hidden="true"><span class="highlight-thumb"></span></span>
      <span class="highlight-state" aria-hidden="true">{{ dyslexia ? 'On' : 'Off' }}</span>
    </label>
    <slot />
  </div>
</template>

<style scoped>
.reading-appearance { display: flex; align-items: center; flex-wrap: wrap; gap: 12px 28px; font-size: 13px; }
.text-size { display: flex; align-items: center; gap: 12px; color: #52616a; }
.size-stepper { display: inline-flex; align-items: center; border: 1px solid #d9e1e4; border-radius: 6px; background: white; overflow: hidden; }
.text-size button { min-width: 34px; min-height: 34px; padding: 4px 6px; border: 0; background: transparent; color: #345d6b; cursor: pointer; font: inherit; }
.text-size button:hover:not(:disabled) { background: #edf3f5; }
.text-size button:disabled { opacity: .35; cursor: default; }
.text-size button:focus-visible { outline: 2px solid #347b91; outline-offset: -3px; }
.text-size output { min-width: 5ch; text-align: center; font-variant-numeric: tabular-nums; color: #52616a; font-size: 12px; }
.font-control { margin-left: 0; }
@media print { .reading-appearance { display: none; } }
</style>
