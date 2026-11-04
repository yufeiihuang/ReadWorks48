<script setup>
// An On/Off switch in the reading settings. Same markup and global .highlight-* styles as the
// Highlight and Dyslexia font switches, so every switch in the panel looks and behaves alike.
defineProps({ label: { type: String, required: true } });
const on = defineModel({ type: Boolean, default: false });
</script>

<template>
  <label class="highlight-control">
    <span>{{ label }}</span>
    <input v-model="on" class="highlight-switch" type="checkbox" role="switch">
    <span class="highlight-track" aria-hidden="true"><span class="highlight-thumb"></span></span>
    <span class="highlight-state" aria-hidden="true">{{ on ? 'On' : 'Off' }}</span>
  </label>
</template>
