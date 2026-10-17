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

## Open after step reveals (0.25.0)

- Owner decision: should the audience see the footer step dots? They show
  on every stepped slide that has a footer; a deck hides them with
  `.step-cue { display: none; }` in `deck.css`. A `meta` switch is the
  candidate if he wants it per deck.
- Check step reveals in Safari/WebKit, which was not tested. The viewer
  falls back from `checkVisibility` (Safari 17.4+) to client rects; the
  fade, `inert` and the deferred interactive load need a look on the
  presenting Mac.
