# Directions

Open work only. Shipped behavior belongs in `CHANGELOG.md`. Design intent for
the items below lives in `design-viewer-authoring.md`.

## Definition of `1.0.0`

- Make `slides.md` with TeX math the primary human authoring format, compiled
  to committed `deck.json` through an optional authoring extra. Detect stale
  generated data and prove the workflow on a reversible representative-unit
  spike before broader migration.
- Complete UI figure adjustment with passkey-guarded write-back to stable-ID
  `adjustments.json`. Support reflowing figure size/stage share, fit, scale,
  shift, and multi-panel proportions rather than relying only on transforms.
- Complete the public style guide and freeze the supported style vocabulary for
  the `1.x` compatibility line.
