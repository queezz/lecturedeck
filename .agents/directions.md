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

## Open after step reveals (0.25.0, 0.25.1)

- Owner decision: should the audience see the footer step dots? They show
  under the page number on every stepped slide that has a footer; a deck
  hides them with `.step-cue { display: none; }` in `deck.css`. A `meta`
  switch is the candidate if he wants it per deck.
- Check step reveals in Safari/WebKit, which was not tested. The viewer
  falls back from `checkVisibility` (Safari 17.4+) to client rects; the
  fade, `inert` and the deferred interactive load need a look on the
  presenting Mac, and so do the 0.25.1 fixed boxes: the absolutely
  positioned dots and the page number's and counter's reserved width
  (a zero-height `content: attr(data-fit)` line in a column flex box).

## Open after the photo viewer (0.26.0)

- Check it on the presenting Mac, in Zen and Safari: a trackpad pinch
  should zoom the photo, not the page (the viewer takes a ctrl wheel; how
  Gecko on macOS delivers a pinch was not tested), and the correction
  should be judged on the real projector. Gecko was tested headless on
  Windows through WebDriver BiDi, WebKit through Playwright; neither ran
  on macOS.
- `lecturedeck serve` answers no HTTP range requests, so Chromium (Chrome,
  Brave) cannot seek a served video at all: its timeline does not scrub,
  and the photo viewer's copy starts from the beginning instead of the
  slide's moment. Firefox and Zen seek anyway. Range support for media in
  the request handler would fix both.
- Pre-existing Gecko layout gap, found while testing: in a `figures` grid
  an SVG figure with a `viewBox` and no `width`/`height` lays out zero
  pixels wide in Gecko (Chromium fills the cell), and a sized SVG keeps
  its own width. `.figure-card img` uses `width: auto; height: 100%`; it
  needs a definite width for SVGs without an intrinsic size.
