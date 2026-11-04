<script setup>
import { tints } from '../composables/useColorFocus.js';
import SettingSwitch from './SettingSwitch.vue';
// The Color Focus section at the bottom of the reading settings: its on/off switch, and while it's
// on, its options. `settings` is the composable's reactive settings object; the section edits it
// in place and the composable remembers the choices. Styled like the rest of the panel: choices
// look like the text size options and on/off options are the panel's switches.
defineProps({
  settings: { type: Object, required: true },
  partCount: { type: Number, default: 0 },
  currentPart: { type: Number, default: 0 },
  hasTimings: { type: Boolean, default: false },
});
const tintLabels = { blue: 'Blue', green: 'Green', cream: 'Cream', none: 'None' };
</script>

<template>
  <div class="color-focus-settings" role="group" aria-label="Color Focus settings">
    <div class="focus-row">
      <SettingSwitch v-model="settings.on" label="Color Focus" />
      <fieldset v-if="settings.on" class="tint-choice">
        <legend>Color</legend>
        <div class="tint-options">
          <label v-for="tint in tints" :key="tint" class="tint-option" :class="[`swatch-${tint}`, { selected: settings.tint === tint }]">
            <input v-model="settings.tint" type="radio" name="color-focus-tint" :value="tint">
            <span class="swatch" aria-hidden="true"></span>{{ tintLabels[tint] }}
          </label>
        </div>
      </fieldset>
      <p v-if="settings.on && hasTimings && partCount > 1" class="part-progress">
        <span>Part {{ currentPart + 1 }} of {{ partCount }}</span>
        <span v-if="partCount <= 20" class="part-dots" aria-hidden="true"><i v-for="n in partCount" :key="n" :class="{ done: n - 1 < currentPart, current: n - 1 === currentPart }"></i></span>
      </p>
    </div>
    <div v-if="settings.on && hasTimings" class="focus-row">
      <SettingSwitch v-model="settings.guide" label="Highlight sentence" />
      <SettingSwitch v-model="settings.dim" label="Dim other paragraphs" />
      <SettingSwitch v-model="settings.pauseParts" label="Pause after each paragraph" />
    </div>
  </div>
</template>

<style scoped>
.color-focus-settings { display: grid; gap: 10px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #e3e9eb; font-size: 13px; color: #52616a; }
.focus-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 28px; }
.tint-choice { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; border: 0; margin: 0; padding: 0; min-width: 0; }
.tint-choice legend { float: left; padding: 0; white-space: nowrap; }
.tint-options { display: flex; flex-wrap: wrap; gap: 2px; }
/* Same look as the text size choices: plain until hovered, filled teal when chosen. */
.tint-option { position: relative; display: inline-flex; align-items: center; gap: 7px; height: 36px; padding: 0 12px 0 9px; border-radius: 5px; color: #345d6b; cursor: pointer; }
.tint-option:hover { background: #e8eff2; }
.tint-option.selected { background: #347b91; color: white; }
.tint-option input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
.tint-option:has(input:focus-visible) { outline: 3px solid #db9d22; outline-offset: 2px; }
.swatch { width: 18px; height: 18px; border-radius: 50%; border: 1px solid rgb(0 0 0 / .15); }
.selected .swatch { border-color: white; }
.swatch-blue .swatch { background: #dbe8f5; }
.swatch-green .swatch { background: #dcede2; }
.swatch-cream .swatch { background: #f5eed8; }
.swatch-none .swatch { background: linear-gradient(135deg, white 45%, #b9c5ca 45%, #b9c5ca 55%, white 55%); }
.part-progress { display: flex; align-items: center; gap: 8px; margin: 0 0 0 auto; color: #345d6b; }
.part-dots { display: inline-flex; gap: 5px; }
.part-dots i { width: 9px; height: 9px; border-radius: 50%; background: #d3dadd; }
.part-dots i.done { background: #347b91; }
.part-dots i.current { background: #f0a92b; box-shadow: 0 0 0 2px #fde3b5; }
@media (max-width: 760px) { .part-progress { margin-left: 0; } }
@media (max-width: 420px) { .tint-option { gap: 5px; padding: 0 8px 0 6px; } }
</style>
