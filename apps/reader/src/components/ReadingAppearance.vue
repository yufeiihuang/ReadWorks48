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
    <slot />
  </div>
</template>

<style scoped>
.reading-appearance { display: flex; align-items: center; flex-wrap: wrap; gap: 12px 28px; font-size: 13px; }
.text-size { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; color: #52616a; border: 0; padding: 0; margin: 0; min-width: 0; }
.size-label { white-space: nowrap; }
.size-options { display: flex; align-items: stretch; gap: 3px; }
.size-option { position: relative; display: block; text-align: center; width: 52px; flex: 0 0 52px; height: 48px; padding: 0 5px; line-height: 0; border-radius: 5px; color: #345d6b; cursor: pointer; }
.size-option::before { content: ''; display: inline-block; height: 35px; vertical-align: baseline; }
.size-option span { line-height: 1; vertical-align: baseline; }
.size-option input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
.size-option:hover { background: #e8eff2; }
.size-option.selected { background: #347b91; color: white; }
.size-option:has(input:focus-visible) { outline: 3px solid #db9d22; outline-offset: 2px; }
@media (max-width: 420px) { .size-options { gap: 1px; } .size-option { width: 38px; flex-basis: 38px; padding-inline: 0; } }
.font-control { margin-left: 0; }
@media print { .reading-appearance { display: none; } }
</style>
