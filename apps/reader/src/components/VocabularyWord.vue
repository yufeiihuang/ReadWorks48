<script setup>
defineProps({ entry: Object, saved: Boolean, canHear: Boolean });
defineEmits(['hear', 'toggle']);
</script>
<template>
  <div class="vocabulary-word">
    <h3>{{ entry.word }}</h3>
    <div v-if="entry.lemma && entry.lemma !== entry.word.toLowerCase()" class="base-word">Base word: {{ entry.lemma }}</div>
    <em>{{ entry.partOfSpeech }}</em>
    <p>{{ entry.definition }}</p>
    <p class="word-sentence">{{ entry.before }}<strong>{{ entry.word }}</strong>{{ entry.after }}</p>
    <div class="vocabulary-actions"><button :disabled="!canHear" @click="$emit('hear', entry.tokenId)">Hear it</button><button :disabled="entry.unavailable" :aria-pressed="saved" @click="$emit('toggle', entry)">{{ saved ? '★ In My words' : '☆ Add to My words' }}</button></div>
    <small v-if="entry.source"><a :href="entry.source.url" target="_blank" rel="noopener">Definitions from {{ entry.source.name }} ({{ entry.source.license }})</a></small>
  </div>
</template>

<style scoped>
.base-word { margin: 0 0 8px; color: #64747d; font-size: 13px; font-weight: 400; line-height: 1.5; }
</style>
