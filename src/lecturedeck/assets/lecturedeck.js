(() => {
  "use strict";
  // Kept in lockstep with the Python package version by the test suite.
  const VIEWER_VERSION = "0.17.2";
  const DECK_SCHEMA_VERSION = 1;
  const SLIDE_WIDTH = 1280;
  const SLIDE_HEIGHT = 720;
  const FAVICON_PRESETS = {
    complex: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#071b2a"/><text x="7" y="49" fill="#fbf1c7" font-family="Cambria Math,serif" font-size="47" font-style="italic">e</text><text x="31" y="25" fill="#4dd9ff" font-family="Cambria Math,serif" font-size="21" font-style="italic">iθ</text></svg>`,
    calculus: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#10241d"/><text x="7" y="53" fill="#fbf1c7" font-family="Cambria Math,serif" font-size="58">∫</text><text x="31" y="39" fill="#8ec07c" font-family="Cambria Math,serif" font-size="24" font-style="italic">f′</text></svg>`,
    plasma: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#282828"/><path d="M32 2v9M32 53v9M2 32h9M53 32h9M10.5 10.5l6.5 6.5M47 47l6.5 6.5M53.5 10.5L47 17M17 47l-6.5 6.5" fill="none" stroke="#fb4934" stroke-width="4" stroke-linecap="round"/><circle cx="32" cy="32" r="20" fill="#68423a" stroke="#fe8019" stroke-width="3"/><circle cx="32" cy="32" r="13" fill="#934d2b"/><circle cx="32" cy="32" r="7" fill="#b5762e"/></svg>`,
  };
  const query = new URLSearchParams(location.search);
  const printMode = query.get("print") === "1";
  const printTheme = query.get("theme") === "dark" ? "dark" : "light";
  const deck = document.querySelector("#deck");
  const overview = document.querySelector("#overview");
  const counter = document.querySelector("#counter");
  const previousButton = document.querySelector("#previous-button");
  const nextButton = document.querySelector("#next-button");
  const appearanceButton = document.querySelector("#appearance-button");
  const appearanceDialog = document.querySelector("#appearance-dialog");
  const colorModeInputs = [...document.querySelectorAll('input[name="color-mode"]')];
  const presentationStyleInputs = [
    ...document.querySelectorAll('input[name="presentation-style"]'),
  ];
  const presentationControls = document.querySelector("#presentation-controls");
  const controlsToggle = document.querySelector("#controls-toggle");
  const controlsTools = document.querySelector("#controls-tools");
  const deckSelectorLink = document.querySelector("#deck-selector-link");
  const fullscreenButtons = [
    document.querySelector("#fullscreen-button"),
    document.querySelector("#touch-fullscreen-button"),
  ].filter(Boolean);

  const escapeHtml = (value = "") => String(value).replace(/[&<>\"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[char]));

  function setTheme(theme, persist = true) {
    const light = theme === "light";
    document.body.classList.toggle("light-theme", light);
    document.documentElement.style.colorScheme = light ? "light" : "dark";
    colorModeInputs.forEach(input => { input.checked = input.value === theme; });
    if (persist) {
      try {
        localStorage.setItem("lecturedeck-theme", light ? "light" : "dark");
      } catch (_) {
        // The viewer remains usable when local storage is unavailable.
      }
    }
  }

  function setPresentationStyle(style, persist = true) {
    const allowed = new Set(["default", "gradient", "gradient-title-rule"]);
    const selected = allowed.has(style) ? style : "default";
    document.body.dataset.presentationStyle = selected;
    presentationStyleInputs.forEach(input => { input.checked = input.value === selected; });
    if (persist) {
      try {
        localStorage.setItem("lecturedeck-presentation-style", selected);
      } catch (_) {
        // The viewer remains usable when local storage is unavailable.
      }
    }
  }

  try {
    setTheme(printMode ? printTheme : localStorage.getItem("lecturedeck-theme") || "dark", false);
    setPresentationStyle(
      printMode ? "default" : localStorage.getItem("lecturedeck-presentation-style") || "default",
      false,
    );
  } catch (_) {
    setTheme(printMode ? printTheme : "dark", false);
    setPresentationStyle("default", false);
  }
  appearanceButton?.addEventListener("click", () => appearanceDialog?.showModal());
  appearanceDialog?.addEventListener("close", () => appearanceButton?.focus());
  colorModeInputs.forEach(input => input.addEventListener("change", () => {
    if (input.checked) setTheme(input.value);
  }));
  presentationStyleInputs.forEach(input => input.addEventListener("change", () => {
    if (input.checked) setPresentationStyle(input.value);
  }));

  const viewerVersion = document.querySelector("#viewer-version");
  if (viewerVersion) {
    viewerVersion.textContent = `v${VIEWER_VERSION}`;
    viewerVersion.title = `lecturedeck viewer ${VIEWER_VERSION}`;
  }
  if (deckSelectorLink && /^\/decks\/[^/]+\/webdeck(?:\/|$)/.test(location.pathname)) {
    deckSelectorLink.href = "/";
    deckSelectorLink.hidden = false;
  }

  function deckLoadError(message) {
    deck.innerHTML = `<div class="deck-error" role="alert">${message}</div>`;
  }

  function setFavicon(favicon) {
    if (typeof favicon !== "string") return;
    const preset = FAVICON_PRESETS[favicon];
    const href = preset
      ? `data:image/svg+xml,${encodeURIComponent(preset)}`
      : favicon.startsWith("assets/") ? favicon : null;
    if (!href) return;
    let link = document.querySelector('link[rel~="icon"]');
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.append(link);
    }
    if (preset) link.type = "image/svg+xml";
    else link.removeAttribute("type");
    link.href = href;
  }

  function loadLegacySpec() {
    // Legacy units carry executable slides.js that assigns window.LECTUREDECK.
    return new Promise(resolve => {
      const script = document.createElement("script");
      script.src = "slides.js";
      script.onload = () => resolve(window.LECTUREDECK || null);
      script.onerror = () => resolve(null);
      document.head.append(script);
    });
  }

  async function loadSpec() {
    let deckJsonProblem = null;
    try {
      const response = await fetch("deck.json", {cache: "no-store"});
      if (response.ok) {
        const jsonLike = (response.headers.get("content-type") || "").includes("json");
        let data = null;
        try {
          data = await response.json();
        } catch (_) {
          // A misconfigured server may answer 200 with HTML; treat it as absent.
          if (jsonLike) deckJsonProblem = "deck.json is not valid JSON.";
        }
        if (data && typeof data === "object") {
          if (data.deck === DECK_SCHEMA_VERSION && Array.isArray(data.slides)) {
            return {meta: data.meta || {}, slides: data.slides};
          }
          deckJsonProblem = data.deck === DECK_SCHEMA_VERSION
            ? "deck.json has no slides list."
            : `deck.json declares schema version ${escapeHtml(String(data.deck))}; this viewer supports ${DECK_SCHEMA_VERSION}.`;
        }
      }
    } catch (_) {
      // No deck.json: fall through to the legacy loader.
    }
    if (deckJsonProblem) {
      deckLoadError(deckJsonProblem);
      return null;
    }
    const legacy = await loadLegacySpec();
    if (legacy) return legacy;
    deckLoadError("No deck data: expected webdeck/deck.json (or legacy webdeck/slides.js).");
    return null;
  }

  function boot(rawSpec) {
    const spec = {
      meta: rawSpec.meta || {},
      slides: Array.isArray(rawSpec.slides) ? rawSpec.slides : [],
    };
    setFavicon(spec.meta.favicon);
    window.LECTUREDECK = spec;
    let index = Math.max(0, Math.min(spec.slides.length - 1, Number(location.hash.replace("#/", "")) || 0));
    let nativeFullscreenWasActive = false;
    let deliberateNativeFullscreenExit = false;
    let controlsExpanded = false;
    // Laser pointer state. Declared here, before render() can run, so the
    // renderer can repaint a lit dot without a temporal-dead-zone guard. The
    // element itself is created only after the print-mode branch returns.
    let laser = null;
    let laserOn = false;

    const slideTitleText = (slide, i) => {
      const raw = slide.title || slide.interactive?.title || slide.video?.title || "";
      return String(raw).replace(/<[^>]*>/g, "").trim() || `Slide ${i + 1}`;
    };

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
      const id = figure.id ? ` data-figure-id="${escapeHtml(figure.id)}"` : "";
      return `<figure class="figure-card" data-figure-index="${figureIndex}"${id}${style}><img src="${escapeHtml(figure.src)}" alt="${escapeHtml(figure.alt || figure.caption || "Lecture figure")}">${caption}</figure>`;
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
      const header = chromeFree ? "" : `<header class="slide-head"><p class="eyebrow">${slide.eyebrow || partLabel(i)}</p><h1 class="slide-title">${slide.title || ""}</h1></header>`;
      const footer = chromeFree ? "" : `<footer class="slide-foot"><span class="source">${slide.source || ""}</span><span class="footer-nav"><span class="course-name">${spec.meta.section || ""}</span><span class="page-number">${i + 1} / ${spec.slides.length}</span></span></footer>`;
      const slideId = slide.id ? ` data-slide-id="${escapeHtml(slide.id)}"` : "";
      return `<article class="slide-frame kind-${escapeHtml(slide.type || "content")}${slide.className ? ` ${escapeHtml(slide.className)}` : ""}${chromeFree ? " chrome-free" : ""}" data-accent="${escapeHtml(slide.accent || partAccent(i))}" data-index="${i}"${slideId} aria-label="Slide ${i + 1}: ${escapeHtml(slideTitleText(slide, i))}">${header}<section class="slide-body layout-${layout}">${body}</section>${footer}</article>`;
    }

    function fitFormulas(scope) {
      // MathML does not wrap and math font metrics differ per browser, so an
      // authored formula can exceed its stage. Shrink it to fit; leave
      // formulas that already fit untouched.
      scope.querySelectorAll(".slide-body").forEach(body => {
        const formula = body.querySelector(".formula");
        if (!formula) return;
        formula.style.fontSize = "";
        const math = formula.querySelector(".formula-math math");
        for (let pass = 0; pass < 3; pass += 1) {
          const bodyRect = body.getBoundingClientRect();
          if (!bodyRect.height) return;
          const rects = [...body.children].map(child => child.getBoundingClientRect());
          const spill = Math.max(...rects.map(rect => rect.bottom))
            - Math.min(...rects.map(rect => rect.top)) - bodyRect.height;
          // Client rects clamp MathML to its max-width; scroll metrics expose
          // the true ink width. Heights stay honest in element boxes.
          const target = math || formula;
          const inkWidth = target.scrollWidth;
          const boxWidth = target.clientWidth;
          const inkHeight = target.getBoundingClientRect().height;
          if (!inkWidth || !inkHeight) return;
          const widthRatio = inkWidth > boxWidth + 1 ? boxWidth / inkWidth : 1;
          const heightRatio = spill > 1 ? Math.max(0.3, (inkHeight - spill) / inkHeight) : 1;
          const ratio = Math.min(widthRatio, heightRatio);
          if (ratio > 0.99) return;
          const base = parseFloat(getComputedStyle(formula).fontSize);
          formula.style.fontSize = `${Math.max(18, base * ratio).toFixed(2)}px`;
        }
      });
    }

    function positionControls(scale, frameWidth = SLIDE_WIDTH, frameHeight = SLIDE_HEIGHT) {
      if (!presentationControls || !controlsToggle || !controlsTools) return;
      const frameLeft = (innerWidth - frameWidth * scale) / 2;
      const frameTop = (innerHeight - frameHeight * scale) / 2;
      const frameBottom = frameTop + frameHeight * scale;
      const gutter = 8;
      // Applying the state classes can change the measured height, so
      // measure again and reposition until the geometry matches the state.
      for (let pass = 0; pass < 2; pass += 1) {
        const controlsHeight = presentationControls.offsetHeight || 38;
        const hasRoomBelow = innerHeight - frameBottom >= controlsHeight + gutter * 2;
        const hasRoomAbove = frameTop >= controlsHeight + gutter * 2;
        const safe = hasRoomBelow || hasRoomAbove;
        const left = Math.max(gutter, frameLeft + 24);
        const top = hasRoomBelow
          ? frameBottom + gutter
          : hasRoomAbove
            ? frameTop - controlsHeight - gutter
            : Math.max(gutter, frameBottom - controlsHeight - 12);
        presentationControls.style.left = `${left}px`;
        presentationControls.style.top = `${top}px`;
        presentationControls.classList.toggle("has-safe-space", safe);
        presentationControls.classList.toggle("is-expanded", !safe && controlsExpanded);
        const toolsVisible = safe || controlsExpanded;
        controlsToggle.setAttribute("aria-expanded", String(toolsVisible));
        controlsToggle.setAttribute(
          "aria-label",
          `${toolsVisible ? "Hide" : "Show"} presentation controls`,
        );
        controlsTools.setAttribute("aria-hidden", String(!toolsVisible));
        controlsTools.inert = !toolsVisible;
      }
    }

    function scaleCurrent() {
      const frame = deck.querySelector(".slide-frame");
      if (!frame) return;
      const scale = Math.min(innerWidth / SLIDE_WIDTH, innerHeight / SLIDE_HEIGHT);
      const fullscreen = isNativeFullscreen()
        || document.body.classList.contains("pseudo-fullscreen");
      // Windowed slides and exported pages keep the authored 16:9 canvas.
      // In presentation mode, expand only the spare logical dimension so the
      // slide reaches every viewport edge without stretching or cropping.
      const frameWidth = fullscreen ? innerWidth / scale : SLIDE_WIDTH;
      const frameHeight = fullscreen ? innerHeight / scale : SLIDE_HEIGHT;
      frame.style.width = fullscreen ? `${frameWidth}px` : "";
      frame.style.height = fullscreen ? `${frameHeight}px` : "";
      frame.style.transform = `scale(${scale})`;
      positionControls(scale, frameWidth, frameHeight);
    }

    function render() {
      if (!spec.slides.length) return;
      document.body.classList.toggle("immersive-slide", spec.slides[index].chrome === false);
      deck.innerHTML = slideMarkup(spec.slides[index], index);
      fitFormulas(deck);
      counter.textContent = `${index + 1} / ${spec.slides.length}`;
      previousButton.disabled = index === 0;
      nextButton.disabled = index === spec.slides.length - 1;
      document.title = `${slideTitleText(spec.slides[index], index)} · ${spec.meta.title || "Lecturedeck"}`;
      history.replaceState(null, "", `#/${index}`);
      if (!overview.hidden) overview.querySelectorAll(".overview-card").forEach(card => card.setAttribute("aria-current", String(Number(card.dataset.index) === index)));
      scaleCurrent();
      // Keep a lit laser on the accent of the slide it is now over.
      if (laserOn) paintLaser();
    }

    async function renderPrintDeck() {
      document.body.classList.add("print-deck");
      deck.innerHTML = spec.slides.map((slide, i) => slideMarkup(slide, i, true)).join("");
      document.title = spec.meta.title || "Lecturedeck";
      const images = [...deck.querySelectorAll("img")];
      await Promise.all(images.map(image => image.complete
        ? Promise.resolve()
        : new Promise(resolve => {
          image.addEventListener("load", resolve, {once: true});
          image.addEventListener("error", resolve, {once: true});
        })));
      if (document.fonts?.ready) await document.fonts.ready;
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      fitFormulas(deck);
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      window.LECTUREDECK_PRINT_READY = true;
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
      requestAnimationFrame(scaleCurrent);
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
        if (frame && thumb.clientWidth) {
          frame.style.transform = `scale(${thumb.clientWidth / SLIDE_WIDTH})`;
        }
      });
    }

    function toggleOverview(force) {
      const open = force ?? overview.hidden;
      // A laser dot over a grid of thumbnails points at nothing useful, and
      // the hidden cursor would make the cards hard to click.
      if (open && laserOn) setLaser(false);
      overview.hidden = !open;
      deck.hidden = open;
      if (!open) { render(); return; }
      overview.innerHTML = spec.slides.map((slide, i) => `<button class="overview-card" type="button" data-index="${i}" aria-current="${i === index}"><div class="overview-thumb">${slideMarkup(slide, i, true)}</div><span class="overview-label">${i + 1}. ${slideTitleText(slide, i)}</span></button>`).join("");
      fitFormulas(overview);
      scaleOverviewThumbs();
      overview.querySelector('[aria-current="true"]')?.focus();
    }

    if (printMode) {
      renderPrintDeck();
      return;
    }

    // Laser pointer. `L`, or the Laser control, toggles a glowing dot that
    // tracks the pointer and hides the ordinary cursor over the slide, so a
    // presenter or a recording can point at part of a figure. It is off by
    // default and is created after the print-mode return, so exported PDFs
    // never contain the element at all.
    const laserButton = document.querySelector("#laser-button");
    laser = document.createElement("div");
    laser.className = "laser-dot";
    laser.hidden = true;
    document.body.append(laser);

    function paintLaser() {
      // Follow the accent of the slide being pointed at. The dot keeps a
      // white core so it stays legible against any figure.
      const frame = deck.querySelector(".slide-frame");
      const accent = frame ? getComputedStyle(frame).getPropertyValue("--accent").trim() : "";
      if (accent && laser) laser.style.setProperty("--laser-accent", accent);
    }

    function setLaser(on) {
      laserOn = on;
      laser.hidden = !on;
      document.body.classList.toggle("laser-active", on);
      laserButton?.setAttribute("aria-pressed", String(on));
      if (on) paintLaser();
    }

    addEventListener("pointermove", event => {
      if (!laserOn) return;
      laser.hidden = false;
      laser.style.transform = `translate(${event.clientX}px, ${event.clientY}px)`;
    });
    // Pointer moves stop arriving once the cursor enters an interactive
    // iframe or leaves the window, which would otherwise strand the dot at
    // the last position it saw.
    document.addEventListener("pointerleave", () => { if (laserOn) laser.hidden = true; });
    addEventListener("blur", () => { if (laserOn) laser.hidden = true; });
    laserButton?.addEventListener("click", () => setLaser(!laserOn));

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
      if (appearanceDialog?.open) return;
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
      else if (event.key.toLowerCase() === "l") setLaser(!laserOn);
      else if (event.key.toLowerCase() === "t") { event.preventDefault(); appearanceDialog?.showModal(); }
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
    controlsToggle?.addEventListener("click", () => {
      controlsExpanded = !controlsExpanded;
      scaleCurrent();
    });
    previousButton.addEventListener("click", () => go(index - 1));
    nextButton.addEventListener("click", () => go(index + 1));
    fullscreenButtons.forEach(button => button.addEventListener("click", toggleFullscreen));
    addEventListener("fullscreenchange", updateFullscreenButtons);
    addEventListener("webkitfullscreenchange", updateFullscreenButtons);
    updateFullscreenButtons();
    render();
  }

  let reloadVersion = null;
  let reloadFailures = 0;
  let reloadTimer = null;
  async function pollLiveReload() {
    try {
      const response = await fetch("../__lecturedeck/version", {cache: "no-store"});
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

  (async () => {
    const spec = await loadSpec();
    if (spec) boot(spec);
  })();
})();
