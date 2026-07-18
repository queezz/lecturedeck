# Directions

Open work only. Shipped behavior belongs in `CHANGELOG.md`. Design intent for
the items below lives in `design-viewer-authoring.md`.

## Definition of `1.0.0`

- Stabilize the presenter UI and add browser-level smoke coverage for
  navigation, overview, fullscreen, theme selection, and a local interactive
  iframe.
- Make `slides.md` with TeX math the primary authoring format, compiled to the
  current `slides.js` artifact through an optional authoring extra (design
  section 2).
- Complete UI figure adjustment with passkey-guarded write-back (design section
  4, then section 3 stage two).
- Replace the binary theme toggle with an accessible selector that distinguishes
  color mode from presentation style and can grow without changing deck data.
- Complete the public style guide and freeze the supported style vocabulary for
  the `1.x` compatibility line.
