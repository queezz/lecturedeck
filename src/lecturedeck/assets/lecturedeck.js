(() => {
  "use strict";
  const spec = window.LECTUREDECK || { meta: {}, slides: [] };
  const deck = document.querySelector("#deck");
  const overview = document.querySelector("#overview");
  const counter = document.querySelector("#counter");
  const previousButton = document.querySelector("#previous-button");
  const nextButton = document.querySelector("#next-button");
  const themeButton = document.querySelector("#theme-button");
  const fullscreenButtons = [
    document.querySelector("#fullscreen-button"),
    document.querySelector("#touch-fullscreen-button"),
  ].filter(Boolean);
  let index = Math.max(0, Math.min(spec.slides.length - 1, Number(location.hash.replace("#/", "")) || 0));
  let nativeFullscreenWasActive = false;
  let deliberateNativeFullscreenExit = false;

  const escapeHtml = (value = "") => String(value).replace(/[&<>\"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[char]));

  const slideTitleText = (slide, i) => {
    const raw = slide.title || slide.interactive?.title || slide.video?.title || "";
    return String(raw).replace(/<[^>]*>/g, "").trim() || `Slide ${i + 1}`;
  };

  function setTheme(theme) {
    const light = theme === "light";
    document.body.classList.toggle("light-theme", light);
    document.documentElement.style.colorScheme = light ? "light" : "dark";
    if (themeButton) {
      themeButton.textContent = light ? "Dark theme" : "Light theme";
      themeButton.setAttribute("aria-pressed", String(light));
      themeButton.title = `Switch to ${light ? "dark" : "light"} theme (T)`;
    }
    try {
      localStorage.setItem("lecturedeck-theme", light ? "light" : "dark");
    } catch (_) {
      // The viewer remains usable when local storage is unavailable.
    }
  }

  function toggleTheme() {
    setTheme(document.body.classList.contains("light-theme") ? "dark" : "light");
  }

  try {
    setTheme(localStorage.getItem("lecturedeck-theme") || "dark");
  } catch (_) {
    setTheme("dark");
  }

  function finiteNumber(value, fallback = 0) {
    return typeof value === "number" && Number.isFinite(value) ? value : fallback;
  }

  function figureGeometry(figure) {
    const shift = Array.isArray(figure.shift) ? figure.shift : [];
    const scale = finiteNumber(figure.scale, 1);
    return {
      x: finiteNumber(shift[0]),
      y: finiteNumber(shift[1]),
      scale: scale > 0 ? scale : 1,
    };
  }

  function figureMarkup(figure, figureIndex) {
    const caption = figure.caption || figure.source ? `<figcaption>${figure.caption || ""}${figure.source ? `<strong>${figure.source}</strong>` : ""}</figcaption>` : "";
    const geometry = figureGeometry(figure);
    const style = geometry.x || geometry.y || geometry.scale !== 1 ? ` style="transform: translate(${geometry.x}px, ${geometry.y}px) scale(${geometry.scale});"` : "";
    return `<figure class="figure-card" data-figure-index="${figureIndex}"${style}><img src="${escapeHtml(figure.src)}" alt="${escapeHtml(figure.alt || figure.caption || "Lecture figure")}">${caption}</figure>`;
  }

  function formulaMarkup(formula) {
    if (!formula) return "";
    if (typeof formula === "string") return `<div class="formula formula-plain">${escapeHtml(formula)}</div>`;
    const math = formula.mathml || formula.html || "";
    const gloss = (formula.gloss || []).map(item => `<span>${item}</span>`).join("");
    return `<div class="formula formula-structured">${formula.label ? `<p class="formula-label">${escapeHtml(formula.label)}</p>` : ""}<div class="formula-math">${math}</div>${gloss ? `<div class="formula-gloss">${gloss}</div>` : ""}</div>`;
  }

  function cardsMarkup(cards = []) {
    if (!cards.length) return "";
    return `<div class="concept-cards count-${Math.min(cards.length, 3)}">${cards.map(card => `<div class="concept-card">${card.label ? `<p class="card-label">${card.label}</p>` : ""}<p class="card-value">${card.value || ""}</p>${card.detail ? `<p class="card-detail">${card.detail}</p>` : ""}</div>`).join("")}</div>`;
  }

  function interactiveMarkup(interactive, thumbnail = false) {
    if (!interactive) return "";
    const title = interactive.title || "Interactive demonstration";
    if (thumbnail) return `<div class="interactive-placeholder">${escapeHtml(title)}</div>`;
    return `<div class="interactive-frame"><iframe src="${escapeHtml(interactive.src)}" title="${escapeHtml(title)}" loading="eager" referrerpolicy="no-referrer"></iframe></div>`;
  }

  function videoMarkup(video, thumbnail = false) {
    if (!video) return "";
    const title = video.title || "Lecture video";
    const poster = video.poster ? ` poster="${escapeHtml(video.poster)}"` : "";
    if (thumbnail) {
      if (video.poster) return `<div class="video-placeholder has-poster"><img src="${escapeHtml(video.poster)}" alt=""><span>${escapeHtml(title)}</span></div>`;
      return `<div class="video-placeholder">${escapeHtml(title)}</div>`;
    }
    const sources = video.sources?.length ? video.sources : video.src ? [video] : [];
    const sourceMarkup = sources.map(source => `<source src="${escapeHtml(source.src)}"${source.type ? ` type="${escapeHtml(source.type)}"` : ""}>`).join("");
    const trackMarkup = (video.tracks || []).map(track => `<track src="${escapeHtml(track.src)}" kind="${escapeHtml(track.kind || "captions")}" srclang="${escapeHtml(track.srclang || "en")}" label="${escapeHtml(track.label || track.srclang || "Captions")}"${track.default ? " default" : ""}>`).join("");
    const originalLink = video.originalUrl ? `<a class="video-original-link" href="${escapeHtml(video.originalUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(video.originalLabel || "Open the original video")}</a>` : "";
    const caption = video.caption || video.source || originalLink ? `<figcaption>${video.caption || ""}${video.source ? `<strong>${video.source}</strong>` : ""}${originalLink}</figcaption>` : "";
    return `<figure class="video-card"><video class="lecture-video" controls playsinline preload="metadata" aria-label="${escapeHtml(title)}"${poster}${video.muted ? " muted" : ""}${video.loop ? " loop" : ""}>${sourceMarkup}${trackMarkup}<p>Your browser cannot play this local video.</p></video>${caption}</figure>`;
  }

  function partLabel(i) {
    let label = spec.meta.opening || "OPENING";
    for (let j = 0; j <= i; j += 1) {
      const candidate = spec.slides[j];
      if (candidate.type === "section") label = candidate.eyebrow || candidate.title || label;
    }
    return label;
  }

  function partAccent(i) {
    let accent = spec.meta.openingAccent || "red";
    for (let j = 0; j <= i; j += 1) {
      const candidate = spec.slides[j];
      if (candidate.type === "section" && candidate.accent) accent = candidate.accent;
    }
    return accent;
  }

  function slideMarkup(slide, i, thumbnail = false) {
    const chromeFree = slide.chrome === false;
    const figures = slide.figures || (slide.figure ? [slide.figure] : []);
    const layout = slide.layout || (slide.interactive ? "interactive" : slide.video ? "video" : figures.length > 1 ? "figures" : figures.length ? "figure" : slide.type === "title" ? "title" : slide.cards?.length ? "cards" : slide.formula ? "equation" : "statement");
    const figureBlock = figures.length ? `<div class="figure-stack ${figures.length === 2 ? "two" : figures.length >= 3 ? "three" : ""}">${figures.map(figureMarkup).join("")}</div>` : "";
    const cardBlock = cardsMarkup(slide.cards);
    const interactiveBlock = interactiveMarkup(slide.interactive, thumbnail);
    const videoBlock = videoMarkup(slide.video, thumbnail);
    const copy = `<div class="copy">${slide.claim ? `<p class="claim">${slide.claim}</p>` : ""}${formulaMarkup(slide.formula)}${slide.body ? `<div class="body-copy">${slide.body}</div>` : ""}${slide.quote ? `<div class="quote">${slide.quote}</div>` : ""}</div>`;
    const body = ["figure", "figure-dominant", "figure-stage", "title", "figures"].includes(layout) ? `${copy}${figureBlock}` : layout === "cards" ? `${copy}${cardBlock}` : layout === "interactive" ? `${copy}${interactiveBlock}` : layout === "video" ? `${copy}${videoBlock}` : copy;
    const header = chromeFree ? "" : `<header class="slide-head"><p class="eyebrow">${partLabel(i)}</p><h1 class="slide-title">${slide.title || ""}</h1></header>`;
    const footer = chromeFree ? "" : `<footer class="slide-foot"><span class="source">${slide.source || ""}</span><span class="footer-nav"><span class="course-name">${spec.meta.section || ""}</span>${slide.beat ? `<span class="beat">${slide.beat}</span>` : ""}<span class="page-number">${i + 1} / ${spec.slides.length}</span></span></footer>`;
    return `<article class="slide-frame kind-${escapeHtml(slide.type || "content")}${slide.className ? ` ${escapeHtml(slide.className)}` : ""}${chromeFree ? " chrome-free" : ""}" data-accent="${escapeHtml(slide.accent || partAccent(i))}" data-index="${i}" aria-label="Slide ${i + 1}: ${escapeHtml(slideTitleText(slide, i))}">${header}<section class="slide-body layout-${layout}">${body}</section>${footer}</article>`;
  }

  function scaleCurrent() {
    const frame = deck.querySelector(".slide-frame");
    if (!frame) return;
    const scale = Math.min(innerWidth / 1280, innerHeight / 720);
    frame.style.transform = `scale(${scale})`;
  }

  function render() {
    if (!spec.slides.length) return;
    document.body.classList.toggle("immersive-slide", spec.slides[index].chrome === false);
    deck.innerHTML = slideMarkup(spec.slides[index], index);
    counter.textContent = `${index + 1} / ${spec.slides.length}`;
    previousButton.disabled = index === 0;
    nextButton.disabled = index === spec.slides.length - 1;
    document.title = `${slideTitleText(spec.slides[index], index)} · ${spec.meta.title || "Lecturedeck"}`;
    history.replaceState(null, "", `#/${index}`);
    if (!overview.hidden) overview.querySelectorAll(".overview-card").forEach(card => card.setAttribute("aria-current", String(Number(card.dataset.index) === index)));
    scaleCurrent();
  }

  function go(next) {
    const clamped = Math.max(0, Math.min(spec.slides.length - 1, next));
    if (clamped === index) return;
    index = clamped;
    render();
  }

  function isNativeFullscreen() {
    return Boolean(document.fullscreenElement || document.webkitFullscreenElement);
  }

  function updateFullscreenButtons() {
    const nativeActive = isNativeFullscreen();
    const escapedNativeFullscreen = (
      nativeFullscreenWasActive && !nativeActive && !deliberateNativeFullscreenExit
    );
    nativeFullscreenWasActive = nativeActive;
    if (!nativeActive) deliberateNativeFullscreenExit = false;
    const active = nativeActive || document.body.classList.contains("pseudo-fullscreen");
    fullscreenButtons.forEach(button => {
      button.textContent = active ? "Exit full screen" : "Full screen";
      button.setAttribute("aria-pressed", String(active));
    });
    if (escapedNativeFullscreen && overview.hidden) toggleOverview(true);
  }

  async function toggleFullscreen() {
    if (isNativeFullscreen()) {
      const exit = document.exitFullscreen || document.webkitExitFullscreen;
      if (exit) {
        deliberateNativeFullscreenExit = true;
        await exit.call(document);
      }
      return;
    }
    if (document.body.classList.contains("pseudo-fullscreen")) {
      document.body.classList.remove("pseudo-fullscreen");
      updateFullscreenButtons();
      return;
    }
    const root = document.documentElement;
    const request = root.requestFullscreen || root.webkitRequestFullscreen;
    if (request) {
      try {
        if (root.requestFullscreen) await request.call(root, {navigationUI: "hide"});
        else await request.call(root);
        if (isNativeFullscreen()) return;
      } catch (_) {
        // iPad Safari may expose the API but reject it for non-video elements.
      }
    }
    document.body.classList.add("pseudo-fullscreen");
    window.scrollTo(0, 0);
    updateFullscreenButtons();
  }

  function scaleOverviewThumbs() {
    if (overview.hidden) return;
    overview.querySelectorAll(".overview-thumb").forEach(thumb => {
      const frame = thumb.querySelector(".slide-frame");
      if (frame && thumb.clientWidth) frame.style.transform = `scale(${thumb.clientWidth / 1280})`;
    });
  }

  function toggleOverview(force) {
    const open = force ?? overview.hidden;
    overview.hidden = !open;
    deck.hidden = open;
    if (!open) { render(); return; }
    overview.innerHTML = spec.slides.map((slide, i) => `<button class="overview-card" type="button" data-index="${i}" aria-current="${i === index}"><div class="overview-thumb">${slideMarkup(slide, i, true)}</div><span class="overview-label">${i + 1}. ${slideTitleText(slide, i)}</span></button>`).join("");
    scaleOverviewThumbs();
    overview.querySelector('[aria-current="true"]')?.focus();
  }

  addEventListener("resize", () => { scaleCurrent(); scaleOverviewThumbs(); });
  addEventListener("hashchange", () => {
    const requested = Number(location.hash.replace("#/", ""));
    if (Number.isFinite(requested) && requested !== index) go(requested);
  });
  addEventListener("message", event => {
    const iframe = deck.querySelector(".interactive-frame iframe");
    if (!iframe || event.source !== iframe.contentWindow || event.data?.type !== "lecturedeck:navigate") return;
    const direction = Number(event.data.direction);
    if (direction === 1 || direction === -1) go(index + direction);
  });
  addEventListener("keydown", event => {
    const target = event.target instanceof Element ? event.target : null;
    if (target && target.closest("video, audio, input, textarea, select, [contenteditable]")) return;
    // Buttons and links keep Space/Enter activation but still allow deck paging.
    const onControl = Boolean(target && target.closest("button, a"));
    if (["ArrowRight", "ArrowDown", "PageDown"].includes(event.key) || (event.key === " " && !onControl)) { event.preventDefault(); go(index + 1); }
    else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(event.key)) { event.preventDefault(); go(index - 1); }
    else if (event.key === "Home") go(0);
    else if (event.key === "End") go(spec.slides.length - 1);
    else if (event.key === "Escape" && overview.hidden && document.body.classList.contains("pseudo-fullscreen")) toggleFullscreen();
    else if (event.key.toLowerCase() === "o" || event.key === "Escape") toggleOverview();
    else if (event.key.toLowerCase() === "f") toggleFullscreen();
    else if (event.key.toLowerCase() === "t") toggleTheme();
  });
  let wheelStreak = 0;
  let wheelPrevAt = -1e6;
  let wheelHoldUntil = 0;
  addEventListener("wheel", event => {
    if (!overview.hidden || event.ctrlKey) return;
    if (event.target instanceof Element && event.target.closest("video, audio, .interactive-frame")) return;
    const now = performance.now();
    const gap = now - wheelPrevAt;
    wheelPrevAt = now;
    const unit = event.deltaMode === 1 ? 20 : event.deltaMode === 2 ? 120 : 1;
    const delta = event.deltaY * unit;
    if (!delta) return;
    const direction = delta > 0 ? 1 : -1;
    if (event.deltaMode !== 0 || (Math.abs(delta) >= 80 && gap > 60)) {
      // A discrete wheel notch always turns one slide, with no lock-out.
      wheelStreak = 0;
      wheelHoldUntil = now + 150;
      go(index + direction);
      return;
    }
    // Smooth pixel stream: trackpad glide or a high-resolution wheel.
    if (now < wheelHoldUntil) {
      wheelHoldUntil = now + 150; // absorb the inertia tail until the stream pauses
      return;
    }
    if (gap > 250 || (wheelStreak && direction !== Math.sign(wheelStreak))) wheelStreak = 0;
    wheelStreak += delta;
    if (Math.abs(wheelStreak) < 60) return;
    wheelStreak = 0;
    wheelHoldUntil = now + 150;
    go(index + direction);
  }, {passive: true});
  let touchX = null;
  addEventListener("touchstart", e => { touchX = e.target instanceof Element && e.target.closest("video") ? null : e.changedTouches[0].clientX; }, {passive:true});
  addEventListener("touchend", e => { if (touchX === null) return; const dx = e.changedTouches[0].clientX - touchX; if (Math.abs(dx) > 55) go(index + (dx < 0 ? 1 : -1)); touchX = null; }, {passive:true});
  overview.addEventListener("click", event => { const card = event.target.closest("[data-index]"); if (!card) return; index = Number(card.dataset.index); toggleOverview(false); });
  document.querySelector("#overview-button").addEventListener("click", () => toggleOverview());
  themeButton?.addEventListener("click", toggleTheme);
  previousButton.addEventListener("click", () => go(index - 1));
  nextButton.addEventListener("click", () => go(index + 1));
  fullscreenButtons.forEach(button => button.addEventListener("click", toggleFullscreen));
  addEventListener("fullscreenchange", updateFullscreenButtons);
  addEventListener("webkitfullscreenchange", updateFullscreenButtons);
  let reloadVersion = null;
  let reloadFailures = 0;
  let reloadTimer = null;
  async function pollLiveReload() {
    try {
      const response = await fetch("/__lecturedeck/version", {cache: "no-store"});
      if (!response.ok) throw new Error(response.status);
      const state = await response.json();
      reloadFailures = 0;
      if (!state.livereload) { clearInterval(reloadTimer); return; }
      if (reloadVersion === null) reloadVersion = state.version;
      else if (reloadVersion !== state.version) location.reload();
    } catch (_) {
      // Static releases and file:// previews intentionally have no reload endpoint.
      reloadFailures += 1;
      if (reloadFailures >= 3) clearInterval(reloadTimer);
    }
  }
  reloadTimer = setInterval(pollLiveReload, 900);
  pollLiveReload();
  updateFullscreenButtons();
  render();
})();
