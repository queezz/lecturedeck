(() => {
  "use strict";
  // The runtime publishes the loaded deck (JSON or legacy) asynchronously.
  const spec = () => window.LECTUREDECK || { slides: [] };
  const values = new Map();
  const step = 2;
  const fastStep = 10;
  const scaleStep = 0.02;
  const minScale = 0.5;
  const maxScale = 2;
  let active = false;
  let selected = 0;

  const hud = document.createElement("aside");
  hud.className = "lecturedeck-adjust-hud";
  hud.hidden = true;
  hud.setAttribute("aria-live", "polite");
  document.body.append(hud);

  const styles = document.createElement("style");
  styles.textContent = `
    .lecturedeck-adjust-hud { position: fixed; z-index: 90; top: 18px; right: 18px; max-width: min(470px, calc(100vw - 36px)); padding: 14px 17px; border: 2px solid #83a598; border-radius: 10px; background: rgba(17, 21, 22, .94); color: #ebdbb2; box-shadow: 0 10px 32px rgba(0, 0, 0, .45); font: 600 16px/1.35 Calibri, Aptos, Arial, sans-serif; }
    .lecturedeck-adjust-hud strong { color: #83a598; letter-spacing: .06em; text-transform: uppercase; }
    .lecturedeck-adjust-hud code { display: block; margin-top: 5px; color: #fbf1c7; font: 600 17px/1.35 Consolas, "Cascadia Mono", monospace; }
    .lecturedeck-adjust-hud small { display: block; margin-top: 8px; color: #a89984; font-size: 13px; font-weight: 400; }
    .figure-card.lecturedeck-adjust-selected { outline: 4px solid #83a598; outline-offset: 5px; }
  `;
  document.head.append(styles);

  function slideIndex() {
    const value = Number(location.hash.replace("#/", ""));
    return Number.isInteger(value) && value >= 0 ? value : 0;
  }

  function figures() {
    const slide = spec().slides[slideIndex()];
    if (!slide) return [];
    return slide.figures || (slide.figure ? [slide.figure] : []);
  }

  function keyFor(figureIndex) {
    return `${slideIndex()}:${figureIndex}`;
  }

  function number(value, fallback = 0) {
    return typeof value === "number" && Number.isFinite(value) ? value : fallback;
  }

  function initial(figure) {
    const shift = Array.isArray(figure.shift) ? figure.shift : [];
    const scale = number(figure.scale, 1);
    return { x: number(shift[0]), y: number(shift[1]), scale: scale > 0 ? scale : 1 };
  }

  function geometry(figureIndex) {
    const key = keyFor(figureIndex);
    if (!values.has(key)) values.set(key, initial(figures()[figureIndex] || {}));
    return values.get(key);
  }

  function apply() {
    const cards = [...document.querySelectorAll("#deck .figure-card")];
    cards.forEach((card, figureIndex) => {
      const value = geometry(figureIndex);
      card.style.transform = `translate(${value.x}px, ${value.y}px) scale(${value.scale})`;
      card.classList.toggle("lecturedeck-adjust-selected", active && figureIndex === selected);
    });
  }

  function format(value) {
    return Number(value.toFixed(2)).toString();
  }

  function updateHud() {
    const count = figures().length;
    hud.hidden = !active;
    if (!active || !count) return;
    const value = geometry(selected);
    hud.innerHTML = `<strong>Geometry adjust · figure ${selected + 1}/${count}</strong><code>shift: [${format(value.x)}, ${format(value.y)}], scale: ${format(value.scale)}</code><small>Arrows nudge · Shift+arrows move 10 px · [ ] scale · Tab selects · R resets · G or Esc exits</small>`;
  }

  function refresh() {
    if (!figures().length) {
      active = false;
      hud.hidden = true;
      return;
    }
    selected = Math.min(selected, figures().length - 1);
    apply();
    updateHud();
  }

  function toggle() {
    if (!figures().length) return;
    active = !active;
    refresh();
  }

  addEventListener("hashchange", () => {
    selected = 0;
    setTimeout(refresh, 0);
  });
  addEventListener("keydown", event => {
    const target = event.target instanceof Element ? event.target : null;
    if (target && target.closest("input, textarea, select, [contenteditable]")) return;
    if (event.key.toLowerCase() === "g" && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault();
      event.stopPropagation();
      toggle();
      return;
    }
    if (!active) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      active = false;
      refresh();
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      event.stopPropagation();
      selected = (selected + (event.shiftKey ? figures().length - 1 : 1)) % figures().length;
      refresh();
      return;
    }
    const value = geometry(selected);
    const distance = event.shiftKey ? fastStep : step;
    const changes = {
      ArrowLeft: () => { value.x -= distance; },
      ArrowRight: () => { value.x += distance; },
      ArrowUp: () => { value.y -= distance; },
      ArrowDown: () => { value.y += distance; },
      "[": () => { value.scale = Math.max(minScale, value.scale - scaleStep); },
      "]": () => { value.scale = Math.min(maxScale, value.scale + scaleStep); },
      r: () => { values.set(keyFor(selected), initial(figures()[selected] || {})); },
    };
    const change = changes[event.key] || changes[event.key.toLowerCase()];
    if (!change) return;
    event.preventDefault();
    // Adjustment consumes the key; the deck must not also page or exit.
    event.stopPropagation();
    change();
    refresh();
  }, true);
})();
