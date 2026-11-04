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
      <button type="button" aria-label="Decrease font size" :disabled="scale <= 0.75" @click="emit('update:scale', Math.max(0.75, scale - 0.25))">A−</button>
      <output aria-live="polite" aria-label="Font size">{{ Math.round(scale * 100) }}%</output>
      <button type="button" aria-label="Increase font size" :disabled="scale >= 2" @click="emit('update:scale', Math.min(2, scale + 0.25))">A+</button>
    </div>
    <label class="highlight-control font-control">
      <span>Dyslexia font</span>
      <input class="highlight-switch" type="checkbox" role="switch" :checked="dyslexia" @change="emit('update:dyslexia', $event.target.checked)">
      <span class="highlight-track" aria-hidden="true"><span class="highlight-thumb"></span></span>
      <span class="highlight-state" aria-hidden="true">{{ dyslexia ? 'On' : 'Off' }}</span>
    </label>
  </div>
</template>

<style scoped>
.reading-appearance { display: flex; align-items: center; flex-wrap: wrap; gap: 16px 24px; margin: 0 14px 24px; font-size: 13px; }
.text-size { display: flex; align-items: center; gap: 10px; }
.text-size button { min-width: 36px; min-height: 36px; padding: 4px 8px; border: 1px solid #a9bac2; border-radius: 4px; background: white; color: #344048; cursor: pointer; font: inherit; }
.text-size button:disabled { opacity: .4; cursor: default; }
.text-size button:focus-visible { outline: 3px solid #e9bd43; outline-offset: 3px; }
.text-size output { min-width: 4ch; text-align: center; font-variant-numeric: tabular-nums; }
.font-control { margin-left: 0; }
@media print { .reading-appearance { display: none; } }
</style>
