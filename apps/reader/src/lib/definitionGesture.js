// Timers are injected so hover/long-press behavior is testable without a browser.
export function definitionGesture(open, { set = setTimeout, clear = clearTimeout } = {}) {
  let timer, origin, held = false;
  const cancel = () => { clear(timer); timer = null; origin = null; };
  return {
    hover(value) { cancel(); timer = set(() => open(value), 600); },
    cancel,
    down(event, value) { cancel(); held = false; if (event.pointerType !== 'touch') return; origin = { x: event.clientX, y: event.clientY }; timer = set(() => { held = true; open(value); }, 500); },
    move(event) { if (origin && Math.hypot(event.clientX - origin.x, event.clientY - origin.y) > 10) cancel(); },
    up() { cancel(); },
    consumeClick() { const suppress = held; held = false; return suppress; },
  };
}
