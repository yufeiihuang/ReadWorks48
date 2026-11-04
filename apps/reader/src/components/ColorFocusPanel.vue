<script setup>
import { tints } from '../composables/useColorFocus.js';
import SettingSwitch from './SettingSwitch.vue';
// The Color Focus section of the reading settings: its on/off switch, and while it's on, its
// options. `settings` is the composable's reactive settings object; the section edits it in place
// and the composable remembers the choices.
defineProps({
  settings: { type: Object, required: true },
  hasTimings: { type: Boolean, default: false },
});
const tintLabels = { blue: 'Blue', green: 'Green', cream: 'Cream', none: 'None' };
</script>

<template>
  <div class="color-focus-settings" role="group" aria-label="Color Focus settings">
    <SettingSwitch v-model="settings.on" label="Color Focus" />
    <template v-if="settings.on">
      <fieldset class="tint-choice">
        <legend>Color</legend>
        <div class="tint-options">
          <label v-for="tint in tints" :key="tint" class="tint-option" :class="[`swatch-${tint}`, { selected: settings.tint === tint }]">
            <input v-model="settings.tint" type="radio" name="color-focus-tint" :value="tint">
            <span class="swatch" aria-hidden="true">Aa</span>{{ tintLabels[tint] }}
          </label>
        </div>
      </fieldset>
      <template v-if="hasTimings">
        <SettingSwitch v-model="settings.guide" label="Highlight sentence" />
        <SettingSwitch v-model="settings.dim" label="Dim other paragraphs" />
        <SettingSwitch v-model="settings.pauseParts" label="Pause after each paragraph" />
      </template>
    </template>
  </div>
</template>

<style scoped>
.color-focus-settings { display: grid; gap: 10px; margin-top: 16px; padding-top: 16px; border-top: 1px solid #e3e9eb; font-size: 15px; }
.tint-choice { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 8px 12px; border: 0; margin: 0; padding: 0; min-width: 0; }
.tint-choice legend { float: left; padding: 0; white-space: nowrap; }
.tint-options { display: flex; flex-wrap: wrap; gap: 8px; }
/* Each choice previews its tint, and keeps its name so it never relies on color alone. */
.tint-option { position: relative; display: grid; justify-items: center; gap: 4px; font-size: 13px; cursor: pointer; }
.tint-option input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
.tint-option:has(input:focus-visible) { outline: 3px solid #db9d22; outline-offset: 2px; border-radius: 6px; }
.swatch { display: grid; place-items: center; width: 56px; height: 44px; border: 1px solid #87979e; border-radius: 6px; color: #202529; font-size: 18px; }
.tint-option:hover .swatch { border-color: var(--teal); }
.tint-option.selected { font-weight: 600; }
.tint-option.selected .swatch { border: 3px solid var(--teal); }
.swatch-blue .swatch { background: #dbe8f5; }
.swatch-green .swatch { background: #dcede2; }
.swatch-cream .swatch { background: #f5eed8; }
.swatch-none .swatch { background: white; }
</style>
