(() => {
  "use strict";
  // Kept in lockstep with the Python package version by the test suite.
  const VIEWER_VERSION = "0.28.0";
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
  const mobileMenuButton = document.querySelector("#mobile-menu-button");
  const touchOverviewButton = document.querySelector("#touch-overview-button");
  const touchControlsButton = document.querySelector("#touch-controls-button");
  const touchReview = matchMedia("(max-width: 700px), (pointer: coarse), (max-height: 500px) and (max-width: 1000px)");
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

  // "#/N" opens slide N (zero-based) with none of its steps shown; "#/N.k"
  // also reveals every step numbered k or lower. Returns null when the hash
  // names no slide at all.
  function parseSlideHash(hash) {
    const text = String(hash || "");
    const match = /^#\/(\d+)(?:\.(\d+))?$/.exec(text);
    if (match) return {index: Number(match[1]), step: match[2] ? Number(match[2]) : 0};
    const loose = Math.trunc(Number(text.replace("#/", "")));
    return Number.isFinite(loose) ? {index: loose, step: 0} : null;
  }

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
  // Focus returns to the Appearance button. While a collapsed controls strip
  // makes it inert, focus leaves the closed dialog instead of staying on one
  // of its radios (the deck's key handler also ignores such a radio).
  appearanceDialog?.addEventListener("close", () => {
    appearanceButton?.focus();
    if (appearanceDialog.contains(document.activeElement)) document.activeElement.blur();
  });
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


  // The first slide with `appendix: true` starts backup material. Main slides
  // count against the main total; appendix slides read B1, B2, … instead.
  // Slides with `review: true` before the appendix (a homework review the
  // meeting opens with) read H1, H2, … and leave the main count too, so the
  // lecture's own slides number 1 … N wherever the review sits. A deck with
  // neither marker keeps plain "i / N" numbering.
  function slideNumbering(slides) {
    const start = slides.findIndex(slide => slide?.appendix === true);
    const hasAppendix = start >= 0;
    const inAppendix = i => hasAppendix && i >= start;
    const inReview = i => !inAppendix(i) && slides[i]?.review === true;
    const ordinal = [];
    let mainTotal = 0;
    let reviewTotal = 0;
    slides.forEach((_, i) => {
      ordinal[i] = inAppendix(i) ? i - start + 1 : inReview(i) ? ++reviewTotal : ++mainTotal;
    });
    const hasReview = reviewTotal > 0;
    const backupTotal = hasAppendix ? slides.length - start : 0;
    const label = i => inAppendix(i) ? `B${ordinal[i]}` : inReview(i) ? `H${ordinal[i]}` : String(ordinal[i]);
    return {
      hasAppendix,
      hasReview,
      inAppendix,
      inReview,
      label,
      // Inside the backup or the review the presenter still wants to see
      // where he is: "B4 / 92" (position and that part's total), never "B4 / B92".
      position: i => inAppendix(i) ? `${label(i)} / ${backupTotal}`
        : inReview(i) ? `${label(i)} / ${reviewTotal}` : `${ordinal[i]} / ${mainTotal}`,
      // The widest positions, one per line. The page number and the counter
      // keep a box this wide on every slide, so going from 9 to 10 moves
      // nothing beside them.
      widest: [`${mainTotal} / ${mainTotal}`, hasReview ? `H${reviewTotal} / ${reviewTotal}` : "",
        hasAppendix ? `B${backupTotal} / ${backupTotal}` : ""].filter(Boolean).join("\n"),
      ariaLabel: (i, title) => !hasAppendix && !hasReview ? `Slide ${i + 1}: ${title}`
        : inAppendix(i) ? `Backup slide ${label(i)} of ${backupTotal}: ${title}`
          : inReview(i) ? `Review slide ${label(i)} of ${reviewTotal}: ${title}`
            : `Slide ${ordinal[i]} of ${mainTotal}: ${title}`,
    };
  }

  async function loadPresentationTime() {
    if (printMode) return null;
    try {
      const response = await fetch("presentation-time.json", {cache: "no-store"});
      return response.ok ? await response.json() : null;
    } catch (_) { return null; }
  }

  function setupLectureClock(timing) {
    if (!timing || printMode) return;
    const parse = value => {
      if (typeof value !== "string" || !/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) return NaN;
      const [hour, minute] = value.split(":").map(Number);
      return hour * 3600 + minute * 60;
    };
    const start = parse(timing.start), end = parse(timing.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return;
    let formatter;
    try {
      formatter = new Intl.DateTimeFormat("en-GB", {
        timeZone: timing.timeZone, hour: "2-digit", minute: "2-digit",
        second: "2-digit", hourCycle: "h23",
      });
    } catch (_) { return; }
    const clock = document.createElement("div");
    clock.id = "lecture-clock";
    clock.className = "lecture-clock";
    clock.setAttribute("role", "timer");
    // Avoid announcements every second while a screen reader reads the slide.
    clock.setAttribute("aria-live", "off");
    clock.title = `${timing.start}–${timing.end} · ${timing.timeZone || "local time"}`;
    document.body.append(clock);
    const toggle = document.createElement("button");
    toggle.id = "clock-button";
    toggle.type = "button";
    toggle.textContent = "Clock";
    toggle.setAttribute("aria-controls", "lecture-clock");
    const key = `lecturedeck-clock-hidden:${timing.start}:${timing.end}:${timing.timeZone || "local"}`;
    let hidden = false;
    try { hidden = localStorage.getItem(key) === "true"; } catch (_) { /* optional */ }
    const apply = () => {
      clock.hidden = hidden;
      toggle.setAttribute("aria-pressed", String(!hidden));
      toggle.setAttribute("aria-label", hidden ? "Show lecture clock" : "Hide lecture clock");
    };
    toggle.addEventListener("click", () => {
      hidden = !hidden;
      try { localStorage.setItem(key, String(hidden)); } catch (_) { /* optional */ }
      apply();
    });
    controlsTools?.append(toggle);
    apply();
    const update = () => {
      const parts = Object.fromEntries(formatter.formatToParts(new Date()).map(p => [p.type, p.value]));
      const seconds = +parts.hour * 3600 + +parts.minute * 60 + +parts.second;
      let label = `${Math.ceil((end - seconds) / 60)} min left`;
      let state = "running";
      if (seconds < start) { label = `starts ${timing.start}`; state = "before"; }
      else if (seconds >= end) { label = seconds === end ? "time's up" : `+${Math.ceil((seconds - end) / 60)} min over`; state = "over"; }
      else if (end - seconds <= 300) state = "last-five";
      clock.dataset.state = state;
      clock.textContent = `${parts.hour}:${parts.minute} · ${label}`;
      clock.setAttribute("aria-label", `Current time ${parts.hour}:${parts.minute}; ${label}`);
    };
    update();
    setInterval(update, 1000);
    document.addEventListener("visibilitychange", update);
    window.addEventListener("focus", update);
  }


  // ---------------------------------------------------------------------
  // Lecture pacing, record schema 2.
  //
  // On scheduled teaching dates the recorder runs from 30 min before the
  // slot to 60 min after it. Every page load writes its own segment:
  // visits are unbroken spans tagged before/slot/after, pauses carry a
  // reason, and a gap the two clocks cannot vouch for is never credited.
  // localStorage is the per-second journal. Records reach disk only
  // through the serve-only sink that the server injects for a browser on
  // its own machine (window.lecturedeckPacingSink). This file holds no
  // endpoint and no write code, so a static release never writes.
  const PACING_LEAD_S = 1800;
  const PACING_TAIL_S = 3600;
  const GAP_MS = 10000;
  const SKEW_MS = 2000;
  const HEARTBEAT_MS = 15000;
  const CHANGE_DEBOUNCE_MS = 2000;
  const ROLLOVER_BYTES = 49152;
  const KEEPALIVE_MAX_BYTES = 60000;
  const BACKOFF_S = [5, 10, 20, 40, 60];
  const PACING_PREFIX = "lecturedeck-pacing2:";
  const PACING_V1_MARK = "lecturedeck-pacing2-migrated:";
  const PACING_PRUNE_DAYS = 60;
  const PACING_REFUSED = [400, 411, 413, 415];
  const PACING_FINAL = [400, 403, 404, 409, 411, 413, 415, 422, 429];
  const pacingEncoder = new TextEncoder();
  const pacingBytes = text => pacingEncoder.encode(text).length;
  const pacingIso = ms => new Date(ms).toISOString();
  const pacingPath = (path = location.pathname) => String(path).replace(/index\.html$/, "");
  // Looked up on every use, so the order in which scripts load is irrelevant.
  const pacingSink = () => window.lecturedeckPacingSink || null;
  // What /__lecturedeck/version said: "unknown" until it answers, the
  // server's own `pacing` word, "absent" from an older server, or
  // "static" when nothing answers (a release or a file copy).
  let serverPacing = "unknown";
  // Segments this page records; the recovery sweep leaves them alone.
  const pacingLive = new Set();

  const modalOpen = () => Boolean(document.querySelector("dialog[open]"));
  // The photo viewer owns deck input like any dialog, but the presenter is
  // still showing the slide's own picture: it pauses no pacing record.
  const pacingDialogOpen = () => Boolean(document.querySelector("dialog[open]:not(.photo-viewer)"));

  // A lone surrogate would make the server refuse the whole record.
  const pacingWellFormed = text => typeof text.toWellFormed === "function" ? text.toWellFormed() : text;

  // Recorded text: no control characters, bounded in code points.
  function pacingText(value, max = 500) {
    const text = pacingWellFormed(String(value ?? "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
    return Array.from(text).slice(0, max).join("");
  }

  function pacingId(value, fallback) {
    const text = pacingWellFormed(String(value ?? "")).replace(/[\u0000-\u001f\u007f]/g, "");
    return Array.from(text).slice(0, 200).join("") || fallback;
  }

  function htmlText(html) {
    // A template parses inertly: nothing in it loads or runs.
    const template = document.createElement("template");
    template.innerHTML = String(html ?? "");
    return template.content.textContent || "";
  }

  const pacingDeckTitle = spec => pacingText(spec?.meta?.tabTitle || spec?.meta?.title || "Lecture", 300) || "Lecture";

  function pacingClock(timeZone) {
    const formatter = new Intl.DateTimeFormat("en-GB", {
      timeZone, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
    });
    return {
      timeZone: formatter.resolvedOptions().timeZone,
      parts(ms) {
        const p = Object.fromEntries(formatter.formatToParts(new Date(ms)).map(part => [part.type, part.value]));
        return {
          date: `${p.year}-${p.month}-${p.day}`,
          seconds: +p.hour * 3600 + +p.minute * 60 + +p.second,
          hhmm: `${p.hour}${p.minute}`,
          hm: `${p.hour}:${p.minute}`,
          hms: `${p.hour}:${p.minute}:${p.second}`,
        };
      },
    };
  }

  // Epoch of wall-clock second `target` on the day of `ms`, whose own
  // wall-clock second is `secondsNow`. Every boundary uses this one
  // formula, so a split lands exactly on the scheduled instant.
  const epochAtSecond = (ms, secondsNow, target) => ms - ((secondsNow - target) * 1000 + (ms % 1000));
  const pacingSeconds = value => {
    const [hour, minute] = String(value).split(":").map(Number);
    return hour * 3600 + minute * 60;
  };

  function pacingSegmentId() {
    const bytes = new Uint8Array(6);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
  }

  const pacingDuration = ms => {
    const seconds = Math.floor(Math.abs(Number(ms) || 0) / 1000);
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  };

  function pacingDay(date, withYear = false) {
    const [year, month, day] = String(date).split("-").map(Number);
    const weekday = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
    const name = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month - 1];
    return `${weekday} ${day} ${name}${withYear ? ` ${year}` : ""}`;
  }

  function pacingRanges(numbers) {
    const parts = [];
    for (let i = 0; i < numbers.length; i += 1) {
      let j = i;
      while (j + 1 < numbers.length && numbers[j + 1] === numbers[j] + 1) j += 1;
      parts.push(j > i ? `${numbers[i]}–${numbers[j]}` : String(numbers[i]));
      i = j;
    }
    return parts.join(", ");
  }

  function pacingSlug(unit, deckTitle) {
    const token = value => String(value || "").normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "").slice(0, 60);
    return token(unit) || token(deckTitle).toLowerCase() || "lecture";
  }

  const pacingShortFile = file => String(file || "").replace(/_([0-9a-f]{4})[0-9a-f]{8}\.json$/, "_$1….json");

  const pacingIsPending = entry => entry.sync.state !== "refused" && (entry.sync.rev || 0) < entry.record.rev;
  const pacingIsSaved = entry => entry.sync.state === "saved" && (entry.sync.rev || 0) >= entry.record.rev;

  function pacingFirstInstant(record) {
    let first = Infinity;
    for (const item of [...(record.visits || []), ...(record.pauses || [])]) {
      const at = Date.parse(item.startedAt);
      if (at < first) first = at;
    }
    return Number.isFinite(first) ? first : Date.parse(record.window?.from) || 0;
  }

  function pacingLastInstant(record) {
    let last = -Infinity;
    for (const item of [...(record.visits || []), ...(record.pauses || [])]) {
      const at = Date.parse(item.startedAt) + (Number(item.durationMs) || 0);
      if (at > last) last = at;
    }
    return last;
  }

  // A schema-1 browser record (viewer 0.20-0.23) as a schema-2 segment.
  // Visits keep their values; v1 recorded only inside the slot, so the
  // window is the slot and every visit is in phase "slot".
  function pacingFromV1(old, keyPath, keyDate) {
    const clockTime = /^([01]\d|2[0-3]):[0-5]\d$/;
    const instant = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
    if (!Array.isArray(old.visits) || !old.visits.length) return null;
    if (!clockTime.test(old.start) || !clockTime.test(old.end)) return null;
    const usable = visit => visit && typeof visit.slideId === "string" && visit.slideId
      && instant.test(visit.startedAt) && Number.isFinite(visit.durationMs);
    if (!old.visits.every(usable)) return null;
    let clock;
    try { clock = pacingClock(old.timeZone); } catch (_) { return null; }
    const first = Date.parse(old.visits[0].startedAt);
    const zoned = clock.parts(first);
    const startAt = epochAtSecond(first, zoned.seconds, pacingSeconds(old.start));
    const endAt = epochAtSecond(first, zoned.seconds, pacingSeconds(old.end));
    const slides = {};
    const visits = old.visits.map(visit => {
      const slideId = pacingId(visit.slideId, "slide");
      const number = Number.isInteger(visit.number) && visit.number > 0 ? Math.min(visit.number, 100000) : 1;
      const label = /^[BH]?\d{1,6}$/.test(String(visit.label ?? "")) ? String(visit.label) : String(number);
      slides[slideId] = {
        number, label,
        title: pacingText(visit.title) || `Slide ${number}`,
        section: pacingText(visit.section) || "Opening",
      };
      if (/^B\d+$/.test(label)) slides[slideId].backup = true;
      if (/^H\d+$/.test(label)) slides[slideId].review = true;
      return {
        slideId, startedAt: visit.startedAt,
        durationMs: Math.min(86400000, Math.max(0, Math.round(visit.durationMs))), phase: "slot",
      };
    });
    return {
      schema: 2, kind: "lecturedeck-pacing-segment", segment: pacingSegmentId(), rev: 1, unit: null,
      path: pacingPath(typeof old.path === "string" ? old.path : keyPath),
      deck: pacingText(old.deck, 300) || "Lecture", viewer: VIEWER_VERSION,
      date: /^\d{4}-\d{2}-\d{2}$/.test(old.date) ? old.date : keyDate,
      opened: zoned.hhmm, timeZone: clock.timeZone,
      slot: {start: old.start, end: old.end, startAt: pacingIso(startAt), endAt: pacingIso(endAt)},
      window: {before: 0, after: 0, from: pacingIso(startAt), to: pacingIso(endAt)},
      migratedFrom: 1, slides, visits, pauses: [], fullscreenMs: null,
    };
  }

  // Whether an older viewer could still add to a schema-1 record: its date
  // is today or later in its own time zone and its slot has not ended.
  function pacingV1MayGrow(old, keyDate, now = Date.now()) {
    const date = /^\d{4}-\d{2}-\d{2}$/.test(old.date) ? old.date : keyDate;
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(old.end)) return false;
    try {
      const today = pacingClock(old.timeZone).parts(now);
      return today.date < date || (today.date === date && today.seconds < pacingSeconds(old.end));
    } catch (_) { return false; }
  }

  // The journal: one localStorage entry per segment,
  // "lecturedeck-pacing2:<path>:<date>:<segment>" -> {record, sync}.
  const pacingStore = {
    available: true,
    keyFor: record => `${PACING_PREFIX}${record.path}:${record.date}:${record.segment}`,
    keys() {
      const keys = [];
      try {
        for (let i = 0; i < localStorage.length; i += 1) {
          const key = localStorage.key(i);
          if (key && key.startsWith(PACING_PREFIX)) keys.push(key);
        }
      } catch (_) { this.available = false; }
      return keys;
    },
    read(key) {
      try {
        const value = JSON.parse(localStorage.getItem(key));
        if (value?.record?.schema !== 2 || !value.sync || !Number.isInteger(value.record.rev)) return null;
        return {key, record: value.record, sync: value.sync};
      } catch (_) { return null; }
    },
    all() { return this.keys().map(key => this.read(key)).filter(Boolean); },
    list({path, date} = {}) {
      return this.all().filter(entry => (path === undefined || pacingPath(entry.record.path) === path)
        && (date === undefined || entry.record.date === date));
    },
    pending() { return this.all().filter(pacingIsPending); },
    put(entry, json = JSON.stringify(entry.record)) {
      const value = `{"record":${json},"sync":${JSON.stringify(entry.sync)}}`;
      for (let attempt = 0; attempt < 100; attempt += 1) {
        try {
          localStorage.setItem(entry.key, value);
          this.available = true;
          return true;
        } catch (error) {
          // A full quota drops the oldest saved entries first. Pending and
          // refused entries are never dropped.
          const full = error?.name === "QuotaExceededError" || error?.code === 22;
          if (!full || !this.dropOldestSaved(entry.key)) break;
        }
      }
      this.available = false;
      return false;
    },
    // Store a response without taking a newer journal record backwards:
    // another tab may own the segment and still be writing it.
    putSync(entry) {
      if (entry.live) return this.put(entry);
      const stored = this.read(entry.key);
      if (stored && stored.record.rev > entry.record.rev) entry.record = stored.record;
      if (stored && (stored.sync.rev || 0) > (entry.sync.rev || 0)) entry.sync = stored.sync;
      if (entry.sync.state !== "refused") {
        entry.sync.state = (entry.sync.rev || 0) >= entry.record.rev ? "saved" : "pending";
      }
      return this.put(entry);
    },
    dropOldestSaved(except) {
      const saved = this.all().filter(entry => entry.key !== except && pacingIsSaved(entry))
        .sort((a, b) => a.record.date.localeCompare(b.record.date)
          || pacingFirstInstant(a.record) - pacingFirstInstant(b.record));
      if (!saved.length) return false;
      try { localStorage.removeItem(saved[0].key); } catch (_) { return false; }
      return true;
    },
    prune(now = Date.now()) {
      const cutoff = now - PACING_PRUNE_DAYS * 86400000;
      for (const entry of this.all()) {
        if (pacingIsSaved(entry) && Date.parse(`${entry.record.date}T00:00:00Z`) < cutoff) {
          try { localStorage.removeItem(entry.key); } catch (_) { /* optional */ }
        }
      }
    },
    // The server's unit for a record. A selector path names it; a bare
    // /webdeck/ record takes the sink's unit only on a page at /webdeck/
    // showing the same deck. Otherwise it stays unknown, and pending.
    attributeUnit(record, page = {}) {
      const selected = /^\/decks\/([^/]+)\/webdeck\/$/.exec(record.path || "");
      if (selected) {
        try { return decodeURIComponent(selected[1]); } catch (_) { return null; }
      }
      const sink = pacingSink();
      const pagePath = page.path ?? pacingPath();
      const deckTitle = page.deckTitle ?? (window.LECTUREDECK ? pacingDeckTitle(window.LECTUREDECK) : "");
      if (record.path === "/webdeck/" && pagePath === "/webdeck/" && typeof sink?.unit === "string"
        && sink.unit && deckTitle && deckTitle === record.deck) return sink.unit;
      return null;
    },
    // Convert schema-1 keys once. The v1 key and its ':latest' key are
    // kept; a marker records the conversion.
    migrateV1(page = {}) {
      const keys = [];
      try {
        for (let i = 0; i < localStorage.length; i += 1) keys.push(localStorage.key(i));
      } catch (_) { return 0; }
      let migrated = 0;
      for (const key of keys) {
        const match = /^lecturedeck-pacing:(.+):(\d{4}-\d{2}-\d{2})$/.exec(key || "");
        if (!match) continue;
        let old = null;
        try {
          if (localStorage.getItem(PACING_V1_MARK + key)) continue;
          old = JSON.parse(localStorage.getItem(key));
        } catch (_) { old = null; }
        // A tab still running an older viewer may be recording this one:
        // v1 never writes after the slot's end, so convert it only then.
        if (old?.schema === 1 && pacingV1MayGrow(old, match[2])) continue;
        const record = old?.schema === 1 ? pacingFromV1(old, match[1], match[2]) : null;
        if (!record) {
          console.warn(`lecturedeck: left the unreadable pacing record ${key} as it is`);
          continue;
        }
        record.unit = this.attributeUnit(record, page);
        const entry = {key: this.keyFor(record), record,
          sync: {rev: 0, file: null, at: null, state: "pending", error: null}};
        if (!this.put(entry)) break;
        try { localStorage.setItem(PACING_V1_MARK + key, entry.key); } catch (_) { break; }
        migrated += 1;
      }
      return migrated;
    },
  };

  // Keep the item whose window changed slide most recently wherever items
  // overlap (then the later start). Returns disjoint pieces and the time
  // claimed by more than one group.
  function pacingLatestStart(items) {
    const points = [...new Set(items.flatMap(item => [item.start, item.end]))].sort((a, b) => a - b);
    const queue = [...items].sort((a, b) => a.start - b.start);
    const rank = (a, b) => a.changedAt - b.changedAt || a.start - b.start || a.group - b.group || a.order - b.order;
    const pieces = [];
    let active = [], next = 0, overlapMs = 0;
    for (let p = 0; p < points.length - 1; p += 1) {
      const from = points[p], to = points[p + 1];
      while (next < queue.length && queue[next].start <= from) active.push(queue[next++]);
      active = active.filter(item => item.end > from);
      if (!active.length) continue;
      const winner = active.reduce((best, item) => rank(item, best) > 0 ? item : best);
      if (new Set(active.map(item => item.group)).size > 1) overlapMs += to - from;
      const last = pieces[pieces.length - 1];
      if (last && last.item === winner && last.end === from) last.end = to;
      else pieces.push({start: from, end: to, item: winner});
    }
    return {pieces, overlapMs};
  }

  // Follow each window through its own segments. A visit that continues
  // the previous visit's slide across a phase split, an uncredited gap (a
  // suspended or clock pause) or a rollover keeps the time its window last
  // changed slide (changedAt); any other visit starts a new one. A visit
  // changes slide only when its window showed another slide just before:
  // the first visit of a page load does not. A rollover is the segment
  // whose first instant is another segment's last.
  function pacingWindowVisits(segments) {
    const gapsOf = segment => (segment.pauses || [])
      .filter(pause => pause.why === "suspended" || pause.why === "clock")
      .map(pause => {
        const from = Date.parse(pause.startedAt);
        return [from, from + (Number(pause.durationMs) || 0)];
      });
    const order = segments.map((_, group) => group)
      .sort((a, b) => pacingFirstInstant(segments[a]) - pacingFirstInstant(segments[b]) || a - b);
    const tails = [];
    const flags = segments.map(() => []);
    for (const group of order) {
      const segment = segments[group];
      const first = pacingFirstInstant(segment);
      const parent = [...tails].reverse().find(tail => tail.at === first) || null;
      const own = gapsOf(segment);
      const gaps = parent ? [...parent.gaps, ...own] : own;
      let previous = parent?.last || null;
      (segment.visits || []).forEach((visit, i) => {
        const start = Date.parse(visit.startedAt);
        const end = start + (Number(visit.durationMs) || 0);
        let changedAt = start, slideChange = false;
        if (previous) {
          const same = visit.slideId === previous.slideId;
          const joined = previous.end === start || gaps.some(([from, to]) => from <= previous.end && to >= start);
          if (same && joined) changedAt = previous.changedAt;
          slideChange = !same;
        }
        flags[group][i] = {changedAt, slideChange};
        previous = {slideId: visit.slideId, end, changedAt};
      });
      tails.push({at: pacingLastInstant(segment), last: previous, gaps: own});
    }
    return flags;
  }

  function pacingIntervals(segments, field) {
    const flags = field === "visits" ? pacingWindowVisits(segments) : null;
    const items = [];
    segments.forEach((segment, group) => (segment[field] || []).forEach((value, order) => {
      const start = Date.parse(value.startedAt);
      const end = start + (Number(value.durationMs) || 0);
      const flag = flags?.[group][order] || {changedAt: start, slideChange: false};
      if (Number.isFinite(start) && end > start) items.push({start, end, group, order, value, ...flag});
    }));
    return items;
  }

  // Merge the segments of one host: each moment counts once, for the
  // window that changed slide most recently; overlapMs is the doubled time.
  // A piece is a slide change when its window changed slide right there.
  function mergeVisits(segments) {
    const {pieces, overlapMs} = pacingLatestStart(pacingIntervals(segments, "visits"));
    return {
      pieces: pieces.map(piece => ({
        start: piece.start, end: piece.end, slideId: piece.item.value.slideId,
        phase: piece.item.value.phase || "slot", segment: piece.item.group,
        slideChange: piece.item.slideChange && piece.start === piece.item.start,
      })),
      overlapMs,
    };
  }

  // Derived measures, as documented for agents in the README.
  function summarizePacing(segments, {mainSlideIds = []} = {}) {
    const ordered = [...segments].sort((a, b) => pacingFirstInstant(a) - pacingFirstInstant(b));
    const slides = {};
    ordered.forEach(segment => Object.assign(slides, segment.slides || {}));
    const {pieces, overlapMs} = mergeVisits(ordered);
    const slot = ordered[ordered.length - 1]?.slot || {};
    const slotStart = Date.parse(slot.startAt), slotEnd = Date.parse(slot.endAt);
    const slotMs = Number.isFinite(slotEnd - slotStart) ? Math.max(0, slotEnd - slotStart) : 0;
    const phaseMs = {before: 0, slot: 0, after: 0};
    const perSlide = new Map();
    const arrivals = [];
    const changes = [];
    let previousId = null, lastMainId = null, lastMainChange = null;
    for (const piece of pieces) {
      const ms = piece.end - piece.start;
      const phase = piece.phase in phaseMs ? piece.phase : "slot";
      phaseMs[phase] += ms;
      // An arrival puts another slide on screen. It is a slide change only
      // where its window changed slide: opening a page (the deck, a new tab,
      // a reload landing elsewhere) is not one, and neither is a phase
      // split, a gap or a rollover on the same slide.
      const arrival = piece.slideId !== previousId;
      const change = arrival && previousId !== null && piece.slideChange;
      previousId = piece.slideId;
      if (arrival) arrivals.push(piece);
      if (change) changes.push(piece);
      if (slides[piece.slideId]?.backup !== true) {
        // Coming back from the backup to the main slide shown before it is
        // not a main-slide change.
        if (change && piece.slideId !== lastMainId) lastMainChange = piece.start;
        lastMainId = piece.slideId;
      }
      const info = slides[piece.slideId] || {};
      const row = perSlide.get(piece.slideId) || {
        slideId: piece.slideId, number: Number(info.number) || 0, label: String(info.label ?? info.number ?? "?"),
        title: info.title || piece.slideId, section: info.section || "", backup: info.backup === true,
        firstAt: piece.start, totalMs: 0, arrivals: 0, beforeMs: 0, slotMs: 0, afterMs: 0,
      };
      row.totalMs += ms;
      row[`${phase}Ms`] += ms;
      if (arrival) row.arrivals += 1;
      perSlide.set(piece.slideId, row);
    }
    let furthest = null;
    for (const piece of pieces) {
      const info = slides[piece.slideId];
      if (!info || info.backup === true) continue;
      if (!furthest || info.number > furthest.number) furthest = {number: info.number, label: info.label, at: piece.start};
    }
    const shown = new Set(pieces.map(piece => piece.slideId));
    const notShown = mainSlideIds.map((id, i) => shown.has(id) ? 0 : i + 1).filter(Boolean);
    // Off slides in the slot: paused where some window logged a pause and
    // none showed a slide; untracked where nothing was recorded at all.
    const pausedByReason = {};
    let pausedMs = 0;
    if (slotMs) {
      let cursor = 0;
      for (const piece of pacingLatestStart(pacingIntervals(ordered, "pauses")).pieces) {
        const from = Math.max(piece.start, slotStart), to = Math.min(piece.end, slotEnd);
        if (to <= from) continue;
        while (cursor < pieces.length && pieces[cursor].end <= from) cursor += 1;
        let free = to - from;
        for (let i = cursor; i < pieces.length && pieces[i].start < to; i += 1) {
          free -= Math.max(0, Math.min(to, pieces[i].end) - Math.max(from, pieces[i].start));
        }
        if (free <= 0) continue;
        const why = piece.item.value.why || "paused";
        pausedByReason[why] = (pausedByReason[why] || 0) + free;
        pausedMs += free;
      }
    }
    const offSlidesMs = Math.max(0, slotMs - phaseMs.slot);
    const sections = new Map();
    let backup = null;
    for (const row of perSlide.values()) {
      const key = row.section || "—";
      let section = row.backup ? backup : sections.get(key);
      if (!section) {
        section = {name: row.backup ? "Backup slides" : key, backup: row.backup, firstAt: row.firstAt,
          minNumber: row.number, slides: [], beforeMs: 0, slotMs: 0, afterMs: 0};
        if (row.backup) backup = section;
        else sections.set(key, section);
      }
      section.firstAt = Math.min(section.firstAt, row.firstAt);
      section.minNumber = Math.min(section.minNumber, row.number);
      section.slides.push(row);
      section.beforeMs += row.beforeMs;
      section.slotMs += row.slotMs;
      section.afterMs += row.afterMs;
    }
    const sectionList = [...sections.values()].sort((a, b) => a.minNumber - b.minNumber);
    if (backup) sectionList.push(backup);
    sectionList.forEach(section => section.slides.sort((a, b) => a.number - b.number));
    const changesIn = phase => changes.filter(piece => piece.phase === phase).length;
    // How the recordings join: a rollover starts where the previous one
    // ended, a later start is a reload, an earlier one another window.
    const joins = {reloads: 0, rollovers: 0, windows: 0};
    let previousEnd = -Infinity;
    ordered.forEach((segment, i) => {
      const first = pacingFirstInstant(segment);
      if (i > 0) joins[first === previousEnd ? "rollovers" : first < previousEnd ? "windows" : "reloads"] += 1;
      previousEnd = Math.max(previousEnd, pacingLastInstant(segment));
    });
    return {
      segments: ordered.length,
      joins,
      migrated: ordered.some(segment => segment.migratedFrom === 1),
      overlapMs,
      slot: {start: slot.start, end: slot.end, startAt: slotStart, endAt: slotEnd, ms: slotMs},
      openFrom: pieces.length ? pieces[0].start : null,
      onScreenUntil: pieces.length ? pieces[pieces.length - 1].end : null,
      started: changes.length ? changes[0].start : null,
      lastMainChange,
      overrunMs: lastMainChange !== null && Number.isFinite(slotEnd) ? lastMainChange - slotEnd : null,
      furthest,
      mainTotal: mainSlideIds.length,
      notShown,
      beforeMs: phaseMs.before, inSlotMs: phaseMs.slot, afterMs: phaseMs.after,
      beforeChanges: changesIn("before"), slotChanges: changesIn("slot"), afterChanges: changesIn("after"),
      offSlidesMs, pausedMs, pausedByReason, untrackedMs: Math.max(0, offSlidesMs - pausedMs),
      sections: sectionList,
      slides: [...perSlide.values()],
      arrivals: arrivals.length,
      visits: ordered.reduce((n, segment) => n + (segment.visits || []).length, 0),
      pauses: ordered.reduce((n, segment) => n + (segment.pauses || []).length, 0),
    };
  }

  function pacingExportSummary(summary) {
    const at = ms => ms === null || !Number.isFinite(ms) ? null : pacingIso(ms);
    return {
      deckOpenFrom: at(summary.openFrom),
      onScreenUntil: at(summary.onScreenUntil),
      started: at(summary.started),
      lastMainSlideChange: at(summary.lastMainChange),
      overrunMs: summary.overrunMs,
      furthestMainSlide: summary.furthest
        ? {number: summary.furthest.number, label: summary.furthest.label, at: at(summary.furthest.at)} : null,
      mainSlides: summary.mainTotal,
      mainSlidesNotShown: summary.notShown,
      slotMs: summary.slot.ms,
      beforeMs: summary.beforeMs,
      inSlotMs: summary.inSlotMs,
      afterMs: summary.afterMs,
      slideChanges: {before: summary.beforeChanges, slot: summary.slotChanges, after: summary.afterChanges},
      offSlidesInSlotMs: summary.offSlidesMs,
      pausedInSlotMs: summary.pausedMs,
      pausedInSlotByReason: summary.pausedByReason,
      untrackedInSlotMs: summary.untrackedMs,
      overlapMs: summary.overlapMs,
      segments: summary.segments,
      migrated: summary.migrated,
      arrivals: summary.arrivals,
      sections: summary.sections.map(section => ({
        name: section.name, backup: section.backup, enteredAt: at(section.firstAt),
        slidesShown: section.slides.length, beforeMs: section.beforeMs,
        inSlotMs: section.slotMs, afterMs: section.afterMs,
      })),
      slides: summary.slides.map(row => ({
        slideId: row.slideId, number: row.number, label: row.label, title: row.title,
        section: row.section, backup: row.backup, firstAt: at(row.firstAt), totalMs: row.totalMs,
        arrivals: row.arrivals, beforeMs: row.beforeMs, inSlotMs: row.slotMs, afterMs: row.afterMs,
      })),
    };
  }

  // Saving to disk. Every request carries a whole segment; the server
  // keeps the highest revision, so retries and overlaps are harmless.
  const pacingDisk = {
    blocked: null, // {code, refused?}: this page may not write
    deckBlocked: null, // 404/422 code for this page's own deck
    blockedDates: new Set(), // 429: too many segments for the date
    failing: null, // {since, reason} while retrying
    refusal: null,
    lastSavedAt: 0,
    pendingOthers: 0, // older entries still being retried
    heldOthers: [], // reasons of older entries this server will not take
    sweeping: false,
    sweepBackoff: 0,
    sweepTimer: 0,
    listeners: new Set(),
    changed() {
      this.listeners.forEach(listener => {
        try { listener(); } catch (_) { /* a listener never stops the others */ }
      });
    },
  };

  function pacingCanSend(record) {
    const sink = pacingSink();
    if (!sink || sink.inert || typeof sink.save !== "function" || pacingDisk.blocked) return false;
    if (pacingDisk.deckBlocked && pacingPath(record.path) === pacingPath()) return false;
    return !pacingDisk.blockedDates.has(record.date);
  }

  function pacingFlush(entry, {closing = false} = {}) {
    const record = entry.record;
    if (entry.sync.state === "refused" || record.rev <= (entry.sync.rev || 0)) return;
    if (!pacingCanSend(record)) return;
    if (!record.unit) {
      record.unit = pacingStore.attributeUnit(record);
      if (!record.unit) return;
    }
    if (closing) {
      // A close-time save rides keepalive when it fits the browser's
      // budget. It may overlap an ordinary request; the revision check on
      // the server orders the two.
      if ((entry.sentRev || 0) >= record.rev) return;
      const body = JSON.stringify(record);
      if (pacingBytes(body) <= KEEPALIVE_MAX_BYTES) {
        pacingSend(entry, {keepalive: true, body});
        return;
      }
    }
    if (entry.inflight) {
      entry.again = true;
      return;
    }
    if (!closing && Date.now() < (entry.retryAt || 0)) return;
    pacingSend(entry);
  }

  function pacingSend(entry, {keepalive = false, body = JSON.stringify(entry.record)} = {}) {
    const sink = pacingSink();
    const rev = entry.record.rev;
    entry.sentRev = Math.max(entry.sentRev || 0, rev);
    entry.lastSentAt = Date.now();
    if (!keepalive) entry.inflight = true;
    let request;
    try { request = Promise.resolve(sink.save(JSON.parse(body), {keepalive})); }
    catch (_) { request = Promise.resolve(null); }
    return request
      .then(result => result && typeof result === "object" ? result : {ok: false, status: 0, error: "network"},
        () => ({ok: false, status: 0, error: "network"}))
      .then(result => {
        if (!keepalive) entry.inflight = false;
        pacingResult(entry, rev, result);
        if (!keepalive && entry.again) {
          entry.again = false;
          pacingFlush(entry);
        }
        return result;
      });
  }

  const pacingTransient = result => !result.ok && !PACING_FINAL.includes(Number(result.status) || 0);

  function pacingResult(entry, rev, result) {
    const status = Number(result.status) || 0;
    const code = pacingText(result.error || (status ? `http-${status}` : "network"), 60);
    const sync = entry.sync;
    const savedUpTo = value => {
      sync.rev = Math.max(sync.rev || 0, Number.isInteger(value) ? value : rev);
      sync.state = sync.rev >= entry.record.rev ? "saved" : "pending";
      sync.error = null;
      entry.backoff = 0;
      entry.retryAt = 0;
      pacingDisk.failing = null;
    };
    if (result.ok) {
      savedUpTo(result.rev);
      if (result.file) sync.file = pacingText(result.file, 300);
      sync.at = typeof result.savedAt === "string" ? result.savedAt : new Date().toISOString();
      pacingDisk.lastSavedAt = Date.now();
      if (entry.live) pacingDisk.refusal = null;
    } else if (status === 409 && code === "stale") {
      // The disk already holds this revision or a newer one.
      savedUpTo(result.rev);
    } else if (PACING_REFUSED.includes(status) || status === 409) {
      sync.state = "refused";
      sync.error = code;
      if (entry.live) pacingDisk.refusal = code;
      entry.onRefused?.();
    } else if (status === 403) {
      sync.error = code;
      pacingDisk.blocked = {code};
    } else if (status === 404 || status === 422) {
      // Browser-only for this deck when its own recording is refused.
      // An older entry stays pending with its reason: on a single-unit
      // serve every unit shares /webdeck/, and a date dropped from the
      // schedule says nothing about today's lecture.
      sync.error = code;
      if (entry.live && pacingPath(entry.record.path) === pacingPath()) pacingDisk.deckBlocked = code;
    } else if (status === 429) {
      sync.error = code;
      pacingDisk.blockedDates.add(entry.record.date);
    } else {
      sync.error = code;
      pacingDisk.failing ||= {
        since: Date.now(),
        reason: status === 0 ? "server unreachable" : status === 503 ? "server could not write"
          : status === 408 ? "request timed out" : `HTTP ${status}`,
      };
      if (!entry.sweep) {
        const delay = BACKOFF_S[Math.min(entry.backoff || 0, BACKOFF_S.length - 1)] * 1000;
        entry.backoff = (entry.backoff || 0) + 1;
        entry.retryAt = Date.now() + delay;
        clearTimeout(entry.retryTimer);
        entry.retryTimer = setTimeout(() => {
          entry.retryAt = 0;
          pacingFlush(entry);
        }, delay);
      }
    }
    pacingStore.putSync(entry);
    pacingDisk.changed();
  }

  // Answers after which this server will not take an older entry as things
  // stand (another unit, a date no longer scheduled, ...). The entry stays
  // pending for a later page load or another server, but is not retried here.
  const PACING_HELD = ["not-found", "disabled", "no-schedule", "not-scheduled", "wrong-unit", "wrong-path",
    "too-many-segments"];

  function pacingCountPending() {
    const others = pacingStore.pending().filter(entry => !pacingLive.has(entry.record.segment));
    const held = [];
    let retrying = 0;
    for (const entry of others) {
      if (PACING_HELD.includes(entry.sync.error)) held.push(entry.sync.error);
      else if (!entry.record.unit && !pacingStore.attributeUnit(entry.record)) held.push("unit unknown");
      else retrying += 1;
    }
    pacingDisk.pendingOthers = retrying;
    pacingDisk.heldOthers = held;
  }

  function pacingScheduleSweep() {
    clearTimeout(pacingDisk.sweepTimer);
    const delay = BACKOFF_S[Math.min(pacingDisk.sweepBackoff, BACKOFF_S.length - 1)] * 1000;
    pacingDisk.sweepBackoff += 1;
    pacingDisk.sweepTimer = setTimeout(pacingSweep, delay);
  }

  // Upload every pending journal entry on this origin, oldest first and
  // one at a time, each to its own record's endpoint.
  async function pacingSweep() {
    const sink = pacingSink();
    if (pacingDisk.sweeping || !sink || sink.inert || pacingDisk.blocked) return;
    pacingDisk.sweeping = true;
    let transient = false;
    try {
      const pending = pacingStore.pending().filter(entry => !pacingLive.has(entry.record.segment))
        .sort((a, b) => a.record.date.localeCompare(b.record.date)
          || pacingFirstInstant(a.record) - pacingFirstInstant(b.record));
      for (const entry of pending) {
        if (pacingDisk.blocked) break;
        if (!pacingCanSend(entry.record)) continue;
        if (!entry.record.unit) {
          entry.record.unit = pacingStore.attributeUnit(entry.record);
          if (!entry.record.unit) continue;
        }
        entry.sweep = true;
        if (pacingTransient(await pacingSend(entry))) {
          transient = true;
          break;
        }
      }
    } finally {
      pacingDisk.sweeping = false;
      pacingCountPending();
      if (transient) pacingScheduleSweep();
      else pacingDisk.sweepBackoff = 0;
      pacingDisk.changed();
    }
  }

  function pacingRecovery(spec) {
    const page = {path: pacingPath(), deckTitle: spec ? pacingDeckTitle(spec) : ""};
    try { pacingStore.migrateV1(page); } catch (error) { console.warn("lecturedeck: pacing migration stopped", error); }
    try { pacingStore.prune(); } catch (_) { /* optional */ }
    pacingCountPending();
    pacingDisk.changed();
    pacingSweep();
  }

  // Why this page saves only in the browser, or null when it saves to disk.
  function pacingBrowserOnlyReason(date) {
    const sink = pacingSink();
    const port = location.port || (location.protocol === "https:" ? "443" : "80");
    const local = `open the deck at http://127.0.0.1:${port} to save to disk`;
    const elsewhere = "only a browser on the computer serving the deck saves to disk";
    const proxied = "the deck is opened through a proxy, which never saves to disk";
    if (!sink) {
      return {
        absent: "this server does not save records yet: restart lecturedeck serve",
        off: "disk saving is off on this server",
        "not-this-machine": elsewhere,
        "use-local-address": local,
        proxied,
        static: "static copy",
        on: "reload the page to save to disk",
      }[serverPacing] || "this page has no disk saving";
    }
    if (sink.inert) return sink.inert === "automation" ? "automated browser" : `disk saving is off (${pacingText(sink.inert, 40)})`;
    const blocked = pacingDisk.blocked;
    if (blocked && !blocked.refused) {
      return {"not-same-machine": elsewhere, host: local, proxied}[blocked.code]
        || `the server refused this page (${blocked.code})`;
    }
    if (pacingDisk.deckBlocked) {
      return {
        disabled: "disk saving is off on this server",
        "no-schedule": "the server finds no schedule for this deck",
        "not-scheduled": "this date is not in the deck's schedule on the server",
        "wrong-unit": "the server serves this deck under another unit",
        "wrong-path": "the server serves this deck at another address",
      }[pacingDisk.deckBlocked] || `the server refused this deck (${pacingDisk.deckBlocked})`;
    }
    if (date && pacingDisk.blockedDates.has(date)) return "too many recordings for this date";
    return null;
  }

  function setupLecturePacer(timing, spec) {
    if (printMode || !Array.isArray(timing?.dates) || !document.querySelector("#lecture-clock")) return;
    let clock;
    try { clock = pacingClock(timing.timeZone); } catch (_) { return; }
    const dates = new Set(timing.dates.filter(date => /^\d{4}-\d{2}-\d{2}$/.test(date)));
    const start = pacingSeconds(timing.start), end = pacingSeconds(timing.end);
    const windowFrom = Math.max(0, start - PACING_LEAD_S);
    const windowTo = Math.min(86400, end + PACING_TAIL_S);
    const slides = Array.isArray(spec?.slides) ? spec.slides : [];
    const numbering = slideNumbering(slides);
    const path = pacingPath();
    const deckTitle = pacingDeckTitle(spec);
    const page = {path, deckTitle};
    const zonedParts = ms => clock.parts(ms);
    const hms = ms => zonedParts(ms).hms;
    const hm = ms => zonedParts(ms).hm;
    const slideIdAt = i => pacingId(slides[i]?.id, `slide-${i + 1}`);
    const mainSlideIds = slides.map((_, i) => i).filter(i => !numbering.inAppendix(i)).map(slideIdAt);
    const sectionAt = i => {
      let section = "Opening";
      for (let j = 0; j <= i; j += 1) {
        if (slides[j]?.type === "section") section = pacingText(htmlText(slides[j].title)) || section;
      }
      return section;
    };
    const titleAt = (i, frame) => {
      const heading = Number(frame?.dataset.index) === i ? frame.querySelector("h1")?.textContent : "";
      const slide = slides[i] || {};
      return pacingText(heading)
        || pacingText(htmlText(slide.title || slide.interactive?.title || slide.video?.title))
        || `Slide ${i + 1}`;
    };
    const fullscreen = () => Boolean(document.fullscreenElement || document.webkitFullscreenElement)
      || document.body.classList.contains("pseudo-fullscreen");

    const button = document.createElement("button");
    button.id = "pacing-button";
    button.type = "button";
    button.textContent = "Pacing";
    button.setAttribute("aria-haspopup", "dialog");
    controlsTools?.append(button);
    // Built once; opening re-renders only the body and the footer.
    const dialog = document.createElement("dialog");
    dialog.id = "pacing-dialog";
    dialog.className = "appearance-dialog pacing-dialog";
    dialog.setAttribute("aria-labelledby", "pacing-title");
    dialog.innerHTML = '<header class="pacing-head"><h2 id="pacing-title">Pacing</h2>'
      + '<button id="pacing-close" class="appearance-close" type="button">Close</button>'
      + '<select id="pacing-date" aria-label="Recorded date" hidden></select></header>'
      + '<div class="pacing-body" tabindex="0" role="region" aria-label="Pacing report"></div>'
      + '<footer class="pacing-foot"><p id="pacing-status" role="status" data-state="neutral"></p>'
      + '<button id="pacing-export" class="appearance-close" type="button">Export JSON</button></footer>';
    document.body.append(dialog);
    const titleNode = dialog.querySelector("#pacing-title");
    const dateSelect = dialog.querySelector("#pacing-date");
    const body = dialog.querySelector(".pacing-body");
    const status = dialog.querySelector("#pacing-status");
    const exportButton = dialog.querySelector("#pacing-export");

    let seg = null; // the open segment's journal entry
    let openVisit = null; // {visit, start, until, index}
    let openPause = null; // {pause, start, why}
    let last = null; // {wall, mono} of the previous sample
    let active = false;
    let gone = false;
    let urgent = false;
    let slideChanged = false;
    let debounceTimer = 0;
    let liveRefusals = 0;
    let selectedDate = null;
    let savedForDate = null;
    let probeState = null;
    let probing = false;
    const pageEntries = new Map();
    const finished = [];

    function newSegment(now, zoned) {
      const at = target => epochAtSecond(now, zoned.seconds, target);
      const bounds = {startAt: at(start), endAt: at(end), from: at(windowFrom), to: at(windowTo)};
      const record = {
        schema: 2, kind: "lecturedeck-pacing-segment", segment: pacingSegmentId(), rev: 0, unit: null,
        path, deck: deckTitle, viewer: VIEWER_VERSION, date: zoned.date, opened: zoned.hhmm,
        timeZone: clock.timeZone,
        slot: {start: timing.start, end: timing.end, startAt: pacingIso(bounds.startAt), endAt: pacingIso(bounds.endAt)},
        window: {before: PACING_LEAD_S / 60, after: PACING_TAIL_S / 60, from: pacingIso(bounds.from), to: pacingIso(bounds.to)},
        slides: {}, visits: [], pauses: [], fullscreenMs: 0,
      };
      record.unit = pacingStore.attributeUnit(record, page);
      const entry = {
        key: pacingStore.keyFor(record), record, bounds, live: true,
        sync: {rev: 0, file: null, at: null, state: "pending", error: null},
        sentRev: 0, inflight: false, again: false, retryAt: 0, backoff: 0, lastSentAt: 0,
      };
      entry.onRefused = () => refused(entry);
      pacingLive.add(record.segment);
      pageEntries.set(record.segment, entry);
      return entry;
    }

    const phaseAt = t => t < seg.bounds.startAt ? "before" : t < seg.bounds.endAt ? "slot" : "after";

    function startVisit(t, index) {
      const slideId = slideIdAt(index);
      const info = {number: index + 1, label: numbering.label(index),
        title: titleAt(index, deck.querySelector(".slide-frame")), section: sectionAt(index)};
      if (numbering.inAppendix(index)) info.backup = true;
      if (numbering.inReview(index)) info.review = true;
      seg.record.slides[slideId] = info;
      const visit = {slideId, startedAt: pacingIso(t), durationMs: 0, phase: phaseAt(t)};
      seg.record.visits.push(visit);
      openVisit = {visit, start: t, until: t, index};
    }

    function startPause(t, why) {
      const pause = {startedAt: pacingIso(t), durationMs: 0, why};
      seg.record.pauses.push(pause);
      openPause = {pause, start: t, why};
    }

    // Extend the open visit or pause to now, splitting a visit exactly at
    // a phase boundary. Returns whether the record changed.
    function advance(now) {
      const t = Math.min(now, seg.bounds.to);
      let changed = false;
      if (openVisit && t > openVisit.until) {
        const credit = t - openVisit.until;
        for (const boundary of [seg.bounds.startAt, seg.bounds.endAt]) {
          if (openVisit.start < boundary && boundary <= t) {
            openVisit.visit.durationMs = boundary - openVisit.start;
            startVisit(boundary, openVisit.index);
            urgent = true;
          }
        }
        openVisit.visit.durationMs = t - openVisit.start;
        openVisit.until = t;
        if (fullscreen()) seg.record.fullscreenMs += credit;
        changed = true;
      }
      if (openPause && t - openPause.start > openPause.pause.durationMs) {
        openPause.pause.durationMs = t - openPause.start;
        changed = true;
      }
      return changed;
    }

    function finish() {
      if (!seg) return;
      finished.push(seg);
      seg = null;
      openVisit = null;
      openPause = null;
    }

    function rollover(now, zoned) {
      const index = openVisit?.index;
      const why = openPause?.why;
      finish();
      seg = newSegment(now, zoned);
      // The current slide continues as a new visit, not an arrival.
      if (index !== undefined) startVisit(now, index);
      else if (why) startPause(now, why);
      seg.record.rev += 1;
      pacingStore.put(seg);
    }

    // A refused live segment rolls to a new one once; a second refusal
    // stops disk saving for this page.
    function refused(entry) {
      if (entry !== seg || !last) return;
      liveRefusals += 1;
      if (liveRefusals >= 2) {
        pacingDisk.blocked = {code: entry.sync.error, refused: true};
        return;
      }
      rollover(last.wall, zonedParts(last.wall));
      finished.length = 0;
      pacingFlush(seg);
    }

    function sample({quiet = false} = {}) {
      const now = Date.now(), mono = performance.now();
      const previous = last;
      last = {wall: now, mono};
      const dirty = new Set();
      if (seg && previous) {
        const dWall = now - previous.wall, dMono = mono - previous.mono;
        const skew = Math.abs(dWall - dMono) > SKEW_MS;
        // A hidden tab's timers are throttled, so only its pause may span
        // a long gap; an overview, report or dialog pause ends at the gap.
        const gap = openPause?.why !== "hidden" && (dWall > GAP_MS || dMono > GAP_MS);
        if (dWall < 0 || skew || gap) {
          // Sleep, frozen timers or a clock step: credit nothing. The
          // visit or pause stays ended at the previous sample.
          openVisit = null;
          openPause = null;
          const until = Math.min(Math.max(now, previous.wall), seg.bounds.to);
          seg.record.pauses.push({startedAt: pacingIso(previous.wall), durationMs: until - previous.wall,
            why: dWall < 0 || skew ? "clock" : "suspended"});
          dirty.add(seg);
          urgent = true;
          if (now < previous.wall) finish();
        } else if (advance(now)) dirty.add(seg);
        if (seg && now >= seg.bounds.to) {
          // The window is over: the visit closed at window.to.
          dirty.add(seg);
          finish();
        }
      }
      const zoned = zonedParts(now);
      const frame = deck.querySelector(".slide-frame");
      const index = Number(frame?.dataset.index);
      const inWindow = !gone && dates.has(zoned.date) && zoned.seconds >= windowFrom && zoned.seconds < windowTo;
      const showing = inWindow && Boolean(frame) && Number.isInteger(index);
      const why = document.visibilityState !== "visible" ? "hidden"
        : dialog.open ? "report"
          : pacingDialogOpen() ? "dialog"
            : document.body.classList.contains("overview-open") ? "overview" : null;
      const wasActive = active;
      active = showing && !why;
      if (!seg && active) {
        seg = newSegment(now, zoned);
        dirty.add(seg);
      }
      if (seg) {
        if (active) {
          if (openPause) openPause = null;
          if (!openVisit) {
            startVisit(now, index);
            dirty.add(seg);
          } else if (openVisit.index !== index) {
            startVisit(now, index);
            slideChanged = true;
            dirty.add(seg);
          }
        } else {
          if (openVisit) {
            openVisit = null;
            dirty.add(seg);
          }
          if (openPause && openPause.why !== why) openPause = null;
          if (why && showing && !openPause) {
            startPause(now, why);
            dirty.add(seg);
          }
        }
        if (wasActive !== active) urgent = true;
      }
      let roll = false;
      for (const entry of dirty) {
        entry.record.rev += 1;
        const json = JSON.stringify(entry.record);
        pacingStore.put(entry, json);
        if (entry === seg && pacingBytes(json) > ROLLOVER_BYTES) roll = true;
      }
      if (roll) {
        rollover(now, zoned);
        urgent = true;
      }
      if (quiet) {
        // The caller saves with keepalive instead.
        finished.length = 0;
        urgent = false;
        slideChanged = false;
      } else {
        while (finished.length) pacingFlush(finished.shift());
        if (seg) schedule(now);
      }
      button.dataset.recording = String(active);
      updateSaved();
      if (dialog.open) renderStatus();
    }

    function schedule(now) {
      if (urgent) {
        // A phase boundary, an active/paused transition or a gap.
        urgent = false;
        slideChanged = false;
        clearTimeout(debounceTimer);
        debounceTimer = 0;
        pacingFlush(seg);
      } else if (slideChanged) {
        // Paging through many slides becomes one send.
        slideChanged = false;
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          debounceTimer = 0;
          if (seg) pacingFlush(seg);
        }, CHANGE_DEBOUNCE_MS);
      } else if (!debounceTimer && now - (seg.lastSentAt || 0) >= HEARTBEAT_MS) {
        // While recording or paused: a growing pause (the report held
        // open after class) reaches disk too, and the footer stays true.
        pacingFlush(seg);
      }
    }

    function savedState(live) {
      if (pacingBrowserOnlyReason(live?.record.date)) return "browser";
      if (pacingDisk.failing || pacingDisk.blocked?.refused || live?.sync.state === "refused") return "failing";
      return "disk";
    }

    function updateSaved() {
      const saved = savedState(seg);
      button.dataset.saved = saved;
      button.title = active
        ? `Recording slide time · ${{disk: "saving to disk", browser: "saved in this browser only", failing: "disk saving failing"}[saved]}`
        : "Lecture pacing report";
    }

    const savedTime = at => Number.isFinite(Date.parse(at)) ? hms(Date.parse(at)) : "";

    function recordsFromText() {
      const pad = value => String(value).padStart(2, "0");
      const from = `${pad(Math.floor(windowFrom / 3600))}:${pad(Math.floor((windowFrom % 3600) / 60))}`;
      const today = zonedParts(Date.now());
      if (dates.has(today.date) && today.seconds < windowTo) return `records from ${from}`;
      const next = [...dates].sort().find(date => date > today.date);
      return next ? `records from ${from} on ${pacingDay(next)}` : "no teaching date ahead";
    }

    function statusInfo() {
      const live = seg || [...pageEntries.values()].pop() || null;
      if (pacingDisk.blocked?.refused) return ["error", `Disk refused this recording: ${pacingDisk.blocked.code}`];
      const reason = pacingBrowserOnlyReason(live?.record.date ?? selectedDate);
      if (reason && !pacingStore.available) {
        return ["error", `Kept only while this page is open — ${reason}; browser storage is unavailable, so export before closing`];
      }
      if (reason) return ["warn", `Saved in this browser only — ${reason}`];
      if (pacingDisk.failing) {
        return ["error", `Disk save failing since ${hms(pacingDisk.failing.since)} (${pacingDisk.failing.reason})`
          + " — retrying; every second is kept in this browser"];
      }
      if (live) {
        if (live.sync.state === "refused" || (pacingDisk.refusal && !live.sync.rev)) {
          return ["error", `Disk refused this recording: ${live.sync.error || pacingDisk.refusal}`];
        }
        if (live.sync.rev && (live.sync.rev >= live.record.rev
          || Date.now() - pacingDisk.lastSavedAt < HEARTBEAT_MS + 5000)) {
          return ["ok", `Saved to disk ${savedTime(live.sync.at)} · ${pacingShortFile(live.sync.file)}`, live.sync.file];
        }
        return ["warn", pacingDisk.lastSavedAt ? `Saving… last saved ${hms(pacingDisk.lastSavedAt)}` : "Saving…"];
      }
      const pending = pacingDisk.pendingOthers;
      if (pending) return ["warn", `${pending} recording${pending === 1 ? "" : "s"} not yet on disk — retrying`];
      if (savedForDate) {
        return ["ok", `Saved to disk ${savedTime(savedForDate.sync.at)} · ${pacingShortFile(savedForDate.sync.file)}`,
          savedForDate.sync.file];
      }
      if (probeState?.ok) {
        // Older entries this server will not take never hide the check.
        const held = pacingDisk.heldOthers;
        const note = held.length ? ` · ${held.length} older recording${held.length === 1 ? "" : "s"} not accepted`
          + ` by this server (${[...new Set(held)].join(", ")})` : "";
        return ["neutral", `Disk saving ready on this computer · ${recordsFromText()}${note}`];
      }
      if (probeState?.status === 503) return ["error", "Disk saving not ready — the unit folder is not writable"];
      if (probeState) return ["error", `Disk saving check failed (${probeState.error || probeState.status})`];
      return ["neutral", "Checking disk saving…"];
    }

    function renderStatus() {
      const [state, text, title] = statusInfo();
      status.dataset.state = state;
      status.textContent = text;
      if (title) status.title = title;
      else status.removeAttribute("title");
    }

    function probe() {
      const sink = pacingSink();
      if (probing || !sink || sink.inert || typeof sink.probe !== "function") return;
      if (probeState && Math.abs(Date.now() - probeState.at) < 30000) return;
      probing = true;
      let request;
      try { request = Promise.resolve(sink.probe(path)); } catch (_) { request = Promise.resolve(null); }
      request
        .then(result => result && typeof result === "object" ? result : {ok: false, status: 0, error: "network"},
          () => ({ok: false, status: 0, error: "network"}))
        .then(result => {
          const code = pacingText(result.error || "", 60);
          probeState = {ok: Boolean(result.ok), status: Number(result.status) || 0, error: code, at: Date.now()};
          if (probeState.status === 403 && !pacingDisk.blocked) pacingDisk.blocked = {code};
          if (probeState.status === 404 && code && !pacingDisk.deckBlocked) pacingDisk.deckBlocked = code;
        })
        .finally(() => {
          probing = false;
          pacingDisk.changed();
        });
    }

    function reportEntries() {
      const entries = new Map(pacingStore.list({path}).map(entry => [entry.key, entry]));
      for (const entry of pageEntries.values()) entries.set(entry.key, entry);
      return [...entries.values()];
    }

    const helpMarkup = () => `<p class="pacing-help">Records automatically on teaching dates from ${PACING_LEAD_S / 60} min before to ${PACING_TAIL_S / 60} min after the slot. Overview, dialogs and hidden tabs pause it; the photo viewer counts as time on its slide. Gaps over ${GAP_MS / 1000} s are never counted. Shows this browser's recordings; files on disk may include other browsers.</p>`;

    function timelineMarkup(segments, summary) {
      const rows = [];
      const slotStart = summary.slot.startAt, slotEnd = summary.slot.endAt;
      if (Number.isFinite(slotStart)) rows.push({at: slotStart, rank: 0, html: `<tr class="pacing-boundary"><td colspan="4">— ${escapeHtml(summary.slot.start)} scheduled start —</td></tr>`});
      if (Number.isFinite(slotEnd)) rows.push({at: slotEnd, rank: 0, html: `<tr class="pacing-boundary"><td colspan="4">— ${escapeHtml(summary.slot.end)} scheduled end —</td></tr>`});
      let previousEnd = -Infinity;
      segments.forEach((segment, i) => {
        const first = pacingFirstInstant(segment);
        if (i > 0 && first !== previousEnd) {
          const text = first < previousEnd ? "another window opened" : "page reloaded";
          rows.push({at: first, rank: 1, html: `<tr class="pacing-boundary pacing-reload"><td colspan="4">— ${text} —</td></tr>`});
        }
        previousEnd = Math.max(previousEnd, pacingLastInstant(segment));
        for (const visit of segment.visits || []) {
          const info = segment.slides?.[visit.slideId] || {};
          rows.push({at: Date.parse(visit.startedAt), rank: 3, html: `<tr data-phase="${escapeHtml(visit.phase)}"><td>${hms(Date.parse(visit.startedAt))}</td><td>${escapeHtml(info.label ?? info.number ?? "")}</td><td>${escapeHtml(info.title || visit.slideId)}</td><td>${pacingDuration(visit.durationMs)}</td></tr>`});
        }
        for (const pause of segment.pauses || []) {
          rows.push({at: Date.parse(pause.startedAt), rank: 2, html: `<tr class="pacing-pause"><td>${hms(Date.parse(pause.startedAt))}</td><td colspan="2">Paused · ${escapeHtml(pause.why)}</td><td>${pacingDuration(pause.durationMs)}</td></tr>`});
        }
      });
      rows.sort((a, b) => a.at - b.at || a.rank - b.rank);
      return `<details class="pacing-timeline"><summary>Timeline · ${summary.visits} visit${summary.visits === 1 ? "" : "s"} · ${summary.pauses} pause${summary.pauses === 1 ? "" : "s"}</summary><table><thead><tr><th scope="col">Time</th><th scope="col">Slide</th><th scope="col">Title</th><th scope="col">Duration</th></tr></thead><tbody>${rows.map(row => row.html).join("")}</tbody></table></details>`;
    }

    function reportMarkup(segments) {
      const s = summarizePacing(segments, {mainSlideIds});
      const slotStartText = s.slot.start || timing.start, slotEndText = s.slot.end || timing.end;
      const over = s.overrunMs !== null && s.overrunMs > 0;
      let headline = "No main-slide change recorded";
      if (s.lastMainChange !== null) {
        headline = `Last main-slide change ${hms(s.lastMainChange)}`;
        if (s.overrunMs !== null) {
          // In whole seconds floored like the wall times beside it (the
          // scheduled end is a whole second), so 09:01:27.150 reads 0:33
          // before 09:02. data-overrun-ms keeps the milliseconds.
          const seconds = Math.floor(s.overrunMs / 1000);
          headline += over ? ` · +${pacingDuration(seconds * 1000)} past ${slotEndText}`
            : ` · ${pacingDuration(-seconds * 1000)} before ${slotEndText}`;
        }
      }
      const facts = [s.started === null ? "No slide change yet" : `Started ${hms(s.started)} (first slide change)`];
      if (s.openFrom !== null) facts.push(`deck open ${hm(s.openFrom)}–${hm(s.onScreenUntil)}`);
      if (s.furthest && s.mainTotal) {
        facts.push(s.furthest.number >= s.mainTotal
          ? `reached slide ${s.furthest.number} of ${s.mainTotal} at ${hms(s.furthest.at)}`
          : `stopped at slide ${s.furthest.number} of ${s.mainTotal}`);
      }
      const percent = s.slot.ms ? Math.round((100 * s.inSlotMs) / s.slot.ms) : 0;
      const reasons = Object.entries(s.pausedByReason).sort((a, b) => b[1] - a[1])
        .map(([why, ms]) => `${why} ${pacingDuration(ms)}`).join(", ");
      const tile = (key, label, value, detail, flag = false) => `<div class="pacing-tile" data-tile="${key}"${flag ? ' data-over="true"' : ""}><span class="pacing-tile-label">${escapeHtml(label)}</span><strong class="pacing-tile-value">${escapeHtml(value)}</strong><span class="pacing-tile-detail">${escapeHtml(detail)}</span></div>`;
      const tiles = [
        tile("slot", "In slot", pacingDuration(s.inSlotMs), `${percent}% of ${pacingDuration(s.slot.ms)}`),
        tile("before", `Before ${slotStartText}`, pacingDuration(s.beforeMs),
          `${s.beforeChanges} slide change${s.beforeChanges === 1 ? "" : "s"}`),
        tile("after", `After ${slotEndText}`, pacingDuration(s.afterMs), s.afterMs > 0 ? "over" : "nothing after the end",
          s.afterMs > 0),
        tile("off", "Off slides in slot", pacingDuration(s.offSlidesMs),
          `paused ${pacingDuration(s.pausedMs)}${reasons ? ` (${reasons})` : ""} · no record ${pacingDuration(s.untrackedMs)}`),
      ].join("");
      const notes = [];
      if (s.overlapMs > 0) notes.push(`Two windows recorded at once for ${pacingDuration(s.overlapMs)}; counted once, for the most recently changed window.`);
      if (s.segments > 1) {
        // A rollover continues one page load in a new file; it is no reload.
        const {reloads, rollovers, windows} = s.joins;
        const how = [reloads ? `${reloads} page reload${reloads === 1 ? "" : "s"}` : "",
          rollovers ? `${rollovers} continued in a new file` : "",
          windows ? `${windows} other window${windows === 1 ? "" : "s"}` : ""].filter(Boolean).join(", ");
        notes.push(`${s.segments} recordings merged (${how}).`);
      }
      if (s.migrated) notes.push(`Migrated from browser storage (viewer 0.20–0.23): nothing was recorded before ${slotStartText} or after ${slotEndText}, and pauses were not logged.`);
      const backupName = section => {
        const labels = section.slides.map(row => row.label);
        const range = labels.length > 1 ? `${labels[0]}–${labels[labels.length - 1]}` : labels[0] || "";
        return `Backup slides (${range})`;
      };
      const sectionName = section => section.backup ? backupName(section) : section.name;
      const outside = section => [section.beforeMs ? `${pacingDuration(section.beforeMs)} before` : "",
        section.afterMs ? `${pacingDuration(section.afterMs)} after` : ""].filter(Boolean).join(" · ") || "—";
      const sectionRows = s.sections.map(section => `<tr${section.backup ? ' class="pacing-backup"' : ""}><th scope="row">${escapeHtml(sectionName(section))}</th><td>${hms(section.firstAt)}</td><td>${section.slides.length}</td><td>${pacingDuration(section.slotMs)}</td><td>${escapeHtml(outside(section))}</td></tr>`).join("");
      const notShown = s.notShown.length
        ? `Not shown: ${s.notShown.length === 1 ? "slide" : "slides"} ${pacingRanges(s.notShown)} (${s.notShown.length} main slide${s.notShown.length === 1 ? "" : "s"}), against the current deck`
        : s.mainTotal ? `All ${s.mainTotal} main slides of the current deck shown` : "";
      const slideRows = s.sections.map(section => `<tr class="pacing-group"><th colspan="5" scope="rowgroup">${escapeHtml(sectionName(section))}</th></tr>${section.slides.map(row => `<tr${row.afterMs ? ' data-after="true"' : ""}><td>${escapeHtml(row.label)}</td><td>${escapeHtml(row.title)}</td><td>${pacingDuration(row.totalMs)}</td><td>${row.arrivals}</td><td>${row.afterMs ? pacingDuration(row.afterMs) : ""}</td></tr>`).join("")}`).join("");
      return `<section id="pacing-headline" class="pacing-headline" data-overrun-ms="${s.overrunMs ?? ""}" data-in-slot-ms="${s.inSlotMs}" data-on-screen-until="${s.onScreenUntil ?? ""}"${over ? ' data-over="true"' : ""}><p class="pacing-headline-main">${escapeHtml(headline)}</p><p class="pacing-headline-facts">${escapeHtml(facts.join(" · "))}</p></section>`
        + `<div class="pacing-tiles">${tiles}</div>`
        + (notes.length ? `<ul class="pacing-notes">${notes.map(note => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : "")
        + `<table class="pacing-sections"><thead><tr><th scope="col">Section</th><th scope="col">Entered</th><th scope="col">Slides shown</th><th scope="col">In slot</th><th scope="col">Outside slot</th></tr></thead><tbody>${sectionRows}</tbody></table>`
        + (notShown ? `<p class="pacing-not-shown">${escapeHtml(notShown)}</p>` : "")
        + `<details class="pacing-slides"><summary>Per-slide time · ${s.slides.length} slide${s.slides.length === 1 ? "" : "s"} · ${s.visits} visit${s.visits === 1 ? "" : "s"}</summary><table><thead><tr><th scope="col">Slide</th><th scope="col">Title</th><th scope="col">Time</th><th scope="col">Arrivals</th><th scope="col">After end</th></tr></thead><tbody>${slideRows}</tbody></table></details>`
        + timelineMarkup(segments, s)
        + helpMarkup();
    }

    function renderPacingReport(requested) {
      const entries = reportEntries();
      const recorded = [...new Set(entries.map(entry => entry.record.date))].sort();
      const today = zonedParts(Date.now()).date;
      const date = recorded.includes(requested) ? requested
        : recorded.includes(today) ? today : recorded[recorded.length - 1] || null;
      selectedDate = date;
      dateSelect.hidden = recorded.length <= 1;
      dateSelect.innerHTML = [...recorded].reverse().map(value => `<option value="${escapeHtml(value)}"${value === date ? " selected" : ""}>${escapeHtml(pacingDay(value, true))}</option>`).join("");
      const forDate = entries.filter(entry => entry.record.date === date)
        .sort((a, b) => pacingFirstInstant(a.record) - pacingFirstInstant(b.record));
      const segments = forDate.map(entry => entry.record);
      savedForDate = forDate.filter(entry => entry.sync.file && entry.sync.at).pop() || null;
      const slot = segments.length ? segments[segments.length - 1].slot : {start: timing.start, end: timing.end};
      titleNode.textContent = date ? `Pacing · ${pacingDay(date)} · ${slot.start}–${slot.end}` : "Pacing";
      exportButton.disabled = !segments.length;
      body.innerHTML = segments.length ? reportMarkup(segments)
        : `<p class="pacing-empty">No recorded lecture yet.</p>${helpMarkup()}`;
      renderStatus();
    }

    function openReport() {
      if (!dialog.open) dialog.showModal();
      // The report pause starts now; that sends the latest state to disk.
      sample();
      for (const entry of pageEntries.values()) pacingFlush(entry);
      pacingCountPending();
      renderPacingReport(selectedDate);
      body.scrollTop = 0;
      // Keys and the trackpad scroll the report; Escape closes it.
      body.focus({preventScroll: true});
      probe();
    }

    function exportReport() {
      const segments = reportEntries().filter(entry => entry.record.date === selectedDate)
        .map(entry => entry.record).sort((a, b) => pacingFirstInstant(a) - pacingFirstInstant(b));
      if (!segments.length) return;
      const unit = segments.find(record => record.unit)?.unit || pacingSink()?.unit || null;
      const payload = {
        schema: 2, kind: "lecturedeck-pacing-export", date: selectedDate, unit, deck: deckTitle, path,
        exportedAt: new Date().toISOString(),
        summary: pacingExportSummary(summarizePacing(segments, {mainSlideIds})),
        segments,
      };
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 1)], {type: "application/json"}));
      const link = document.createElement("a");
      link.href = url;
      // Named like the disk records (owner: "No lecture name, no time. Only date.").
      link.download = `${selectedDate}_${segments[0].opened}_${pacingSlug(unit, deckTitle)}_export.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    button.addEventListener("click", openReport);
    dialog.querySelector("#pacing-close").addEventListener("click", () => dialog.close());
    exportButton.addEventListener("click", exportReport);
    dateSelect.addEventListener("change", () => {
      renderPacingReport(dateSelect.value);
      body.scrollTop = 0;
    });
    dialog.addEventListener("click", event => {
      // The backdrop belongs to the dialog element itself.
      if (event.target !== dialog) return;
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right
        || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
    });
    dialog.addEventListener("close", () => {
      sample();
      const usable = node => node && !node.closest("[inert]") && node.getClientRects().length > 0;
      [button, controlsToggle, mobileMenuButton].find(usable)?.focus();
    });

    function closingSave() {
      for (const entry of pageEntries.values()) pacingFlush(entry, {closing: true});
    }
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "hidden") {
        sample();
        return;
      }
      sample({quiet: true});
      closingSave();
    });
    addEventListener("pagehide", () => {
      sample({quiet: true});
      // The tab is going away: the visit ends at this last sample. Time
      // with the tab closed is the gap between segments.
      gone = true;
      finish();
      finished.length = 0;
      closingSave();
    });
    addEventListener("pageshow", event => {
      if (!event.persisted) return;
      gone = false;
      last = null;
      sample();
    });
    pacingDisk.listeners.add(() => {
      updateSaved();
      if (dialog.open) renderStatus();
    });
    const observer = new MutationObserver(() => sample());
    observer.observe(deck, {childList: true});
    observer.observe(document.body, {attributes: true, attributeFilter: ["class"]});
    document.querySelectorAll("dialog").forEach(node => observer.observe(node, {attributes: true, attributeFilter: ["open"]}));
    sample();
    setInterval(() => sample(), 1000);
  }

  function boot(rawSpec) {
    const spec = {
      meta: rawSpec.meta || {},
      slides: Array.isArray(rawSpec.slides) ? rawSpec.slides : [],
    };
    const numbering = slideNumbering(spec.slides);
    setFavicon(spec.meta.favicon);
    window.LECTUREDECK = spec;
    const clampIndex = value => Math.max(0, Math.min(spec.slides.length - 1, value));
    const requested = parseSlideHash(location.hash) || {index: 0, step: 0};
    let index = clampIndex(requested.index);
    // Step-by-step reveals on the slide shown. stepItems are its rendered
    // [data-step] elements, stepLevels the distinct step numbers among them
    // in ascending order, and revealed how many of those levels are shown.
    let stepItems = [];
    let stepLevels = [];
    let revealed = 0;
    let stepIndicator = null;
    const stepOriginal = new WeakMap();
    let deckFullscreenWasActive = false;
    let deliberateNativeFullscreenExit = false;
    let controlsExpanded = false;
    // Laser pointer state. Declared here, before render() can run, so the
    // renderer can repaint a lit dot without a temporal-dead-zone guard. The
    // element itself is created only after the print-mode branch returns.
    let laser = null;
    let laserOn = false;
    // The photo viewer, built after the print-mode return like the laser:
    // print pages and PDF exports never contain it.
    let photoViewer = null;
    // Photo hotspots, built after the print-mode return too.
    let hotspots = null;

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

    // A viewer-rendered object (figure, card, formula, interactive, video)
    // joins a step through its own `step` field; slide HTML uses data-step.
    const stepAttribute = item => Number.isInteger(item?.step) && item.step > 0 ? ` data-step="${item.step}"` : "";

    function figureMarkup(figure, figureIndex) {
      const caption = figure.caption || figure.source ? `<figcaption>${figure.caption || ""}${figure.source ? `<strong>${figure.source}</strong>` : ""}</figcaption>` : "";
      const geometry = figureGeometry(figure);
      const style = geometry.x || geometry.y || geometry.scale !== 1 ? ` style="transform: translate(${geometry.x}px, ${geometry.y}px) scale(${geometry.scale});"` : "";
      const id = figure.id ? ` data-figure-id="${escapeHtml(figure.id)}"` : "";
      return `<figure class="figure-card" data-figure-index="${figureIndex}"${id}${stepAttribute(figure)}${style}><img src="${escapeHtml(figure.src)}" alt="${escapeHtml(figure.alt || figure.caption || "Lecture figure")}">${caption}</figure>`;
    }

    function formulaMarkup(formula) {
      if (!formula) return "";
      if (typeof formula === "string") return `<div class="formula formula-plain">${escapeHtml(formula)}</div>`;
      const math = formula.mathml || formula.html || "";
      const gloss = (formula.gloss || []).map(item => `<span>${item}</span>`).join("");
      return `<div class="formula formula-structured"${stepAttribute(formula)}>${formula.label ? `<p class="formula-label">${escapeHtml(formula.label)}</p>` : ""}<div class="formula-math">${math}</div>${gloss ? `<div class="formula-gloss">${gloss}</div>` : ""}</div>`;
    }

    function cardsMarkup(cards = []) {
      if (!cards.length) return "";
      return `<div class="concept-cards count-${Math.min(cards.length, 3)}">${cards.map(card => `<div class="concept-card"${stepAttribute(card)}>${card.label ? `<p class="card-label">${card.label}</p>` : ""}<p class="card-value">${card.value || ""}</p>${card.detail ? `<p class="card-detail">${card.detail}</p>` : ""}</div>`).join("")}</div>`;
    }

    function interactiveMarkup(interactive, thumbnail = false) {
      if (!interactive) return "";
      const title = interactive.title || "Interactive demonstration";
      if (thumbnail) return `<div class="interactive-placeholder">${escapeHtml(title)}</div>`;
      // A stepped page loads when its step appears (applySteps), so an
      // animation starts in front of the audience instead of running unseen.
      const step = stepAttribute(interactive);
      const source = `${step ? "data-step-src" : "src"}="${escapeHtml(interactive.src)}"`;
      return `<div class="interactive-frame"${step}><iframe ${source} title="${escapeHtml(title)}" loading="eager" referrerpolicy="no-referrer"></iframe></div>`;
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
      return `<figure class="video-card"${stepAttribute(video)}><video class="lecture-video" controls playsinline preload="metadata" aria-label="${escapeHtml(title)}"${poster}${video.muted ? " muted" : ""}${video.loop ? " loop" : ""}>${sourceMarkup}${trackMarkup}<p>Your browser cannot play this local video.</p></video>${caption}</figure>`;
    }

    // Slide HTML with every data-step dropped: for markup shown on slides
    // other than the one that wrote it, where a step would hide part of an
    // unrelated slide.
    function withoutSteps(html) {
      const text = String(html ?? "");
      if (!/data-step/i.test(text)) return text;
      const template = document.createElement("template");
      template.innerHTML = text;
      template.content.querySelectorAll("[data-step]").forEach(node => node.removeAttribute("data-step"));
      return template.innerHTML;
    }

    // The part label of slide i: the eyebrow or title of the last section
    // slide at or before it. A section slide keeps its own steps in it (its
    // eyebrow repeats its stepped title); later slides and the opening label
    // never inherit them.
    function partLabel(i) {
      let label = spec.meta.opening || "OPENING";
      let from = -1;
      for (let j = 0; j <= i; j += 1) {
        const candidate = spec.slides[j];
        if (candidate.type === "section" && (candidate.eyebrow || candidate.title)) {
          label = candidate.eyebrow || candidate.title;
          from = j;
        }
      }
      return from === i ? label : withoutSteps(label);
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
      const footer = chromeFree ? "" : `<footer class="slide-foot"><span class="source">${slide.source || ""}</span><span class="footer-nav"><span class="course-name">${withoutSteps(spec.meta.section || "")}</span><span class="page-number" data-fit="${numbering.widest}">${numbering.position(i)}</span></span></footer>`;
      const slideId = slide.id ? ` data-slide-id="${escapeHtml(slide.id)}"` : "";
      const appendix = numbering.inAppendix(i) ? ` data-appendix="true"`
        : numbering.inReview(i) ? ` data-review="true"` : "";
      return `<article class="slide-frame kind-${escapeHtml(slide.type || "content")}${slide.className ? ` ${escapeHtml(slide.className)}` : ""}${chromeFree ? " chrome-free" : ""}" data-accent="${escapeHtml(slide.accent || partAccent(i))}" data-index="${i}"${slideId}${appendix} aria-label="${numbering.ariaLabel(i, escapeHtml(slideTitleText(slide, i)))}">${header}<section class="slide-body layout-${layout}">${body}</section>${footer}</article>`;
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
      if (touchReview.matches) {
        presentationControls.style.left = "";
        presentationControls.style.top = "";
        presentationControls.classList.remove("has-safe-space");
        presentationControls.classList.toggle("is-expanded", controlsExpanded);
        controlsTools.setAttribute("aria-hidden", String(!controlsExpanded));
        controlsTools.inert = !controlsExpanded;
        mobileMenuButton?.setAttribute("aria-expanded", String(controlsExpanded));
        touchControlsButton?.setAttribute("aria-expanded", String(controlsExpanded));
        touchControlsButton?.setAttribute("aria-label", `${controlsExpanded ? "Hide" : "Show"} presentation controls`);
        return;
      }
      const frameLeft = (innerWidth - frameWidth * scale) / 2;
      const frameTop = (innerHeight - frameHeight * scale) / 2;
      const frameBottom = frameTop + frameHeight * scale;
      const gutter = 8;
      // Reserve the expanded height even while tools are collapsed. Measuring
      // the current state makes safe-space detection oscillate at the boundary.
      const previousDisplay = controlsTools.style.display;
      controlsTools.style.display = "flex";
      const expandedHeight = Math.max(controlsToggle.offsetHeight, controlsTools.offsetHeight, 38);
      controlsTools.style.display = previousDisplay;
      for (let pass = 0; pass < 2; pass += 1) {
        const controlsHeight = expandedHeight;
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
      document.body.classList.toggle("touch-review", touchReview.matches);
      document.body.classList.toggle("mobile-controls-open", touchReview.matches && controlsExpanded);
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
      // Full screen reflows the canvas: the video expand controls and the
      // hotspot rings follow.
      photoViewer?.placeExpanders();
      hotspots?.place();
    }

    // ---------------------------------------------------------------
    // Step-by-step reveals. Any element of the live slide carrying
    // data-step="N" (N a positive integer) is a step; everything else is
    // always shown. Next reveals the next step number still hidden, then
    // advances; Previous hides the last one shown, then goes back. A hidden
    // step keeps its box (visibility, not display), so nothing reflows. The
    // overview, print, the narration skeleton and every dialog never hide
    // anything: only the live slide is ever stepped.
    const STEP_VALUE = /^[1-9]\d*$/;
    const isShown = node => typeof node.checkVisibility === "function"
      ? node.checkVisibility() : node.getClientRects().length > 0;
    const shownStep = () => revealed ? stepLevels[revealed - 1] : 0;
    // Boxes the viewer draws around authored HTML, each with its own
    // background, rule or divider.
    const STEP_BOXES = ".figure-card > figcaption, .video-card > figcaption, .copy > .quote, .formula-gloss > span";

    // A step that is the whole content of such a box takes the box with it,
    // so no empty caption bar or gloss divider waits on screen. The number
    // moves to the box, so styling hooks see one step, not two.
    function stepBox(node, value) {
      const box = node.parentElement;
      if (!box?.matches(STEP_BOXES) || box.hasAttribute("data-step")) return node;
      const alone = [...box.childNodes].every(child => child === node
        || (child.nodeType === Node.TEXT_NODE && !child.textContent.trim()));
      if (!alone) return node;
      box.setAttribute("data-step", value);
      node.removeAttribute("data-step");
      return box;
    }

    // Every element of the live slide with a valid data-step is a step item,
    // whether or not the layout shows it right now: deck.css may show one
    // twin of a dark/light figure pair per theme, or drop a block below some
    // width, and that item must already be hidden when it appears. A step
    // nested in a later one cannot show before it, so it simply appears with
    // it and is no step of its own.
    function collectSteps(frame) {
      stepItems = [];
      const effective = new Map();
      const enclosing = node => {
        for (let up = node.parentElement?.closest("[data-step]"); up; up = up.parentElement?.closest("[data-step]")) {
          if (effective.has(up)) return effective.get(up);
        }
        return 0;
      };
      for (const node of frame ? frame.querySelectorAll("[data-step]") : []) {
        const value = (node.getAttribute("data-step") || "").trim();
        // check rejects other values; the viewer simply shows them.
        if (!STEP_VALUE.test(value)) continue;
        if (Number(value) <= enclosing(node)) {
          node.removeAttribute("data-step");
          continue;
        }
        const target = stepBox(node, value);
        effective.set(target, Number(value));
        stepOriginal.set(target, {ariaHidden: target.getAttribute("aria-hidden"), inert: target.hasAttribute("inert")});
        stepItems.push({node: target, step: Number(value)});
      }
      countSteps();
    }

    // The levels a press can reveal: the numbers of the items the layout
    // shows right now (checkVisibility ignores visibility, so a hidden step
    // still counts). Content the layout never shows (a full-canvas
    // interactive hides its copy, deck.css may set display: none) is no
    // level: a press must always reveal something. A frame that is not laid
    // out at all (the deck behind the overview) cannot tell, and counts all.
    function countSteps() {
      const frame = deck.querySelector(".slide-frame");
      const measurable = Boolean(frame) && frame.getClientRects().length > 0;
      const live = measurable ? stepItems.filter(item => isShown(item.node)) : stepItems;
      stepLevels = [...new Set(live.map(item => item.step))].sort((a, b) => a - b);
    }

    // A theme switch, a resize or another body class can show or hide
    // stepped content: recount the levels, keeping the step on screen.
    function refreshSteps() {
      if (!overview.hidden || !stepItems.length) return;
      const through = shownStep();
      const before = stepLevels.join();
      countSteps();
      if (stepLevels.join() === before) return;
      revealed = stepLevels.filter(level => level <= through).length;
      applySteps();
      updateNavigation();
    }

    function pauseMedia(node) {
      const media = node.matches("video, audio") ? [node] : [];
      media.push(...node.querySelectorAll("video, audio"));
      for (const element of media) {
        try { element.pause(); } catch (_) { /* nothing is playing */ }
      }
    }

    function applySteps() {
      const through = shownStep();
      for (const {node, step} of stepItems) {
        const hidden = step > through;
        node.classList.toggle("step-hidden", hidden);
        node.classList.toggle("step-current", !hidden && step === through);
        const original = stepOriginal.get(node) || {ariaHidden: null, inert: false};
        if (hidden) {
          // Focus leaves a step as it hides, also from inside an embedded
          // page: an inert iframe would keep the keyboard and the clicker.
          if (node.contains(document.activeElement)) document.activeElement.blur();
          node.setAttribute("aria-hidden", "true");
          if (node instanceof HTMLElement) node.setAttribute("inert", "");
          // A step stepped back out of view must not keep playing sound.
          pauseMedia(node);
        } else {
          if (original.ariaHidden === null) node.removeAttribute("aria-hidden");
          else node.setAttribute("aria-hidden", original.ariaHidden);
          if (node instanceof HTMLElement) node.toggleAttribute("inert", original.inert);
          // A stepped interactive page loads the first time it appears and
          // stays loaded when stepped back.
          const pending = node.matches(".interactive-frame") ? node.querySelector(":scope > iframe[data-step-src]") : null;
          if (pending) {
            pending.src = pending.getAttribute("data-step-src");
            pending.removeAttribute("data-step-src");
          }
        }
      }
      const frame = deck.querySelector(".slide-frame");
      if (!frame) return;
      // A video's expand control shows and hides with the video's step; a
      // hotspot's popup closes when its figure steps out of view.
      photoViewer?.placeExpanders();
      hotspots?.stepped();
      if (stepLevels.length) {
        frame.dataset.stepCount = String(stepLevels.length);
        frame.dataset.stepShown = String(revealed);
        frame.dataset.stepCurrent = String(through);
      } else {
        delete frame.dataset.stepCount;
        delete frame.dataset.stepShown;
        delete frame.dataset.stepCurrent;
      }
    }

    // Buttons, the address and the step dots follow the slide and its step.
    function updateNavigation() {
      const open = !overview.hidden;
      previousButton.disabled = open || (index === 0 && revealed === 0);
      nextButton.disabled = open || (index === spec.slides.length - 1 && revealed === stepLevels.length);
      const through = shownStep();
      history.replaceState(null, "", through ? `#/${index}.${through}` : `#/${index}`);
      // Filled marks for steps shown, open ones for steps to come, drawn at
      // a fixed size, so stepping never changes their width.
      const marks = stepLevels.map((_, n) => `<i${n < revealed ? ' class="shown"' : ""}></i>`).join("");
      // The same dots under the live slide's page number, where the
      // presenter looks: the controls strip is often collapsed. The cue is
      // positioned out of the layout, so a slide with steps, any number of
      // them and any step shown, leaves the page number, the course name
      // and the source line exactly where every other slide has them.
      const footerNav = deck.querySelector(".slide-frame .footer-nav");
      let cue = footerNav?.querySelector(":scope > .step-cue") || null;
      if (!stepLevels.length) cue?.remove();
      else if (footerNav) {
        if (!cue) {
          cue = document.createElement("span");
          cue.className = "step-cue";
          cue.setAttribute("aria-hidden", "true");
          footerNav.append(cue);
        }
        cue.innerHTML = marks;
      }
      if (!stepIndicator) return;
      stepIndicator.hidden = !stepLevels.length;
      if (!stepLevels.length) return;
      stepIndicator.innerHTML = marks;
      const label = `Step ${revealed} of ${stepLevels.length}`;
      stepIndicator.setAttribute("aria-label", label);
      stepIndicator.title = label;
    }

    function setRevealed(count) {
      const next = Math.max(0, Math.min(stepLevels.length, count));
      // Same count: still rewrite the address, so "#/N.9" on a whole slide
      // reads "#/N.2" whichever way it arrived.
      if (next === revealed) { updateNavigation(); return; }
      revealed = next;
      applySteps();
      updateNavigation();
    }

    // stepTarget reveals every step numbered at or below it: 0 shows only
    // the unstepped content, Infinity shows the whole slide.
    function render(stepTarget = 0) {
      if (!spec.slides.length) return;
      // A photo never stays open over a slide it does not belong to.
      photoViewer?.close();
      document.body.classList.toggle("immersive-slide", spec.slides[index].chrome === false);
      deck.innerHTML = slideMarkup(spec.slides[index], index);
      const frame = deck.querySelector(".slide-frame");
      // Steps take their first state without a fade.
      frame?.classList.add("steps-settling");
      collectSteps(frame);
      revealed = stepLevels.filter(step => step <= stepTarget).length;
      applySteps();
      fitFormulas(deck);
      counter.textContent = numbering.position(index);
      if (numbering.hasAppendix) document.body.classList.toggle("in-appendix", numbering.inAppendix(index));
      if (numbering.hasReview) document.body.classList.toggle("in-review", numbering.inReview(index));
      document.title = typeof spec.meta.tabTitle === "string" && spec.meta.tabTitle.trim()
        ? spec.meta.tabTitle.trim()
        : `${slideTitleText(spec.slides[index], index)} · ${spec.meta.title || "Lecturedeck"}`;
      updateNavigation();
      if (!overview.hidden) overview.querySelectorAll(".overview-card").forEach(card => card.setAttribute("aria-current", String(Number(card.dataset.index) === index)));
      scaleCurrent();
      photoViewer?.decorate(frame);
      hotspots?.decorate(frame);
      if (frame) {
        void frame.offsetWidth; // commit the settled state before fades return
        frame.classList.remove("steps-settling");
      }
      // Keep a lit laser on the accent of the slide it is now over.
      if (laserOn) paintLaser();
    }

    async function renderPrintDeck() {
      document.body.classList.add("print-deck");
      deck.innerHTML = spec.slides.map((slide, i) => slideMarkup(slide, i, true)).join("");
      // A PDF has no router: anchor every page and point `#/N` links at it,
      // resolved as the live viewer resolves the hash, so Chromium writes
      // them as jumps inside the document instead of dead localhost URLs.
      deck.querySelectorAll(":scope > .slide-frame").forEach(frame => { frame.id = `slide-${frame.dataset.index}`; });
      deck.querySelectorAll('a[href^="#/"]').forEach(link => {
        const target = clampIndex(parseSlideHash(link.getAttribute("href"))?.index || 0);
        link.setAttribute("href", `#slide-${target}`);
      });
      document.title = spec.meta.tabTitle?.trim() || spec.meta.title || "Lecturedeck";
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

    // A jump (Home, End, the overview, a #/N link) lands on a slide with the
    // steps numbered at or below `step` shown; staying on the same slide
    // only moves its step.
    function show(target, step = 0) {
      const clamped = clampIndex(target);
      if (clamped !== index) {
        index = clamped;
        render(step);
      } else {
        setRevealed(stepLevels.filter(level => level <= step).length);
      }
    }

    // Whole slides, steps ignored (Shift with the paging keys, and every
    // press while the overview is open): the next slide opens bare, the
    // previous one whole.
    function nextSlide() {
      if (index < spec.slides.length - 1) show(index + 1, 0);
    }

    function previousSlide() {
      if (index > 0) show(index - 1, Infinity);
    }

    // Next reveals the next step; on a fully shown slide it advances, and
    // the next slide opens with none of its steps shown. The overview pages
    // whole slides: a press there never changes a slide nobody can see.
    function next() {
      if (!overview.hidden) nextSlide();
      else if (revealed < stepLevels.length) setRevealed(revealed + 1);
      else if (index < spec.slides.length - 1) {
        index += 1;
        render(0);
      }
    }

    // Previous hides the last step shown; on a bare slide it goes back, and
    // the previous slide opens fully revealed, as it was left.
    function previous() {
      if (!overview.hidden) previousSlide();
      else if (revealed > 0) setRevealed(revealed - 1);
      else if (index > 0) {
        index -= 1;
        render(Infinity);
      }
    }

    const turn = direction => (direction > 0 ? next() : previous());

    function isNativeFullscreen() {
      return Boolean(document.fullscreenElement || document.webkitFullscreenElement);
    }

    function updateFullscreenButtons() {
      const nativeElement = document.fullscreenElement || document.webkitFullscreenElement;
      const nativeActive = Boolean(nativeElement);
      const escapedNativeFullscreen = (
        deckFullscreenWasActive && !nativeActive && !deliberateNativeFullscreenExit
      );
      // Video fullscreen belongs to its player; exiting it must preserve the slide.
      deckFullscreenWasActive = nativeElement === document.documentElement;
      if (!nativeActive) deliberateNativeFullscreenExit = false;
      const active = nativeActive || document.body.classList.contains("pseudo-fullscreen");
      fullscreenButtons.forEach(button => {
        button.textContent = active ? "Exit full screen" : "Full screen";
        button.setAttribute("aria-pressed", String(active));
      });
      requestAnimationFrame(scaleCurrent);
      // Escape that leaves native fullscreen opens the overview, but never
      // behind an open dialog: the same Escape closed that dialog. Over a
      // photo, the browser took the Escape meant for the photo: close it.
      if (escapedNativeFullscreen && photoViewer?.isOpen()) photoViewer.close();
      else if (escapedNativeFullscreen && overview.hidden && !modalOpen()) toggleOverview(true);
    }

    async function toggleFullscreen() {
      if (touchReview.matches) {
        controlsExpanded = false;
        scaleCurrent();
      }
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
      document.body.classList.toggle("overview-open", open);
      if (touchReview.matches) {
        controlsExpanded = false;
        scaleCurrent();
      }
      if (touchOverviewButton) {
        touchOverviewButton.textContent = open ? "Close overview" : "Overview";
        touchOverviewButton.setAttribute("aria-expanded", String(open));
      }
      deck.hidden = open;
      // Closing the overview returns to the slide at the step it was left on.
      if (!open) { render(shownStep()); return; }
      updateNavigation();
      // Thumbnails are never stepped: the overview shows every slide whole.
      overview.innerHTML = spec.slides.map((slide, i) => `<button class="overview-card" type="button" data-index="${i}" aria-current="${i === index}"><div class="overview-thumb">${slideMarkup(slide, i, true)}</div><span class="overview-label">${numbering.label(i)}. ${slideTitleText(slide, i)}</span></button>`).join("");
      fitFormulas(overview);
      // Thumbnails show the same photo correction as the slides.
      photoViewer?.mark(overview);
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

    // ---------------------------------------------------------------
    // Photo viewer. A projector eats contrast. A click on a content image
    // of the live slide (a figure, a figure grid, a photo in slide HTML),
    // or the expand control on a video, opens a copy of it in an overlay
    // that fills the window, with big brightness, contrast and zoom
    // controls. The overlay is a modal dialog: like the other dialogs it
    // owns keys, the wheel and swipes, and the deck behind it never moves.
    // A navigation or clicker key only closes it, on the slide and step it
    // opened from. Brightness, contrast and "Use on all photos" are kept
    // per deck in this browser; that toggle corrects every photo and video
    // of the slides, never a drawn SVG figure, a formula or the chrome.
    const PHOTO_MIN = 50;
    const PHOTO_MAX = 300;
    const PHOTO_STEP = 10;
    const PHOTO_ZOOM_MAX = 8;
    const PHOTO_ZOOM_STEP = Math.SQRT2;
    const EXPAND_SIZE = 44;
    const EXPAND_INSET = 12;
    // Pictures that are no photos to open: formulas (MathML, or an image
    // formula such as img.math-display), links and other controls, embedded
    // pages, thumbnail placeholders and anything marked data-photo="off".
    const PHOTO_SKIP = '.formula, .formula-gloss, .math-inline, .math-display, [class^="math-"], [class*=" math-"], math, a[href], button, summary, label, [role="button"], .interactive-frame, .video-placeholder, .interactive-placeholder, [data-photo="off"]';
    const PHOTO_CLOSE_KEYS = new Set(["Escape", "PageDown", "PageUp", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " ", "Home", "End"]);
    const NBSP = "\u00a0";
    const photoStoreKey = `lecturedeck-photo:${pacingPath()}:${String(spec.meta.title || spec.meta.tabTitle || "")}`;
    const photoLevel = value => typeof value === "number" && Number.isFinite(value)
      ? Math.min(PHOTO_MAX, Math.max(PHOTO_MIN, Math.round(value))) : 100;
    const photoSettings = {brightness: 100, contrast: 100, all: false};
    try {
      const saved = JSON.parse(localStorage.getItem(photoStoreKey) || "null");
      if (saved && typeof saved === "object") {
        photoSettings.brightness = photoLevel(saved.brightness);
        photoSettings.contrast = photoLevel(saved.contrast);
        photoSettings.all = saved.all === true;
      }
    } catch (_) {
      // Without storage every photo opens plain and nothing is remembered.
    }
    const photoFilter = () => photoSettings.brightness === 100 && photoSettings.contrast === 100 ? "none"
      : `brightness(${photoSettings.brightness}%) contrast(${photoSettings.contrast}%)`;
    const isSvgImage = image => {
      const src = image.currentSrc || image.getAttribute("src") || "";
      if (/^data:image\/svg\+xml/i.test(src)) return true;
      try { return /\.svgz?$/i.test(new URL(src, location.href).pathname); } catch (_) { return false; }
    };

    const viewer = document.createElement("dialog");
    viewer.id = "photo-viewer";
    viewer.className = "photo-viewer";
    viewer.setAttribute("aria-label", "Photo viewer");
    const photoButton = (act, label, text, key) => `<button type="button" data-photo-act="${act}" aria-label="${label}" title="${label} (${key})">${text}</button>`;
    const photoGroup = (name, label, down, up) => `<span class="photo-group">${photoButton(...down)}<span class="photo-value" data-photo-value="${name}" aria-live="polite">${label} <span class="photo-number"></span></span>${photoButton(...up)}</span>`;
    viewer.innerHTML = '<div class="photo-stage" tabindex="-1"></div>'
      + '<div class="photo-bar" role="group" aria-label="Photo controls">'
      + photoGroup("brightness", "Brightness", ["brightness-down", "Less brightness", "−", "Shift+B"], ["brightness-up", "More brightness", "+", "B"])
      + photoGroup("contrast", "Contrast", ["contrast-down", "Less contrast", "−", "Shift+C"], ["contrast-up", "More contrast", "+", "C"])
      + photoGroup("zoom", "Zoom", ["zoom-out", "Zoom out", "−", "−"], ["zoom-in", "Zoom in", "+", "+"])
      + '<button type="button" class="photo-toggle" data-photo-act="all" aria-pressed="false" title="Use this brightness and contrast on every photo and video of the deck (A)">Use on all photos</button>'
      + photoButton("reset", "Reset brightness, contrast and zoom", "Reset", "0")
      + photoButton("close", "Close the photo", "Close", "Esc")
      + "</div>";
    document.body.append(viewer);
    const stage = viewer.querySelector(".photo-stage");
    const photoBar = viewer.querySelector(".photo-bar");
    const photoNumber = name => viewer.querySelector(`[data-photo-value="${name}"] .photo-number`);

    let photoSource = null; // the slide's own picture
    let photoMedia = null; // its copy in the viewer
    const photoView = {zoom: 1, cx: 0.5, cy: 0.5};
    const photoPointers = new Map();
    let photoDrag = null;
    let photoPinch = null;
    let photoSuppressClick = false;
    let expanders = new Map(); // a live slide's video -> its expand control
    let expanderObserver = null;

    // The Appearance dialog carries the same toggle, built here so a legacy
    // unit-local index.html gets it too.
    const photoField = document.createElement("fieldset");
    photoField.className = "photo-fieldset";
    photoField.innerHTML = '<legend>Photos</legend><label><input type="checkbox" id="photo-all-input"> Use on all photos</label><p class="appearance-note" id="photo-all-note"></p>';
    const appearanceForm = appearanceDialog?.querySelector("form");
    appearanceForm?.insertBefore(photoField, appearanceForm.querySelector(":scope > .appearance-note"));
    const photoAllInput = photoField.querySelector("input");
    const photoAllNote = photoField.querySelector("#photo-all-note");

    function updatePhotoControls() {
      const {brightness, contrast, all} = photoSettings;
      photoNumber("brightness").textContent = `${brightness}${NBSP}%`;
      photoNumber("contrast").textContent = `${contrast}${NBSP}%`;
      photoNumber("zoom").textContent = `${photoView.zoom.toFixed(1)}×`;
      const limits = {
        "brightness-down": brightness <= PHOTO_MIN, "brightness-up": brightness >= PHOTO_MAX,
        "contrast-down": contrast <= PHOTO_MIN, "contrast-up": contrast >= PHOTO_MAX,
        "zoom-out": photoView.zoom <= 1, "zoom-in": photoView.zoom >= PHOTO_ZOOM_MAX - 1e-6,
      };
      // aria-disabled, not disabled: a button that has the focus keeps it.
      for (const [act, limit] of Object.entries(limits)) {
        viewer.querySelector(`[data-photo-act="${act}"]`).setAttribute("aria-disabled", String(limit));
      }
      viewer.querySelector('[data-photo-act="all"]').setAttribute("aria-pressed", String(all));
      photoAllInput.checked = all;
      photoAllNote.textContent = `Brightness ${brightness}${NBSP}%, contrast ${contrast}${NBSP}% on every photo and video of this deck. Click a photo on a slide to change them.`;
    }

    // The filter the slide itself gives the picture (a deck.css invert for
    // the dark theme, say), without the room correction: the copy shows
    // the picture as the slide does, then corrects it.
    let photoBaseFilter = "none";

    function slideFilter(source) {
      const corrected = source.classList.contains("photo-content");
      if (corrected) source.classList.remove("photo-content");
      const filter = getComputedStyle(source).filter;
      if (corrected) source.classList.add("photo-content");
      return filter && filter !== "none" ? filter : "none";
    }

    function applyPhotoSettings(persist = true) {
      const filter = photoFilter();
      document.body.style.setProperty("--photo-filter", filter);
      document.body.classList.toggle("photos-corrected", photoSettings.all);
      if (photoMedia) {
        const parts = [photoBaseFilter, filter].filter(part => part !== "none");
        photoMedia.style.filter = parts.join(" ");
      }
      updatePhotoControls();
      if (!persist) return;
      try {
        localStorage.setItem(photoStoreKey, JSON.stringify(photoSettings));
      } catch (_) {
        // Kept for this page only when local storage is unavailable.
      }
    }

    function stepPhoto(name, direction) {
      photoSettings[name] = photoLevel(photoSettings[name] + direction * PHOTO_STEP);
      applyPhotoSettings();
    }

    // The size the picture really has, for fitting it: the copy's own once
    // it has loaded, the slide's until then, its box on the slide at worst.
    function photoNatural() {
      const video = photoMedia instanceof HTMLVideoElement;
      const sizes = video
        ? [[photoMedia.videoWidth, photoMedia.videoHeight], [photoSource.videoWidth, photoSource.videoHeight]]
        : [[photoMedia.naturalWidth, photoMedia.naturalHeight], [photoSource.naturalWidth, photoSource.naturalHeight]];
      sizes.push([photoSource.offsetWidth, photoSource.offsetHeight]);
      const found = sizes.find(([width, height]) => width > 0 && height > 0);
      return found ? {width: found[0], height: found[1]} : {width: 16, height: 9};
    }

    // The picture in the stage: fitted, zoomed, with its point (cx, cy),
    // in fractions of its size, at the stage centre. Every size here is in
    // pixels from the stage's own box: no percentage height anywhere.
    function photoBox() {
      const width = stage.clientWidth, height = stage.clientHeight;
      const natural = photoNatural();
      const fit = Math.min(width / natural.width, height / natural.height);
      const shownWidth = natural.width * fit * photoView.zoom;
      const shownHeight = natural.height * fit * photoView.zoom;
      return {width, height, shownWidth, shownHeight,
        left: width / 2 - photoView.cx * shownWidth, top: height / 2 - photoView.cy * shownHeight};
    }

    function drawPhoto() {
      if (!photoMedia || !stage.clientWidth || !stage.clientHeight) return;
      // A picture no wider (or taller) than the stage stays centred; a
      // larger one never leaves a gap at an edge.
      const fitted = photoBox();
      const axis = (shown, room, value) => shown <= room + 0.5 ? 0.5
        : Math.min(1 - room / 2 / shown, Math.max(room / 2 / shown, value));
      photoView.cx = axis(fitted.shownWidth, fitted.width, photoView.cx);
      photoView.cy = axis(fitted.shownHeight, fitted.height, photoView.cy);
      const box = photoBox();
      photoMedia.style.width = `${box.shownWidth}px`;
      photoMedia.style.height = `${box.shownHeight}px`;
      photoMedia.style.transform = `translate(${box.left}px, ${box.top}px)`;
      viewer.dataset.zoomed = String(photoView.zoom > 1);
      // The hotspot rings lie over the copy, outside its filter, and follow
      // every zoom and pan.
      hotspots?.drawn(box);
      updatePhotoControls();
    }

    // Zoom so that the picture's point under (x, y) of the stage stays put.
    function zoomPhoto(target, x = stage.clientWidth / 2, y = stage.clientHeight / 2) {
      if (!photoMedia) return;
      const zoom = Math.min(PHOTO_ZOOM_MAX, Math.max(1, target));
      const before = photoBox();
      const fx = (x - before.left) / before.shownWidth;
      const fy = (y - before.top) / before.shownHeight;
      photoView.zoom = Math.abs(zoom - 1) < 1e-3 ? 1 : zoom;
      const after = photoBox();
      photoView.cx = (before.width / 2 - x) / after.shownWidth + fx;
      photoView.cy = (before.height / 2 - y) / after.shownHeight + fy;
      drawPhoto();
    }

    const stagePoint = event => {
      const rect = stage.getBoundingClientRect();
      return {x: event.clientX - rect.left, y: event.clientY - rect.top};
    };

    // A copy, never the slide's own element, so the slide behind keeps
    // every box where it was. A video continues where the slide's was.
    function photoCopy(source) {
      if (source instanceof HTMLVideoElement) {
        const video = source.cloneNode(true);
        for (const name of ["id", "class", "style", "data-step", "aria-hidden", "inert", "autoplay"]) {
          video.removeAttribute(name);
        }
        video.className = "photo-media";
        video.controls = true;
        video.playsInline = true;
        video.preload = "auto";
        video.muted = source.muted;
        video.volume = source.volume;
        video.defaultPlaybackRate = source.playbackRate;
        const at = source.currentTime;
        const playing = !source.paused && !source.ended;
        source.pause();
        video.addEventListener("loadedmetadata", () => {
          // Closed before it loaded: a copy nobody sees must never play.
          if (video !== photoMedia) return;
          try {
            if (at) video.currentTime = at;
          } catch (_) {
            // Not seekable: it starts from the beginning.
          }
          drawPhoto();
          if (playing) video.play().catch(() => {});
        }, {once: true});
        return video;
      }
      const image = document.createElement("img");
      image.className = "photo-media";
      image.alt = source.alt || "";
      image.decoding = "async";
      image.draggable = false;
      if (source.srcset) {
        image.srcset = source.srcset;
        image.sizes = "100vw";
      }
      image.src = source.currentSrc || source.src;
      image.addEventListener("load", drawPhoto, {once: true});
      return image;
    }

    function openPhoto(source) {
      if (viewer.open || modalOpen() || !source.isConnected) return;
      photoSource = source;
      photoMedia = photoCopy(source);
      photoBaseFilter = slideFilter(source);
      if (photoMedia instanceof HTMLImageElement) {
        // A drawing with a transparent background keeps the slide's own
        // background, so dark ink stays readable on the black stage.
        const frame = source.closest(".slide-frame");
        const background = frame ? getComputedStyle(frame).getPropertyValue("--bg").trim() : "";
        photoMedia.style.backgroundColor = background || "";
      }
      viewer.dataset.kind = source instanceof HTMLVideoElement ? "video" : "image";
      Object.assign(photoView, {zoom: 1, cx: 0.5, cy: 0.5});
      stage.replaceChildren(photoMedia);
      hotspots?.opened(source);
      viewer.showModal();
      // The stage, not a button, takes the focus: a clicker's Space must
      // close the photo, never press "Less brightness".
      stage.focus({preventScroll: true});
      // The laser keeps pointing over the photo: its dot moves into the
      // viewer, which the top layer draws above everything else.
      viewer.append(laser);
      applyPhotoSettings(false);
      drawPhoto();
    }

    function finishPhoto() {
      if (!photoMedia) return;
      if (photoMedia instanceof HTMLVideoElement && photoSource instanceof HTMLVideoElement) {
        const at = photoMedia.currentTime;
        const known = photoMedia.readyState >= 1;
        photoMedia.pause();
        // The slide's video waits, paused, at the moment the viewer reached.
        try {
          if (known && Number.isFinite(at) && photoSource.isConnected) photoSource.currentTime = at;
        } catch (_) {
          // Not seekable: it keeps its own moment.
        }
      }
      if (photoMedia instanceof HTMLVideoElement) {
        // Stop the copy loading, too.
        photoMedia.removeAttribute("src");
        photoMedia.querySelectorAll("source").forEach(node => node.remove());
        try { photoMedia.load(); } catch (_) { /* already released */ }
      }
      photoMedia.remove();
      photoMedia = null;
      photoSource = null;
      photoBaseFilter = "none";
      hotspots?.closed();
      // The tail of a trackpad scroll that zoomed the photo must not page
      // the deck once the photo is gone.
      wheelStreak = 0;
      wheelPrevAt = performance.now();
      wheelHoldUntil = performance.now() + 150;
      photoDrag = null;
      photoPinch = null;
      photoPointers.clear();
      viewer.classList.remove("photo-dragging");
      if (laser.parentElement === viewer) document.body.append(laser);
      // The dialog hands the focus back, or leaves it a moment on its own
      // button. Neither keeps it: the clicker's Space then pages the deck
      // instead of pressing a control again.
      const focused = document.activeElement;
      if (focused instanceof HTMLElement && (deck.contains(focused) || viewer.contains(focused))) focused.blur();
    }

    function closePhoto() {
      if (viewer.open) viewer.close();
      finishPhoto();
    }

    function resetPhoto() {
      photoSettings.brightness = 100;
      photoSettings.contrast = 100;
      Object.assign(photoView, {zoom: 1, cx: 0.5, cy: 0.5});
      applyPhotoSettings();
      drawPhoto();
    }

    function photoAction(act) {
      ({
        "brightness-down": () => stepPhoto("brightness", -1),
        "brightness-up": () => stepPhoto("brightness", 1),
        "contrast-down": () => stepPhoto("contrast", -1),
        "contrast-up": () => stepPhoto("contrast", 1),
        "zoom-out": () => zoomPhoto(photoView.zoom / PHOTO_ZOOM_STEP),
        "zoom-in": () => zoomPhoto(photoView.zoom * PHOTO_ZOOM_STEP),
        all: () => {
          photoSettings.all = !photoSettings.all;
          applyPhotoSettings();
        },
        reset: resetPhoto,
        close: closePhoto,
      })[act]?.();
    }

    // Keys while the photo is open. Navigation and clicker keys only close
    // it; every other deck shortcut waits behind it, except the laser.
    function photoKeydown(event) {
      const plain = !event.ctrlKey && !event.metaKey && !event.altKey;
      if (event.key === "Escape" || (plain && PHOTO_CLOSE_KEYS.has(event.key))) {
        event.preventDefault();
        closePhoto();
        return;
      }
      if (!plain || event.key === "Tab" || event.key === "Enter") return;
      const key = event.key.toLowerCase();
      const act = key === "b" ? (event.shiftKey ? "brightness-down" : "brightness-up")
        : key === "c" ? (event.shiftKey ? "contrast-down" : "contrast-up")
          : ["+", "=", "add"].includes(key) ? "zoom-in"
            : ["-", "_", "subtract"].includes(key) ? "zoom-out"
              : key === "0" ? "reset"
                : key === "a" ? "all" : null;
      if (act) {
        event.preventDefault();
        photoAction(act);
      } else if (key === "l") {
        event.preventDefault();
        setLaser(!laserOn);
      } else if (key === "h") {
        event.preventDefault();
        hotspots?.toggle();
      }
    }

    photoAllInput.addEventListener("change", () => {
      photoSettings.all = photoAllInput.checked;
      applyPhotoSettings();
    });
    photoBar.addEventListener("click", event => {
      const button = event.target instanceof Element ? event.target.closest("[data-photo-act]") : null;
      if (button) photoAction(button.dataset.photoAct);
    });
    // The stage around the picture is the backdrop; a drag that ends there
    // is no click on it.
    viewer.addEventListener("click", event => {
      if (photoSuppressClick) {
        photoSuppressClick = false;
        return;
      }
      if (event.target === stage || event.target === viewer) closePhoto();
    });
    viewer.addEventListener("cancel", event => {
      event.preventDefault();
      closePhoto();
    });
    viewer.addEventListener("close", () => { if (!viewer.open) finishPhoto(); });
    viewer.addEventListener("wheel", event => {
      // The page never scrolls or zooms behind the photo.
      event.preventDefault();
      if (!photoMedia) return;
      const unit = event.deltaMode === 1 ? 20 : event.deltaMode === 2 ? 400 : 1;
      const delta = event.deltaY * unit;
      if (!delta) return;
      const point = photoBar.contains(event.target)
        ? {x: stage.clientWidth / 2, y: stage.clientHeight / 2} : stagePoint(event);
      // A trackpad pinch arrives as a wheel with ctrlKey, in small steps.
      zoomPhoto(photoView.zoom * Math.exp(-delta * (event.ctrlKey ? 0.01 : 0.002)), point.x, point.y);
    }, {passive: false});
    stage.addEventListener("dblclick", event => {
      // A video keeps its own double-click (the player's full screen). A
      // hotspot ring is part of the picture.
      const onPicture = event.target === photoMedia
        || (event.target instanceof Element && Boolean(event.target.closest(".photo-stage > .hotspot-layer")));
      if (!onPicture || !(photoMedia instanceof HTMLImageElement)) return;
      event.preventDefault();
      const point = stagePoint(event);
      zoomPhoto(photoView.zoom > 1 ? 1 : 2, point.x, point.y);
    });
    stage.addEventListener("dragstart", event => event.preventDefault());
    stage.addEventListener("pointerdown", event => {
      photoSuppressClick = false;
      if (!photoMedia || (event.pointerType === "mouse" && event.button !== 0)) return;
      // A new gesture starts clean, whatever an earlier one left behind.
      if (event.isPrimary) photoPointers.clear();
      photoPointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      if (photoPointers.size === 2) {
        const [a, b] = [...photoPointers.values()];
        photoPinch = {distance: Math.hypot(a.x - b.x, a.y - b.y) || 1, zoom: photoView.zoom};
        photoDrag = null;
        return;
      }
      // At fit there is nothing to pan, and a video's controls keep their clicks.
      if (photoView.zoom <= 1) return;
      photoDrag = {id: event.pointerId, x: event.clientX, y: event.clientY,
        cx: photoView.cx, cy: photoView.cy, moved: false};
    });
    stage.addEventListener("pointermove", event => {
      if (!photoPointers.has(event.pointerId)) return;
      photoPointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      if (photoPinch && photoPointers.size === 2) {
        const [a, b] = [...photoPointers.values()];
        const rect = stage.getBoundingClientRect();
        zoomPhoto(photoPinch.zoom * Math.hypot(a.x - b.x, a.y - b.y) / photoPinch.distance,
          (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
        photoSuppressClick = true;
        return;
      }
      const drag = photoDrag;
      if (!drag || drag.id !== event.pointerId) return;
      const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
      if (!drag.moved) {
        if (Math.hypot(dx, dy) < 4) return;
        drag.moved = true;
        try { stage.setPointerCapture(event.pointerId); } catch (_) { /* the pointer is gone */ }
        viewer.classList.add("photo-dragging");
        // A popup the pointer only passed over goes; a tapped one stays.
        hotspots?.dragged();
      }
      const box = photoBox();
      photoView.cx = drag.cx - dx / box.shownWidth;
      photoView.cy = drag.cy - dy / box.shownHeight;
      drawPhoto();
    });
    const endPhotoPointer = event => {
      photoPointers.delete(event.pointerId);
      if (photoPointers.size < 2) photoPinch = null;
      if (photoDrag?.id !== event.pointerId) return;
      if (photoDrag.moved) photoSuppressClick = true;
      photoDrag = null;
      viewer.classList.remove("photo-dragging");
    };
    // On the dialog, so a finger lifted over the bar ends its pointer too.
    viewer.addEventListener("pointerup", endPhotoPointer);
    viewer.addEventListener("pointercancel", endPhotoPointer);
    if (typeof ResizeObserver === "function") new ResizeObserver(drawPhoto).observe(stage);
    addEventListener("resize", drawPhoto);

    // Mark a slide's pictures: every image that opens in the viewer, and the
    // photos and videos the room correction reaches (no SVG drawing).
    function markPhotos(scope, live) {
      const found = [];
      for (const node of scope.querySelectorAll(".slide-body img, .slide-body video")) {
        // Only the slide's own content counts: an overview card is a button.
        const skip = node.closest(PHOTO_SKIP);
        if (skip && node.closest(".slide-body").contains(skip)) continue;
        const image = node instanceof HTMLImageElement;
        if (image && live) node.classList.add("photo-zoomable");
        if (!image || !isSvgImage(node)) node.classList.add("photo-content");
        found.push(node);
      }
      return found;
    }

    // Each expand control sits on its video's top right corner, out of the
    // slide's layout (a child of the frame, positioned in its unscaled
    // pixels), and shows only while its video does.
    function placeExpanders() {
      const frame = deck.querySelector(".slide-frame");
      if (!frame || !expanders.size) return;
      const box = frame.getBoundingClientRect();
      const scale = frame.offsetWidth ? box.width / frame.offsetWidth : 1;
      for (const [video, button] of expanders) {
        const rect = video.getBoundingClientRect();
        const shown = video.isConnected && !video.closest(".step-hidden") && rect.width > 0 && rect.height > 0;
        button.hidden = !shown;
        if (!shown) continue;
        button.style.left = `${(rect.right - box.left) / scale - EXPAND_SIZE - EXPAND_INSET}px`;
        button.style.top = `${(rect.top - box.top) / scale + EXPAND_INSET}px`;
      }
    }

    function decoratePhotos(frame) {
      expanderObserver?.disconnect();
      expanders = new Map();
      if (!frame) return;
      for (const node of markPhotos(frame, true)) {
        if (!(node instanceof HTMLVideoElement)) continue;
        // A click on the video plays it; the expand control opens it.
        const button = document.createElement("button");
        button.type = "button";
        button.className = "photo-expand";
        button.title = "Enlarge: brightness, contrast and zoom";
        button.setAttribute("aria-label", "Enlarge the video");
        button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        button.hidden = true;
        button.addEventListener("click", event => {
          event.preventDefault();
          event.stopPropagation();
          openPhoto(node);
        });
        node.addEventListener("loadedmetadata", placeExpanders);
        frame.append(button);
        expanders.set(node, button);
      }
      if (expanders.size && typeof ResizeObserver === "function") {
        expanderObserver = new ResizeObserver(placeExpanders);
        expanders.forEach((_, video) => expanderObserver.observe(video));
      }
      // A late image or font can move a video without resizing it.
      if (expanders.size) {
        frame.querySelectorAll("img").forEach(image => {
          if (!image.complete) image.addEventListener("load", placeExpanders, {once: true});
        });
        document.fonts?.ready.then(placeExpanders, () => {});
      }
      placeExpanders();
    }

    // A click on a marked image opens it. Nothing else on the deck acts on
    // a click, so it never pages or steps the slide.
    deck.addEventListener("click", event => {
      const image = event.target instanceof Element ? event.target.closest("img.photo-zoomable") : null;
      if (!image || image.closest(".step-hidden") || !image.closest(".slide-frame")) return;
      event.preventDefault();
      event.stopPropagation();
      openPhoto(image);
    });

    // ---------------------------------------------------------------
    // Photo hotspots. A figure may carry `hotspots`: points of its picture,
    // x and y as fractions of its natural width and height and a radius r
    // as a fraction of its natural width, each with a label and a popup.
    // On the live slide a layer of rings lies exactly on the drawn picture
    // (its content box, object-fit and object-position, and the figure's
    // shift and scale). The layer is a child of the frame, out of every
    // layout box, and the figure card is never restyled: WebKit lays a
    // positioned fit-content card out at another width. The layer follows
    // the figure's step and fade from script. The rings stay invisible
    // until the pointer is over the picture; then faint rings mark every
    // hotspot, the presenter's hint of where to point. A ring under the
    // pointer, focused from the keyboard or tapped shows its popup beside
    // it, inside the slide. The photo viewer lays the same rings over its
    // copy, following zoom and pan, outside the copy's brightness and
    // contrast filter. `H` turns the hint rings off and on for the whole
    // deck; a hotspot under the pointer still shows its own ring and popup.
    const HOTSPOT_HIDE_MS = 200;
    const HOTSPOT_GAP = 12;
    const HOTSPOT_MARGIN = 8;
    const HOTSPOT_FLASH_MS = 1500;
    const hotspotOf = new WeakMap(); // ring -> its hotspot
    const hotspotsOfCard = new WeakMap(); // figure card -> its hotspots
    const hotspotRingsKey = `lecturedeck-hotspot-rings:${pacingPath()}:${String(spec.meta.title || spec.meta.tabTitle || "")}`;
    const inRange = (value, low, high) => typeof value === "number" && Number.isFinite(value)
      && value >= low && value <= high;
    // check rejects a malformed hotspot; the viewer simply leaves it out.
    const figureHotspots = figure => !Array.isArray(figure?.hotspots) ? []
      : figure.hotspots.filter(spot => spot && typeof spot === "object"
        && inRange(spot.x, 0, 1) && inRange(spot.y, 0, 1) && inRange(spot.r, 1e-9, 0.5)
        && typeof spot.label === "string" && spot.label.trim());
    const slideFigures = slide => Array.isArray(slide?.figures) ? slide.figures : slide?.figure ? [slide.figure] : [];
    const deckHasHotspots = spec.slides.some(slide => slideFigures(slide).some(figure => figureHotspots(figure).length));
    let hotspotRings = true;
    try {
      hotspotRings = sessionStorage.getItem(hotspotRingsKey) !== "off";
    } catch (_) {
      // Without session storage the rings start on with every page.
    }
    let hotspotFlash = 0;
    let hotspotObservers = [];
    let slideLayers = []; // {card, image, layer} of the live slide
    let viewerLayer = null;
    const pictureOfLayer = new WeakMap(); // layer -> the image it lies on

    // The layout size of a box, in its own unscaled pixels.
    const layoutSize = node => {
      const style = getComputedStyle(node);
      return {width: parseFloat(style.width) || 0, height: parseFloat(style.height) || 0};
    };

    const OBJECT_KEYWORDS = new Map([["left", 0], ["top", 0], ["center", 50], ["right", 100], ["bottom", 100]]);
    // The offset object-position gives a picture inside its content box,
    // from the free room on each axis (negative when the picture overflows).
    function objectOffset(position, freeX, freeY) {
      const words = String(position || "").trim().split(/\s+/);
      if (words.length !== 2) return [freeX / 2, freeY / 2];
      let [across, down] = words;
      if (["top", "bottom"].includes(across) || ["left", "right"].includes(down)) [across, down] = [down, across];
      const offset = (word, free) => OBJECT_KEYWORDS.has(word) ? free * OBJECT_KEYWORDS.get(word) / 100
        : word.endsWith("%") ? free * parseFloat(word) / 100
          : word.endsWith("px") ? parseFloat(word) : free / 2;
      return [offset(across, freeX), offset(down, freeY)];
    }

    // Where an image draws its picture, in the unscaled pixels of
    // `container`, an ancestor it is laid out in: its content box, then
    // object-fit and object-position, as the browser paints it, through
    // every transform between them (the frame's scale, a figure's shift
    // and scale). `clip` is the part of that rectangle outside the content
    // box (object-fit cover or none), as an inset() of it. Null while the
    // picture is not laid out or has no size.
    function drawnPicture(image, container) {
      if (!image?.isConnected) return null;
      const outer = image.getBoundingClientRect();
      const around = container.getBoundingClientRect();
      const room = layoutSize(container);
      if (!outer.width || !outer.height || !around.width || !room.width) return null;
      const naturalWidth = image.naturalWidth, naturalHeight = image.naturalHeight;
      if (!naturalWidth || !naturalHeight) return null;
      const style = getComputedStyle(image);
      const px = name => parseFloat(style[name]) || 0;
      const left = px("borderLeftWidth") + px("paddingLeft"), right = px("borderRightWidth") + px("paddingRight");
      const top = px("borderTopWidth") + px("paddingTop"), bottom = px("borderBottomWidth") + px("paddingBottom");
      const sized = style.boxSizing === "border-box";
      const width = (parseFloat(style.width) || 0) + (sized ? 0 : left + right);
      const height = (parseFloat(style.height) || 0) + (sized ? 0 : top + bottom);
      const contentWidth = width - left - right, contentHeight = height - top - bottom;
      if (contentWidth <= 0 || contentHeight <= 0) return null;
      const contain = Math.min(contentWidth / naturalWidth, contentHeight / naturalHeight);
      const cover = Math.max(contentWidth / naturalWidth, contentHeight / naturalHeight);
      const [fitX, fitY] = {
        contain: [contain, contain], cover: [cover, cover], none: [1, 1],
        "scale-down": [Math.min(1, contain), Math.min(1, contain)],
      }[style.objectFit] || [contentWidth / naturalWidth, contentHeight / naturalHeight];
      const drawnWidth = naturalWidth * fitX, drawnHeight = naturalHeight * fitY;
      const [x, y] = objectOffset(style.objectPosition, contentWidth - drawnWidth, contentHeight - drawnHeight);
      // The transforms only scale and move: one factor turns the image's
      // own pixels into screen pixels, another the container's.
      const imageScale = outer.width / width;
      const scale = imageScale / (around.width / room.width);
      const insets = [Math.max(0, -y), Math.max(0, drawnWidth + x - contentWidth),
        Math.max(0, drawnHeight + y - contentHeight), Math.max(0, -x)].map(inset => inset * scale);
      const origin = {
        left: (outer.left - around.left) * (room.width / around.width) - container.clientLeft,
        top: (outer.top - around.top) * (room.width / around.width) - container.clientTop,
      };
      return {
        left: origin.left + (left + x) * scale, top: origin.top + (top + y) * scale,
        width: drawnWidth * scale, height: drawnHeight * scale,
        clip: insets.some(inset => inset > 0.5) ? `inset(${insets.map(inset => `${inset}px`).join(" ")})` : "",
      };
    }

    // A popup surface: one popup at a time, beside its ring, inside the
    // container it is shown in (the slide frame, or the viewer's stage).
    // A tapped popup is pinned: it stays until a tap elsewhere.
    function hotspotSurface(name) {
      const popup = document.createElement("div");
      popup.className = "hotspot-popup";
      popup.id = `hotspot-popup-${name}`;
      popup.setAttribute("role", "tooltip");
      popup.hidden = true;
      let ring = null;
      let pinned = false;
      let timer = 0;
      const surface = {
        popup,
        get ring() { return ring; },
        get pinned() { return pinned; },
        show(next, pin = false) {
          clearTimeout(timer);
          const container = next.closest(".slide-frame, .photo-stage");
          const spot = hotspotOf.get(next);
          if (!container || !spot) return;
          const keep = next === ring && pinned;
          if (next !== ring) {
            surface.hide();
            // Popup HTML is slide HTML, but a popup is never stepped.
            popup.innerHTML = typeof spot.html === "string" && spot.html.trim()
              ? withoutSteps(spot.html) : escapeHtml(spot.label.trim());
            ring = next;
            ring.classList.add("is-active");
            ring.setAttribute("aria-describedby", popup.id);
          }
          pinned = pin || keep;
          if (popup.parentElement !== container) container.append(popup);
          surface.place();
        },
        hide() {
          clearTimeout(timer);
          if (ring) {
            ring.classList.remove("is-active");
            ring.removeAttribute("aria-describedby");
          }
          ring = null;
          pinned = false;
          popup.hidden = true;
        },
        // The pointer left the ring: a moment to reach the popup's links.
        later() {
          clearTimeout(timer);
          timer = setTimeout(() => { if (!pinned) surface.hide(); }, HOTSPOT_HIDE_MS);
        },
        keep() { clearTimeout(timer); },
        // Beside the ring, on the side with more room, else below or above
        // it, slid along that side to stay inside the container.
        place() {
          const container = popup.parentElement;
          if (!ring || !container) return;
          if (!ring.isConnected || !container.contains(ring)) { surface.hide(); return; }
          const box = container.getBoundingClientRect();
          const size = layoutSize(container);
          const scale = size.width ? box.width / size.width : 0;
          const r = ring.getBoundingClientRect();
          if (!scale || !r.width) return;
          const near = {
            left: (r.left - box.left) / scale, right: (r.right - box.left) / scale,
            top: (r.top - box.top) / scale, bottom: (r.bottom - box.top) / scale,
          };
          const cx = (near.left + near.right) / 2, cy = (near.top + near.bottom) / 2;
          // A ring zoomed or panned out of view takes its popup with it.
          popup.hidden = cx < 0 || cy < 0 || cx > size.width || cy > size.height;
          if (popup.hidden) return;
          const width = popup.offsetWidth, height = popup.offsetHeight;
          const m = HOTSPOT_MARGIN, gap = HOTSPOT_GAP;
          const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
          const alongX = x => clamp(x, m, size.width - m - width);
          const alongY = y => clamp(y, m, size.height - m - height);
          const right = {side: "right", x: near.right + gap, y: alongY(cy - height / 2)};
          const left = {side: "left", x: near.left - gap - width, y: alongY(cy - height / 2)};
          const below = {side: "below", x: alongX(cx - width / 2), y: near.bottom + gap};
          const above = {side: "above", x: alongX(cx - width / 2), y: near.top - gap - height};
          const fits = p => p.x >= m - 0.5 && p.y >= m - 0.5
            && p.x + width <= size.width - m + 0.5 && p.y + height <= size.height - m + 0.5;
          const order = cx > size.width / 2 ? [left, right, below, above] : [right, left, below, above];
          const chosen = order.find(fits) || {side: order[0].side, x: alongX(order[0].x), y: alongY(order[0].y)};
          popup.style.left = `${chosen.x}px`;
          popup.style.top = `${chosen.y}px`;
          popup.dataset.side = chosen.side;
        },
      };
      popup.addEventListener("pointerenter", () => surface.keep());
      popup.addEventListener("pointerleave", event => {
        if (event.pointerType === "mouse" && !pinned) surface.later();
      });
      return surface;
    }
    const slideSurface = hotspotSurface("slide");
    const viewerSurface = hotspotSurface("viewer");

    // A ring: a focusable button-like mark, named by its label. A mouse
    // shows its popup on hover, a keyboard on focus, a finger on a tap.
    // On the slide a mouse click on a ring opens the photo like a click on
    // the picture; in the viewer it does nothing more.
    function hotspotRing(spot, surface) {
      const ring = document.createElement("span");
      ring.className = "hotspot";
      ring.tabIndex = 0;
      ring.setAttribute("role", "button");
      ring.setAttribute("aria-label", spot.label.trim());
      ring.style.setProperty("--hotspot-x", String(spot.x));
      ring.style.setProperty("--hotspot-y", String(spot.y));
      ring.style.setProperty("--hotspot-r", String(spot.r));
      hotspotOf.set(ring, spot);
      let pointer = "mouse";
      const toggle = () => {
        if (surface.ring === ring && surface.pinned) surface.hide();
        else surface.show(ring, true);
      };
      ring.addEventListener("pointerdown", event => { pointer = event.pointerType || "mouse"; });
      ring.addEventListener("pointerenter", event => {
        if (event.pointerType === "mouse") surface.show(ring);
      });
      ring.addEventListener("pointerleave", event => {
        if (event.pointerType === "mouse" && surface.ring === ring && !surface.pinned) surface.later();
      });
      ring.addEventListener("focus", () => { if (ring.matches(":focus-visible")) surface.show(ring); });
      ring.addEventListener("blur", () => {
        if (surface.ring === ring && !surface.pinned && !ring.matches(":hover")) surface.hide();
      });
      ring.addEventListener("keydown", event => {
        if (event.key !== "Enter" || event.ctrlKey || event.metaKey || event.altKey) return;
        event.preventDefault();
        toggle();
      });
      ring.addEventListener("click", event => {
        if (surface === viewerSurface) {
          // The end of a drag or pinch is no tap (the viewer's own click
          // handler then forgets the drag).
          if (!photoSuppressClick && pointer !== "mouse") toggle();
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        if (pointer !== "mouse") { toggle(); return; }
        const image = pictureOfLayer.get(ring.parentElement);
        if (image?.matches("img.photo-zoomable") && !image.closest(".step-hidden")) openPhoto(image);
      });
      return ring;
    }

    // The faint rings show while the pointer is over the picture or its
    // rings (a finger has no hover; a screen without hover always shows them).
    function hotspotLayer(spots, surface, image) {
      const layer = document.createElement("div");
      layer.className = "hotspot-layer";
      layer.append(...spots.map(spot => hotspotRing(spot, surface)));
      pictureOfLayer.set(layer, image);
      const over = node => node instanceof Node && (node === image || layer.contains(node));
      const hint = event => { if (event.pointerType !== "touch") layer.classList.add("is-hinted"); };
      const unhint = event => { if (!over(event.relatedTarget)) layer.classList.remove("is-hinted"); };
      image.addEventListener("pointerenter", hint);
      image.addEventListener("pointerleave", unhint);
      layer.addEventListener("pointerover", hint);
      layer.addEventListener("pointerout", unhint);
      return layer;
    }

    // Lay each figure's rings on its drawn picture, in the frame's own
    // pixels, and let them step and fade with the figure.
    function placeHotspotLayers() {
      const frame = deck.querySelector(".slide-frame");
      if (!frame) return;
      for (const {card, image, layer} of slideLayers) {
        if (!layer.isConnected) continue;
        const out = Boolean(card.closest(".step-hidden"));
        layer.classList.toggle("hotspot-stepped-out", out);
        layer.inert = out;
        const box = drawnPicture(image, frame);
        layer.hidden = !box;
        if (!box) continue;
        layer.style.left = `${box.left}px`;
        layer.style.top = `${box.top}px`;
        layer.style.width = `${box.width}px`;
        layer.style.height = `${box.height}px`;
        layer.style.clipPath = box.clip;
      }
      slideSurface.place();
    }

    function decorateHotspots(frame) {
      slideSurface.hide();
      hotspotObservers.forEach(observer => observer.disconnect());
      hotspotObservers = [];
      slideLayers = [];
      if (!frame) return;
      const figures = slideFigures(spec.slides[Number(frame.dataset.index)]);
      for (const card of frame.querySelectorAll(".figure-card[data-figure-index]")) {
        const spots = figureHotspots(figures[Number(card.dataset.figureIndex)]);
        const image = card.querySelector(":scope > img");
        if (!spots.length || !image) continue;
        hotspotsOfCard.set(card, spots);
        // A hook only: the card's own style never changes.
        card.classList.add("has-hotspots");
        const layer = hotspotLayer(spots, slideSurface, image);
        layer.classList.toggle("opens-photo", image.classList.contains("photo-zoomable"));
        // deck.css can style one figure's rings by its id.
        if (card.dataset.figureId) layer.dataset.figureId = card.dataset.figureId;
        layer.hidden = true;
        frame.append(layer);
        slideLayers.push({card, image, layer});
        if (!image.complete) image.addEventListener("load", placeHotspotLayers, {once: true});
      }
      if (!slideLayers.length) return;
      // A late font, a theme or full screen can resize the picture; the
      // adjust HUD moves a figure by its style.
      if (typeof ResizeObserver === "function") {
        const resized = new ResizeObserver(placeHotspotLayers);
        slideLayers.forEach(({card, image}) => { resized.observe(card); resized.observe(image); });
        hotspotObservers.push(resized);
      }
      const restyled = new MutationObserver(placeHotspotLayers);
      slideLayers.forEach(({card}) => restyled.observe(card, {attributes: true, attributeFilter: ["style"]}));
      hotspotObservers.push(restyled);
      document.fonts?.ready.then(placeHotspotLayers, () => {});
      placeHotspotLayers();
    }

    // The viewer's copy of a figure with hotspots gets the same rings.
    function openViewerHotspots(source) {
      slideSurface.hide();
      viewerLayer = null;
      const card = source instanceof HTMLImageElement ? source.closest(".figure-card.has-hotspots") : null;
      const spots = card && card.querySelector(":scope > img") === source ? hotspotsOfCard.get(card) : null;
      if (!spots?.length || !photoMedia) return;
      // Popup text as large as on the slide, never smaller than 22 px.
      viewer.style.setProperty("--hotspot-scale",
        String(Math.max(1, Math.min(innerWidth / SLIDE_WIDTH, innerHeight / SLIDE_HEIGHT))));
      viewerLayer = hotspotLayer(spots, viewerSurface, photoMedia);
      stage.append(viewerLayer);
    }

    function setHotspotRings(on) {
      hotspotRings = on;
      document.body.classList.toggle("hotspot-rings-off", !on);
      // Turned on, every ring shows a moment, also without the pointer.
      clearTimeout(hotspotFlash);
      document.body.classList.toggle("hotspot-rings-flash", on);
      if (on) hotspotFlash = setTimeout(() => document.body.classList.remove("hotspot-rings-flash"), HOTSPOT_FLASH_MS);
      if (hotspotRingsInput) hotspotRingsInput.checked = on;
      try {
        sessionStorage.setItem(hotspotRingsKey, on ? "on" : "off");
      } catch (_) {
        // Kept for this page only.
      }
    }

    // The Appearance dialog carries the switch on a deck with hotspots.
    let hotspotRingsInput = null;
    if (deckHasHotspots) {
      const label = document.createElement("label");
      label.innerHTML = '<input type="checkbox" id="hotspot-rings-input"> Hint rings on photo hotspots (H)';
      photoField.insertBefore(label, photoAllNote);
      hotspotRingsInput = label.querySelector("input");
      hotspotRingsInput.addEventListener("change", () => setHotspotRings(hotspotRingsInput.checked));
    }
    document.body.classList.toggle("hotspot-rings-off", !hotspotRings);
    if (hotspotRingsInput) hotspotRingsInput.checked = hotspotRings;

    // A tap anywhere else lets a pinned popup go.
    document.addEventListener("pointerdown", event => {
      const target = event.target instanceof Element ? event.target : null;
      for (const surface of [slideSurface, viewerSurface]) {
        if (!surface.pinned) continue;
        if (target && (surface.popup.contains(target) || target.closest(".hotspot"))) continue;
        surface.hide();
      }
    }, true);

    hotspots = {
      decorate: decorateHotspots,
      place: placeHotspotLayers,
      stepped: () => {
        placeHotspotLayers();
        if (slideSurface.ring?.closest(".hotspot-stepped-out")) slideSurface.hide();
      },
      toggle: () => setHotspotRings(!hotspotRings),
      opened: openViewerHotspots,
      drawn: box => {
        if (!viewerLayer) return;
        viewerLayer.style.width = `${box.shownWidth}px`;
        viewerLayer.style.height = `${box.shownHeight}px`;
        viewerLayer.style.transform = `translate(${box.left}px, ${box.top}px)`;
        viewerSurface.place();
      },
      dragged: () => { if (!viewerSurface.pinned) viewerSurface.hide(); },
      closed: () => {
        viewerSurface.hide();
        viewerSurface.popup.remove();
        viewerLayer?.remove();
        viewerLayer = null;
      },
    };

    photoViewer = {
      isOpen: () => viewer.open,
      close: closePhoto,
      decorate: decoratePhotos,
      mark: scope => { markPhotos(scope, false); },
      placeExpanders,
    };
    applyPhotoSettings(false);

    addEventListener("resize", () => { scaleCurrent(); scaleOverviewThumbs(); refreshSteps(); });
    // The theme, the presentation style and other body classes may show or
    // hide stepped content through deck.css.
    new MutationObserver(() => { refreshSteps(); photoViewer?.placeExpanders(); hotspots?.place(); }).observe(document.body, {
      attributes: true, attributeFilter: ["class", "data-presentation-style"],
    });
    addEventListener("hashchange", () => {
      const requested = parseSlideHash(location.hash);
      if (requested && (requested.index !== index || requested.step !== shownStep())) {
        show(requested.index, requested.step);
      }
    });
    addEventListener("message", event => {
      // Nothing pages the deck under an open photo.
      if (viewer.open) return;
      const iframe = deck.querySelector(".interactive-frame iframe");
      if (!iframe || event.source !== iframe.contentWindow || event.data?.type !== "lecturedeck:navigate") return;
      // `to` is the page's Home or End: the deck's first or last state.
      if (event.data.to === "first") { show(0, 0); return; }
      if (event.data.to === "last") { show(spec.slides.length - 1, Infinity); return; }
      const direction = Number(event.data.direction);
      // The page asks for the deck's own Next or Previous, steps included.
      if (direction === 1 || direction === -1) turn(direction);
    });
    // While any dialog is open, keys, the wheel and swipes belong to it:
    // they scroll the dialog and never page, open or exit the deck.
    addEventListener("keydown", event => {
      // The photo viewer is a dialog too, with keys of its own.
      if (viewer.open) { photoKeydown(event); return; }
      if (modalOpen()) return;
      // Focus can linger on a control of a dialog that just closed (its
      // close event comes a task later); such a key belongs to the deck.
      const target = event.target instanceof Element && !event.target.closest("dialog:not([open])") ? event.target : null;
      if (target && target.closest("video, audio, input, textarea, select, [contenteditable]")) return;
      // Buttons and links keep Space/Enter activation but still allow deck paging.
      const onControl = Boolean(target && target.closest("button, a"));
      const forward = ["ArrowRight", "ArrowDown", "PageDown"].includes(event.key);
      const backward = ["ArrowLeft", "ArrowUp", "PageUp"].includes(event.key);
      // Shift pages whole slides past their steps, for rewinding.
      if (event.shiftKey && (forward || backward)) { event.preventDefault(); if (forward) nextSlide(); else previousSlide(); }
      else if (forward || (event.key === " " && !onControl)) { event.preventDefault(); next(); }
      else if (backward) { event.preventDefault(); previous(); }
      // Home is the deck's first state, End its last: the final slide whole.
      else if (event.key === "Home") show(0, 0);
      else if (event.key === "End") show(spec.slides.length - 1, Infinity);
      else if (event.key === "Escape" && overview.hidden && document.body.classList.contains("pseudo-fullscreen")) toggleFullscreen();
      else if (event.key.toLowerCase() === "o" || event.key === "Escape") toggleOverview();
      else if (event.key.toLowerCase() === "f") toggleFullscreen();
      else if (event.key.toLowerCase() === "l") setLaser(!laserOn);
      else if (event.key.toLowerCase() === "t") { event.preventDefault(); appearanceDialog?.showModal(); }
      else if (event.key.toLowerCase() === "h" && !event.ctrlKey && !event.metaKey && !event.altKey) hotspots?.toggle();
    });
    let wheelStreak = 0;
    let wheelPrevAt = -1e6;
    let wheelHoldUntil = 0;
    addEventListener("wheel", event => {
      if (modalOpen() || !overview.hidden || event.ctrlKey) return;
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
        turn(direction);
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
      turn(direction);
    }, {passive: true});
    let swipe = null;
    addEventListener("touchstart", event => {
      swipe = null;
      if (!overview.hidden || modalOpen() || event.touches.length > 1) return;
      if (event.target instanceof Element && event.target.closest(
        "video, audio, iframe, button, a, input, select, textarea, .deck-chrome, .touch-nav, .interactive-frame",
      )) return;
      const touch = event.changedTouches[0];
      if (touch) swipe = {id: touch.identifier, x: touch.clientX, y: touch.clientY};
    }, {passive: true});
    addEventListener("touchend", event => {
      const start = swipe;
      swipe = null;
      if (!start || !overview.hidden || modalOpen()) return;
      const touch = [...event.changedTouches].find(t => t.identifier === start.id);
      if (!touch) return;
      const dx = touch.clientX - start.x;
      const dy = touch.clientY - start.y;
      if (touchReview.matches && Math.abs(dy) > 55 && Math.abs(dy) > Math.abs(dx) * 1.3) {
        controlsExpanded = dy < 0;
        scaleCurrent();
      } else if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.3) {
        if (touchReview.matches) controlsExpanded = false;
        turn(dx < 0 ? 1 : -1);
      }
    }, {passive: true});
    addEventListener("touchcancel", () => { swipe = null; }, {passive: true});
    overview.addEventListener("click", event => {
      const card = event.target.closest("[data-index]");
      if (!card) return;
      const target = Number(card.dataset.index);
      // Overview jumps are bookmarks, unlike ordinary next/previous paging.
      // Preserve the departure screen so Back can return to it. A jump to
      // another slide opens it with none of its steps shown.
      if (target !== index) {
        history.pushState(null, "", `#/${target}`);
        index = target;
        revealed = 0;
      }
      toggleOverview(false);
    });
    document.querySelector("#overview-button").addEventListener("click", () => toggleOverview());
    mobileMenuButton?.addEventListener("click", () => {
      controlsExpanded = !controlsExpanded;
      scaleCurrent();
    });
    touchOverviewButton?.addEventListener("click", () => toggleOverview());
    touchControlsButton?.addEventListener("click", () => {
      controlsExpanded = !controlsExpanded;
      scaleCurrent();
    });
    controlsToggle?.addEventListener("click", () => {
      controlsExpanded = !controlsExpanded;
      scaleCurrent();
    });
    previousButton.addEventListener("click", previous);
    nextButton.addEventListener("click", next);
    fullscreenButtons.forEach(button => button.addEventListener("click", toggleFullscreen));
    addEventListener("fullscreenchange", updateFullscreenButtons);
    addEventListener("webkitfullscreenchange", updateFullscreenButtons);
    updateFullscreenButtons();
    // The counter keeps the box of the deck's widest position. The step
    // dots sit inside its box, under the number, in a slot that takes no
    // room, and appear only on a slide with steps: the controls after the
    // counter never move. Built here, so a legacy unit-local index.html
    // gets them too.
    counter.dataset.fit = numbering.widest;
    const counterSlot = document.createElement("span");
    counterSlot.className = "counter-slot";
    counter.replaceWith(counterSlot);
    stepIndicator = document.createElement("span");
    stepIndicator.id = "step-indicator";
    stepIndicator.className = "step-indicator";
    stepIndicator.setAttribute("role", "img");
    stepIndicator.hidden = true;
    counterSlot.append(counter, stepIndicator);
    render(requested.step);
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
      // The pacing footer words why a page without a sink saves only in
      // the browser; an older server sends no `pacing` field at all.
      const pacing = typeof state.pacing === "string" ? state.pacing : "absent";
      if (pacing !== serverPacing) {
        serverPacing = pacing;
        pacingDisk.changed();
      }
      if (!state.livereload) { clearInterval(reloadTimer); return; }
      if (reloadVersion === null) reloadVersion = state.version;
      else if (reloadVersion !== state.version) location.reload();
    } catch (_) {
      // Static releases and file:// previews intentionally have no reload endpoint.
      if (serverPacing === "unknown") {
        serverPacing = "static";
        pacingDisk.changed();
      }
      reloadFailures += 1;
      if (reloadFailures >= 3) clearInterval(reloadTimer);
    }
  }
  reloadTimer = setInterval(pollLiveReload, 900);
  pollLiveReload();

  (async () => {
    const [spec, timing] = await Promise.all([loadSpec(), loadPresentationTime()]);
    if (spec) { boot(spec); setupLectureClock(timing); setupLecturePacer(timing, spec); }
    if (printMode) return;
    // Every page load, scheduled or not: convert old records and upload
    // what the journal still holds, once the serve-only sink has loaded.
    if (document.readyState !== "complete") {
      await new Promise(resolve => addEventListener("load", resolve, {once: true}));
    }
    pacingRecovery(spec ? window.LECTUREDECK : null);
  })();
})();
