<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';
// A button that opens the reading settings in a panel over the passage, so students can watch the
// text change as they choose. It isn't modal: reading and playback carry on while it's open.
const emit = defineEmits(['reset']);
const open = ref(false);
const root = ref(null);
const button = ref(null);

function close({ returnFocus = false } = {}) {
  open.value = false;
  if (returnFocus) button.value?.focus();
}
const closeIfOutside = event => { if (open.value && !root.value?.contains(event.target)) close(); };
const closeOnEscape = event => { if (open.value && event.key === 'Escape') close({ returnFocus: true }); };
// relatedTarget is null when focus leaves the page or lands on nothing, which shouldn't close it.
const closeIfFocusLeaves = event => { if (event.relatedTarget && !root.value?.contains(event.relatedTarget)) close(); };

onMounted(() => {
  document.addEventListener('pointerdown', closeIfOutside);
  document.addEventListener('keydown', closeOnEscape);
});
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeIfOutside);
  document.removeEventListener('keydown', closeOnEscape);
});
</script>

<template>
  <div ref="root" class="settings-menu" @focusout="closeIfFocusLeaves">
    <button ref="button" type="button" class="settings-button" aria-label="Reading settings" :aria-expanded="open" aria-controls="reading-settings-panel" @click="open = !open">
      <span aria-hidden="true">A<span>a</span></span>
    </button>
    <div v-show="open" id="reading-settings-panel" class="settings-panel" role="group" aria-label="Reading settings">
      <!-- Scrolls on its own: the button is pinned with the audio bar, so on a short screen the page
           can't scroll the bottom of the panel into view. -->
      <div class="settings-scroll">
        <slot />
        <div class="settings-footer">
          <button type="button" class="settings-reset" @click="emit('reset')">Back to default settings</button>
          <button type="button" class="settings-done" @click="close({ returnFocus: true })">Done</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-menu { position: relative; flex: none; }
.settings-button { position: relative; display: grid; place-items: center; width: 48px; height: 48px; padding: 0; border: 1px solid var(--teal); border-radius: 50%; background: white; color: var(--teal); font-size: 22px; font-weight: 700; line-height: 1; }
.settings-button:hover, .settings-button[aria-expanded=true] { background: #e8f3f6; }
.settings-button span span { opacity: .6; }
/* Same bubble as the audio controls' tooltips, kept to the right edge so it stays on screen. */
.settings-button::after { content: 'Reading settings'; position: absolute; top: calc(100% + 8px); right: 0; z-index: 20; padding: 5px 9px; border-radius: 6px; background: #235b6e; color: white; font-size: 12px; font-weight: 400; line-height: 1.2; white-space: nowrap; box-shadow: 0 4px 14px rgb(0 0 0 / .18); opacity: 0; pointer-events: none; transition: opacity .12s ease; }
.settings-button:hover::after, .settings-button:focus-visible::after { opacity: 1; }
.settings-button[aria-expanded=true]::after { content: none; }
.settings-panel { position: absolute; top: calc(100% + 12px); right: 0; z-index: 31; width: min(460px, calc(100vw - 34px)); border: 1px solid #d3dadd; border-radius: 8px; background: white; box-shadow: 0 8px 28px rgb(0 0 0 / .2); color: #344048; }
/* The arrow pointing back at the button. */
.settings-panel::before { content: ''; position: absolute; top: -8px; right: 17px; width: 14px; height: 14px; border-top: 1px solid #d3dadd; border-left: 1px solid #d3dadd; background: white; transform: rotate(45deg); }
.settings-scroll { max-height: calc(100vh - 90px); overflow-y: auto; padding: 20px; border-radius: 8px; }
.settings-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-top: 16px; padding-top: 16px; border-top: 1px solid #e3e9eb; }
.settings-reset { border: 0; padding: 4px 0; background: none; color: var(--teal); font-size: 14px; }
.settings-reset:hover { text-decoration: underline; }
.settings-done { min-height: 40px; padding: 6px 28px; border: 0; border-radius: 5px; background: var(--teal); color: white; font-size: 16px; }
.settings-done:hover { background: #235b6e; }
@media (max-width: 420px) { .settings-scroll { padding: 16px; } }
@media (prefers-reduced-motion: reduce) { .settings-button::after { transition: none; } }
</style>
