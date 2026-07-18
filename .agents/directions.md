# Directions

Open work only. Shipped behavior belongs in `CHANGELOG.md`. Design intent for
the items below lives in `design-viewer-authoring.md`.

## Definition of `1.0.0`

- Stabilize the presenter UI and add browser-level smoke coverage for
  navigation, rapid wheel input, overview, fullscreen, theme selection, local
  video, and a keyboard/pointer/touch interactive iframe.
- Fix validation of dependencies relative to nested interactive files; cover
  nested HTML, CSS, and static ES-module references without weakening path or
  external-runtime checks.
- Replace executable `slides.js` as the target browser contract with a
  versioned, schema-validated `deck.json` fetched over HTTP. Keep `slides.js`
  as a supported legacy input throughout `1.x`; new scaffolds use JSON.
- Make `slides.md` with TeX math the primary human authoring format, compiled
  to committed `deck.json` through an optional authoring extra. Detect stale
  generated data and prove the workflow on a reversible representative-unit
  spike before broader migration.
- Complete UI figure adjustment with passkey-guarded write-back to stable-ID
  `adjustments.json`. Support reflowing figure size/stage share, fit, scale,
  shift, and multi-panel proportions rather than relying only on transforms.
- Replace the binary theme toggle with an accessible selector that distinguishes
  color mode from presentation style and can grow without changing deck data.
- Complete the public style guide and freeze the supported style vocabulary for
  the `1.x` compatibility line.
