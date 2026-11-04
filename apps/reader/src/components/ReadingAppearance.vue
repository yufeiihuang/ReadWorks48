<script setup>
import '@fontsource/opendyslexic/latin-400.css';
import '@fontsource/opendyslexic/latin-700.css';

defineProps({ scale: { type: Number, default: 1 }, dyslexia: Boolean });
const emit = defineEmits(['update:scale', 'update:dyslexia']);
const sizes = [0.75, 1, 1.25, 1.5, 1.75, 2];
</script>

<template>
  <div class="reading-appearance" role="group" aria-label="Reading appearance">
    <div class="text-size" role="group" aria-label="Text size">
      <span class="size-label">Text size</span>
      <div class="size-options">
        <label v-for="size in sizes" :key="size" class="size-option" :class="{ selected: scale === size }">
          <input type="radio" name="font-size" :value="size" :checked="scale === size" :aria-label="`${Math.round(size * 100)}% font size`" @change="emit('update:scale', size)">
          <span aria-hidden="true" :style="{ fontSize: `${17 * size}px` }">Aa</span>
        </label>
      </div>
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
.reading-appearance { display: grid; gap: 12px; font-size: 15px; }
.text-size { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px 12px; border: 0; padding: 0; margin: 0; min-width: 0; }
.size-label { white-space: nowrap; }
.size-options { display: flex; align-items: stretch; gap: 0; }
.size-option { position: relative; display: block; text-align: center; flex: 0 0 auto; height: 48px; padding: 0 10px; line-height: 0; border-radius: 5px; color: #345d6b; cursor: pointer; }
.size-option::before { content: ''; display: inline-block; height: 35px; vertical-align: baseline; }
.size-option span { position: relative; z-index: 1; line-height: 1; vertical-align: baseline; pointer-events: none; }
.size-option::after { content: ''; position: absolute; width: 44px; height: 48px; top: 0; left: 50%; transform: translateX(-50%); border-radius: 5px; pointer-events: none; }
.size-option input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
.size-option:hover::after { background: #e8eff2; }
.size-option.selected { color: white; }
.size-option.selected::after { background: var(--teal); }
.size-option:has(input:focus-visible) { outline: 3px solid #db9d22; outline-offset: 2px; }
@media (max-width: 420px) { .size-options { gap: 1px; } .size-option { padding-inline: 7px; } }
@media print { .reading-appearance { display: none; } }
</style>
