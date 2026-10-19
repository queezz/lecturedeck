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
- Not committed in the suite: the Gecko checks run through a scratch
  WebDriver BiDi client against headless Zen (no Gecko in the Playwright
  install here: its Firefox will not start). A small stdlib BiDi harness
  in `tests/` would let the browser suite run in Gecko too.
- Pre-existing Gecko layout gap, found while testing: in a `figures` grid
  an SVG figure with a `viewBox` and no `width`/`height` lays out zero
  pixels wide in Gecko (Chromium fills the cell), and a sized SVG keeps
  its own width. `.figure-card img` uses `width: auto; height: 100%`; it
  needs a definite width for SVGs without an intrinsic size.

## Open after photo hotspots (0.27.0)

- Owner judgment at the first lecture with them (the Solvay 1927 photo):
  the hint ring's strength (0.7 opacity cream, gold when active), the
  popup's side (beside the face, on the side with more room, which covers
  neighbours in a crowded row), and whether he wants a mode that shows
  every ring without hover. All are one CSS variable or one branch.
- Trackpad and touch on the presenting Mac and an iPad were not tried:
  WebKit ran through Playwright on Windows, a touch tap through Chromium's
  touch emulation only.
- Hotspots exist only on figure objects. An image in slide HTML (a photo
  card) has none; a `data-hotspots` attribute would need its own check.
