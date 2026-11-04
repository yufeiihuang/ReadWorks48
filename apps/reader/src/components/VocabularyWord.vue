<script setup>
defineProps({ entry: Object, saved: Boolean, canHear: Boolean });
defineEmits(['hear', 'toggle']);
</script>
<template>
  <div class="vocabulary-word">
    <h3>{{ entry.word }} <small v-if="entry.lemma && entry.lemma !== entry.word.toLowerCase()">→ {{ entry.lemma }}</small></h3>
    <em>{{ entry.partOfSpeech }}</em>
    <p>{{ entry.definition }}</p>
    <p class="word-sentence">{{ entry.before }}<strong>{{ entry.word }}</strong>{{ entry.after }}</p>
    <div class="vocabulary-actions"><button :disabled="!canHear" @click="$emit('hear', entry.tokenId)">Hear it</button><button :disabled="entry.unavailable" :aria-pressed="saved" @click="$emit('toggle', entry)">{{ saved ? '★ In My words' : '☆ Add to My words' }}</button></div>
    <small v-if="entry.source"><a :href="entry.source.url" target="_blank" rel="noopener">Definitions from {{ entry.source.name }} ({{ entry.source.license }})</a></small>
  </div>
</template>
