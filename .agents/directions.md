# Directions

Open work only. Shipped behavior belongs in `CHANGELOG.md`. Design intent for
the items below lives in `design-viewer-authoring.md`.

- Add the markdown authoring compiler: `slides.md` with TeX math compiled to
  the current `slides.js` artifact; authoring dependencies as an optional
  extra (design section 2).
- Add passkey-guarded write-back and persist geometry adjustments through it
  (design section 4, then section 3 stage two).
- Add browser-level smoke coverage for navigation, overview, fullscreen, and a
  local interactive iframe.
- Decide the long-term compatibility promise before declaring `1.0.0`.
