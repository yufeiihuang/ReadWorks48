<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';

defineProps({
  question: { type: String, required: true },
  speed: { type: Number, required: true },
});
const emit = defineEmits(['accept', 'dismiss']);
const dismissOnEscape = event => { if (event.key === 'Escape') emit('dismiss'); };

// The tip lines up with the right edge of the speed menu, but on small screens that menu wraps
// to the left. Slide the tip back on screen; its pointer moves the other way to stay on the menu.
const EDGE_GAP = 16;
const tip = ref(null);
const shift = ref(0);
function keepOnScreen() {
  const menuRight = tip.value.parentElement.getBoundingClientRect().right;
  shift.value = Math.max(0, EDGE_GAP - (menuRight - tip.value.offsetWidth));
}
onMounted(() => {
  keepOnScreen();
  document.addEventListener('keydown', dismissOnEscape);
  window.addEventListener('resize', keepOnScreen);
});
onBeforeUnmount(() => {
  document.removeEventListener('keydown', dismissOnEscape);
  window.removeEventListener('resize', keepOnScreen);
});
</script>

<template>
  <!-- Doesn't take focus on page load. It follows the speed control in tab order, and
       App.vue announces it through a status region. -->
  <div ref="tip" class="speed-tip" role="group" aria-labelledby="speed-tip-question" :style="{ '--shift': `${shift}px` }">
    <p id="speed-tip-question" class="speed-tip-question">{{ question }}</p>
    <p class="speed-tip-text">Change to {{ speed }}× speed for better listening.</p>
    <div class="speed-tip-actions">
      <button type="button" class="speed-tip-accept" @click="emit('accept')">Change to {{ speed }}×</button>
      <button type="button" class="speed-tip-dismiss" @click="emit('dismiss')">No thanks</button>
    </div>
  </div>
</template>

<style scoped>
.speed-tip {
  position: absolute;
  top: calc(100% + 12px);
  right: 0;
  transform: translateX(var(--shift));
  z-index: 30;
  width: min(290px, calc(100vw - 48px));
  padding: 14px 16px;
  border-radius: 10px;
  background: #235b6e; /* matches the audio control tooltips */
  color: #fff;
  font-size: 14px;
  line-height: 1.4;
  white-space: normal;
  box-shadow: 0 6px 20px rgb(0 0 0 / 0.25);
}

/* Points up at the speed menu. */
.speed-tip::before {
  content: "";
  position: absolute;
  bottom: 100%;
  right: calc(30px + var(--shift));
  border: 8px solid transparent;
  border-bottom-color: #235b6e;
}

.speed-tip-question { margin: 0 0 2px; font-size: 16px; font-weight: 700; }
.speed-tip-text { margin: 0 0 12px; }
.speed-tip-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }

.speed-tip-actions button {
  min-height: 36px;
  padding: 6px 14px;
  border-radius: 18px;
  font-size: 14px;
}
.speed-tip-accept { border: 1px solid #fff; background: #fff; color: #235b6e; font-weight: 600; }
.speed-tip-accept:hover { background: #e6eff2; }
.speed-tip-dismiss { border: 1px solid transparent; background: none; color: #fff; }
.speed-tip-dismiss:hover { border-color: #fff; }
.speed-tip-actions button:focus-visible { outline-color: #ffd27a; outline-offset: 2px; }
</style>
