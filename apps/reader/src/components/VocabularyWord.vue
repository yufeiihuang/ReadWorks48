<script setup>
defineProps({ entry: Object, saved: Boolean, canHear: Boolean, collapsible: Boolean });
defineEmits(['hear', 'toggle']);
</script>
<template>
  <component :is="collapsible ? 'details' : 'div'" class="vocabulary-word" :class="{ 'word-dropdown': collapsible }">
    <summary v-if="collapsible"><span class="word-label">{{ entry.word }}</span><em>{{ entry.partOfSpeech }}</em></summary>
    <h3 v-else>{{ entry.word }}</h3>
    <div v-if="entry.lemma && entry.lemma !== entry.word.toLowerCase()" class="base-word">Base word: {{ entry.lemma }}</div>
    <em v-if="!collapsible">{{ entry.partOfSpeech }}</em>
    <p>{{ entry.definition }}</p>
    <p class="word-sentence">{{ entry.before }}<strong>{{ entry.word }}</strong>{{ entry.after }}</p>
    <div class="vocabulary-actions"><button :disabled="!canHear" @click="$emit('hear', entry.tokenId)">Hear it</button><button :disabled="entry.unavailable" :aria-pressed="saved" @click="$emit('toggle', entry)">{{ saved ? '★ Remove from My words' : '☆ Add to My words' }}</button></div>
    <small v-if="entry.source && !collapsible"><a :href="entry.source.url" target="_blank" rel="noopener">Definitions from {{ entry.source.name }} ({{ entry.source.license }})</a></small>
  </component>
</template>

<style scoped>
.base-word { margin: 0 0 8px; color: #64747d; font-size: 13px; font-weight: 400; line-height: 1.5; }
.word-dropdown summary { display: flex; align-items: baseline; gap: 12px; cursor: pointer; list-style: none; padding: 6px 0; }
.word-dropdown summary::-webkit-details-marker { display: none; }
.word-dropdown summary::before { content: '›'; align-self: center; color: #347b91; font-size: 24px; line-height: 1; transition: transform .15s; }
.word-dropdown[open] summary::before { transform: rotate(90deg); }
.word-dropdown summary:focus-visible { outline: 3px solid #db9d22; outline-offset: 4px; border-radius: 3px; }
.word-label { font-size: 19px; font-weight: 600; }
.word-dropdown summary em { font-size: 14px; }
.word-dropdown[open] summary { margin-bottom: 12px; }
@media (prefers-reduced-motion: reduce) { .word-dropdown summary::before { transition: none; } }
</style>
