<script setup>
import { h, reactive, useId } from 'vue';
defineProps({ words: { type: Array, default: () => [] }, canHear: Boolean });
defineEmits(['hear']);
const id = useId();
const ratings = reactive({});
const levels = ["Don’t know it", 'Have heard of it but not sure of its meaning', 'Know something about its meaning', 'Know it well'];
const SpeakerIcon = () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.4, 'aria-hidden': 'true' }, [
  h('path', { d: 'M11 4 6 8H3v8h3l5 4V4Z M15 8a6 6 0 0 1 0 8 M18 5a10 10 0 0 1 0 14' }),
]);
</script>

<template>
  <section v-if="words.length" class="vocabulary-activity" :aria-labelledby="`${id}-title`">
    <h2 :id="`${id}-title`">Before you start reading… <SpeakerIcon class="instruction-speaker" /></h2>
    <p>Here are the vocabulary words that will be in this reading. Let’s see how well you already know them.</p>
    <p :id="`${id}-instructions`">Move the dots to show how well you know each word. It’s ok if you don’t know them yet (this is not graded)! <SpeakerIcon class="instruction-speaker" /></p>
    <div class="familiarity-rows">
      <div v-for="(entry, index) in words" :key="entry.word" class="familiarity-row">
        <div class="familiarity-word"><label :id="`${id}-word-${index}`" :for="`${id}-rating-${index}`">{{ entry.word }}</label><button type="button" class="word-speaker" :disabled="!canHear" :aria-label="`Hear ${entry.word}`" @click="$emit('hear', entry.tokenId)"><SpeakerIcon /></button></div>
        <input :id="`${id}-rating-${index}`" :value="ratings[entry.word] ?? 0" @input="ratings[entry.word] = Number($event.target.value)" type="range" min="0" max="3" step="1" :aria-labelledby="`${id}-word-${index}`" :aria-describedby="`${id}-instructions`" :aria-valuetext="levels[ratings[entry.word] ?? 0]">
      </div>
    </div>
    <div class="familiarity-legend" aria-label="Word familiarity scale">
      <div v-for="(level, index) in levels" :key="level"><span class="legend-color" :class="`level-${index}`" aria-hidden="true"></span><span>{{ level }}</span></div>
    </div>
  </section>
</template>

<style scoped>
.vocabulary-activity { border: 1px solid #b8bfc1; padding: 32px; margin: 8px 0 32px; color: #38434a; }
.vocabulary-activity h2 { margin: 0 0 24px; font-size: clamp(24px, 3vw, 32px); font-weight: 300; line-height: 1.35; }
.vocabulary-activity p { font-size: 17px; line-height: 1.65; margin: 0 0 22px; }
.instruction-speaker { display: inline-block; width: 23px; height: 23px; vertical-align: middle; margin-left: 4px; }
.familiarity-rows { display: grid; gap: 24px; margin: 36px 0 24px; }
.familiarity-row { display: grid; grid-template-columns: 170px minmax(0, 1fr); align-items: center; gap: 16px; }
.familiarity-word { display: flex; align-items: center; gap: 4px; min-width: 0; }
.familiarity-word label { font-size: 19px; font-weight: 650; overflow-wrap: anywhere; }
.word-speaker { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; border: 0; background: none; color: inherit; padding: 4px; cursor: pointer; }
.word-speaker svg { width: 23px; height: 23px; }
.word-speaker:disabled { opacity: .4; cursor: default; }
.familiarity-row input { appearance: none; -webkit-appearance: none; width: 100%; min-width: 0; height: 32px; margin: 0; background: transparent; cursor: pointer; }
.familiarity-row input::-webkit-slider-runnable-track { height: 14px; border: 1px solid #9ca985; background: linear-gradient(to right, #faf093 0% 25%, #e6e968 25% 50%, #afd276 50% 75%, #6bcb76 75% 100%); }
.familiarity-row input::-moz-range-track { height: 14px; border: 1px solid #9ca985; background: linear-gradient(to right, #faf093 0% 25%, #e6e968 25% 50%, #afd276 50% 75%, #6bcb76 75% 100%); }
.familiarity-row input::-webkit-slider-thumb { appearance: none; -webkit-appearance: none; width: 24px; height: 24px; border: 1px solid #929b95; border-radius: 50%; background: white; margin-top: -6px; }
.familiarity-row input::-moz-range-thumb { width: 24px; height: 24px; border: 1px solid #929b95; border-radius: 50%; background: white; }
.familiarity-row input:focus-visible, .word-speaker:focus-visible { outline: 3px solid #db9d22; outline-offset: 4px; border-radius: 4px; }
.familiarity-legend { margin-left: 186px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; text-align: center; font-size: 13px; line-height: 1.6; }
.legend-color { display: block; height: 16px; margin-bottom: 12px; }
.level-0 { background: #f5eb69; } .level-1 { background: #d9e21d; } .level-2 { background: #8cc33f; } .level-3 { background: #36b34a; }
@media (max-width: 600px) { .vocabulary-activity { padding: 24px 18px; } .vocabulary-activity p { font-size: 16px; } .familiarity-row { grid-template-columns: 1fr; gap: 4px; } .familiarity-rows { gap: 18px; } .familiarity-legend { margin-left: 0; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; } }
</style>
