# Directions

Open work only. Shipped behavior belongs in `CHANGELOG.md`. Design intent for
the items below lives in `design-viewer-authoring.md`.

- Implement the viewer/content split: serve the runtime from the installed
  package, add the unit-owned `deck.css` hook, materialize the runtime into
  releases, and scaffold content-only units (design §1, target v0.5.0).
- Add geometry adjust mode, stage one: keyboard nudge/scale for figures in
  serve mode with the resulting `shift`/`scale` values shown for pasting
  (design §3).
- Add the markdown authoring compiler: `slides.md` with TeX math compiled to
  the current `slides.js` artifact; authoring dependencies as an optional
  extra (design §2).
- Add passkey-guarded write-back and persist geometry adjustments through it
  (design §4, then §3 stage two).
- Add browser-level smoke coverage for navigation, overview, fullscreen, and a
  local interactive iframe.
- Decide the long-term compatibility promise before declaring `1.0.0`.
