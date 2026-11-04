<script setup>
import { tints } from '../composables/useColorFocus.js';
// Settings strip shown while Color Focus is on. `settings` is the composable's reactive settings
// object; the strip edits it in place and the composable remembers the choices.
defineProps({
  settings: { type: Object, required: true },
  partCount: { type: Number, default: 0 },
  currentPart: { type: Number, default: 0 },
  hasTimings: { type: Boolean, default: false },
});
const tintLabels = { blue: 'Blue', green: 'Green', cream: 'Cream', none: 'None' };
</script>

<template>
  <section class="color-focus-panel" aria-label="Color Focus settings">
    <fieldset class="tint-choice">
      <legend>Color</legend>
      <label v-for="tint in tints" :key="tint" :class="[`swatch-${tint}`, { selected: settings.tint === tint }]">
        <input v-model="settings.tint" type="radio" name="color-focus-tint" :value="tint"><span class="swatch" aria-hidden="true"></span>{{ tintLabels[tint] }}
      </label>
    </fieldset>
    <template v-if="hasTimings">
      <label class="focus-option"><input v-model="settings.guide" type="checkbox">Highlight sentence</label>
      <label class="focus-option"><input v-model="settings.dim" type="checkbox">Dim other paragraphs</label>
      <label class="focus-option"><input v-model="settings.pauseParts" type="checkbox">Pause after each paragraph</label>
      <p v-if="partCount > 1" class="part-progress">
        <span>Part {{ currentPart + 1 }} of {{ partCount }}</span>
        <span v-if="partCount <= 20" class="part-dots" aria-hidden="true"><i v-for="n in partCount" :key="n" :class="{ done: n - 1 < currentPart, current: n - 1 === currentPart }"></i></span>
      </p>
    </template>
  </section>
</template>

<style scoped>
.color-focus-panel { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px; margin: -12px 14px 22px; padding: 12px 14px; border: 1px solid #dce2e4; border-radius: 14px; background: #f8fafa; font-size: 13px; color: #52616a; }
.tint-choice { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; border: 0; margin: 0; padding: 0; }
.tint-choice legend { float: left; padding: 0; margin-right: 4px; font-weight: 600; color: #344048; }
.tint-choice label { position: relative; display: inline-flex; align-items: center; gap: 6px; min-height: 34px; padding: 3px 12px 3px 6px; border: 1px solid #c8d2d6; border-radius: 17px; background: white; color: #344048; cursor: pointer; }
.tint-choice label.selected { border-color: var(--teal); box-shadow: 0 0 0 2px var(--teal); }
.tint-choice input, .focus-option input { accent-color: var(--teal); }
.tint-choice input { position: absolute; opacity: 0; pointer-events: none; }
.tint-choice label:has(input:focus-visible) { outline: 3px solid #db9d22; outline-offset: 2px; }
.swatch { width: 22px; height: 22px; border-radius: 50%; border: 1px solid rgb(0 0 0 / .12); }
.swatch-blue .swatch { background: #dbe8f5; }
.swatch-green .swatch { background: #dcede2; }
.swatch-cream .swatch { background: #f5eed8; }
.swatch-none .swatch { background: linear-gradient(135deg, white 45%, #c8d2d6 45%, #c8d2d6 55%, white 55%); }
.focus-option { display: inline-flex; align-items: center; gap: 6px; min-height: 34px; cursor: pointer; }
.focus-option input { width: 18px; height: 18px; margin: 0; }
.focus-option input:focus-visible { outline: 3px solid #db9d22; outline-offset: 2px; }
.part-progress { display: flex; align-items: center; gap: 10px; margin: 0 0 0 auto; font-weight: 600; color: #344048; }
.part-dots { display: inline-flex; gap: 5px; }
.part-dots i { width: 10px; height: 10px; border-radius: 50%; background: #d3dadd; }
.part-dots i.done { background: var(--teal); }
.part-dots i.current { background: #f0a92b; box-shadow: 0 0 0 2px #fde3b5; }
@media (max-width: 760px) { .color-focus-panel { margin: -10px 0 20px; } .part-progress { margin-left: 0; } }
@media print { .color-focus-panel { display: none; } }
</style>
