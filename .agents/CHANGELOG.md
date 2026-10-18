# Changelog — shipped version history

## 0.26.0

Owner, 2026-10-18: "Projector eats a lot of contrast, so we need some tool
to make images brighter. And maybe a zoom tool. So I can click on any
picture, and it fills the screen, and I can adjust brightness/contrast..."

- A photo viewer. A click or tap on a content image of the live slide (a
  figure, a figure grid, an image in slide HTML such as a photo card)
  opens a copy of it in a modal overlay that fills the window, scaled to
  fit. A zoom-in cursor marks what opens. A video, whose click plays it,
  opens from a small expand control on its top right corner, placed out
  of the slide's layout; the viewer plays a copy on from the slide's
  moment, and closing leaves the slide's video paused where the viewer
  left it. Links and other controls, formulas (also image formulas such
  as `img.math-display`), interactive pages, the chrome and anything in
  `data-photo="off"` never open. The copy keeps a `deck.css` filter (a
  dark-theme invert) and, behind a transparent drawing, the slide's
  background, so it reads as it does on the slide.
- Big plain controls along the bottom (labels 20 px on a fixed dark bar,
  the same in both color modes): brightness and contrast in 10 % steps
  from 50 to 300 %, zoom from fit to 8×, each showing its value
  ("Brightness 130 %") in a fixed box so no button moves, **Use on all
  photos**, **Reset** and **Close**. Brightness and contrast are CSS
  `filter: brightness() contrast()`.
- Zoom around the cursor with the wheel, a trackpad scroll or pinch;
  drag to pan, never past an edge; double-click toggles fit and 2×; two
  fingers pinch on a touch screen. Keys, all free in the viewer: `B` /
  `Shift+B` brightness, `C` / `Shift+C` contrast, `+` / `-` zoom, `0`
  reset, `A` all photos, `L` laser (it keeps tracking over the photo).
- A paging or clicker key (`PageDown`, `PageUp`, arrows, `Space`, `Home`,
  `End`) or `Escape` only closes the photo, on the same slide and step:
  it never pages or steps, also when a bar button has the focus, and the
  clicker's next press pages the deck again. The backdrop and **Close**
  close it too. In native full screen the browser's `Escape` leaves full
  screen and the photo closes with it, with no overview behind.
- Brightness, contrast and the toggle are kept per deck (address and
  title) in local storage, so the next photo opens with the same
  correction; every access is guarded and the viewer works without
  storage. **Use on all photos**, also a checkbox in the Appearance
  dialog, corrects every content photo and video of the slides and the
  overview thumbnails, never an SVG drawing, a formula, the chrome,
  print or PDF; a `deck.css` filter on an image keeps priority.
- Nothing moves: the page counter, step dots, footer and controls strip
  keep their boxes to the pixel while the photo opens, changes and
  closes. Pacing counts time in the viewer as time on its slide, with no
  pause and no slide change; the tail of a trackpad scroll that zoomed
  the photo never pages the deck after it closes, and a video copy closed
  before it loaded never plays. Print and PDF contain no viewer.
- Browser tests cover opening and fit, every closing key, the controls
  and their limits, zoom around the cursor, pan and double-click,
  remembered settings with and without storage, the all-photos scope,
  fixed chrome at two sizes, the video copy with a seekable WebM served
  with range support, exclusions, the laser, full screen and pacing.

## 0.25.1

Owner, 2026-10-18, on the first stepped lecture: "Your dots shift the page
numbers. I HATE it when a thing with a fixed position is shifted. Jumpy
from slide to slide."

- The step dots no longer move anything. In 0.25.0 they sat in the
  footer's row after the page number, so every stepped slide pushed the
  page number and the course name left (by more with more steps) and could
  narrow and rewrap a long source line; in the controls strip they pushed
  every control after the counter right. The footer dots now sit under the
  page number, in the frame's bottom padding, and the strip's dots inside
  the counter's own box, under the number; both are positioned out of the
  layout and drawn at a fixed size (the strip's are drawn marks now, not
  `●○` characters). Print, PDF and the overview still show none.
- The page number and the counter keep the width of the deck's widest
  position, so going from slide 9 to 10, or into the backup, no longer
  moves the course name or the controls beside the counter. The counter's
  digits are tabular.
- A browser test holds the page number, course name, source line, footer,
  header, body, counter and controls to the pixel across slides with no
  steps, one and three, at no step, mid-way and whole, from 9 to 10 and
  into the backup, in both themes and at two window sizes; it fails on
  0.25.0. A legacy `deck.css` rule that draws a pill on every span of the
  strip draws none on the counter's slot or its dots.

## 0.25.0

Owner, 2026-10-17: "We can dev step by step reveal." A slide must have one
obvious reading path, and a screen that shows every block at once does not
say where to look first.

- Step-by-step reveals. Any element of slide HTML with `data-step="N"`, and
  a figure, each `figures` item, each card, an object `formula`, an
  `interactive` or a `video` with a numeric `step`, waits hidden until its
  step. Elements sharing a number appear together; content without one is
  always on screen. Next (keys, the Next control, wheel, swipe, clicker, an
  interactive page's direction `1`) shows the next number still hidden and
  then changes slide; Previous hides the last one and then goes back, where
  the previous slide arrives whole. `Shift` with the arrow and page keys
  moves by whole slides, for rewinding, and while the overview is open
  every press moves by whole slides. Decks without steps behave as before.
- A hidden step keeps its place, so nothing moves when it appears; it fades
  in over about a quarter of a second, at once under reduced motion. It is
  hidden from screen readers and cannot hold focus: focus inside it, also
  inside an embedded page, leaves as it hides, so the keyboard and the
  clicker keep driving the deck. A caption, quote or gloss item that is all
  one step takes its box with it. A video stepped back out of view pauses,
  and a stepped interactive page loads only when its step first appears, so
  an animation starts in front of the audience instead of finishing unseen.
- Only what the layout shows counts. One twin of a dark/light figure pair,
  or a block `deck.css` drops below some width, waits hidden; switching the
  theme mid-slide or resizing no longer shows the other twin early or spends
  a press on nothing. A step nested in a later one appears with it. A
  section slide's stepped title steps only that slide, never the eyebrow of
  the slides after it.
- The address reads `#/N.k` once steps up to `k` are shown, so reload and
  live reload keep the step; `#/N` and overview jumps open a slide bare,
  `End` shows the last slide whole. Small dots after the page number in the
  slide footer (and beside the counter) show the steps shown and to come,
  where the presenter looks even with the controls strip collapsed. The
  overview, print, `lecturedeck pdf`, the narration skeleton and the dialogs
  always show every step; pacing records keep one visit per slide.
- `check` rejects a step that is not a positive integer, a step in content
  the slide never shows, and a `data-step` in `meta.section` or
  `meta.opening`; it prints a `WARNING:` for a gap in a slide's numbers and
  for a step nested in a later one.
- An interactive page's `{type: "lecturedeck:navigate", to: "first"}` or
  `to: "last"` now acts as the deck's `Home` or `End`; the deck used to
  ignore it.
- Closing the Appearance dialog while the controls strip is collapsed no
  longer leaves the next arrow key on one of its radios: that press used to
  be lost, a dead key right after a theme switch.

## 0.24.0

Owner, 2026-10-14, after the lecture of 13 October: "the timings save button was on the
end of a long list, With no good back/close option. And saving location was
default, downloads folder."

- Pacing records save themselves. While `serve` delivers a scheduled deck to
  a browser on the serving computer, each page load's segment is written to
  `<unit>/pacing-records/<date>_<HHMM>_<unit>_<segment>.json`, beside
  `webdeck/`: 2 s after a slide change, at phase boundaries and pauses,
  every 15 s while a segment is open (also while the report is held open),
  and with keepalive when the tab hides or closes. Nothing needs pressing. The write code is a serve-only `pacing-sink.js`, injected only
  for a loopback (or own-address) browser with a `localhost` or IP-literal
  `Host`, exact `Origin`, the custom header and no proxy headers; releases,
  PDF exports, LAN viewers and automated browsers never write. The server
  rebuilds each record from a strict whitelist, writes it atomically, keeps
  only a higher revision and never deletes. `serve --no-pacing-records`
  turns it off; `/__lecturedeck/version` reports the `pacing` state.
- Recording runs from 30 min before to 60 min after the slot, and every
  visit is tagged `before`, `slot` or `after`, split exactly at the
  boundaries. The report leads with the last main-slide change and the
  signed overrun, so a closing slide left up during questions no longer
  reads as overrun; "deck on screen until" is shown separately. Opening a
  page (the deck itself, or again after class to read the report) is no
  slide change, and coming back from the backup to the slide shown before it
  is no main-slide change. The overrun reads in whole seconds, floored like
  the wall times beside it.
- Record schema 2: titles once per slide in a `slides` map, unbroken visits
  (a gap over 10 s or a 2 s clock disagreement credits nothing and logs a
  `suspended` or `clock` pause, also inside an overview, report or dialog
  pause), pauses with their reason (overview, report, dialog, hidden tab),
  and time in full screen. A segment rolls over at
  48 KiB so the closing keepalive always fits.
- The report keeps Close and Export JSON on screen and scrolls only its body:
  headline, four tiles, notes, a section table with one backup row, "not
  shown" slides, and collapsed per-slide and timeline tables. A footer says
  where the record went or why it stayed in the browser, and the button's
  dot is green (disk), gold (browser only) or red (failing). Older entries
  the server will not take (another unit, a date no longer scheduled) stay
  pending without blocking the open deck or hiding "Disk saving ready". Export is now
  secondary and names the file `<date>_<HHMM>_<unit>_export.json`, like the
  records: lecture and start time, not only the date.
- Any open dialog now owns keys, the wheel, the trackpad and swipes: Escape
  in the report no longer opens the overview, arrows no longer page the deck
  behind it, an Escape that leaves native full screen no longer opens the
  overview behind a dialog, and the adjust HUD's keys stay out.
- Two tabs on one date no longer overwrite each other's record: each page
  load writes its own segment, and the report merges them, counting
  overlapping time once for the window that changed slide most recently and
  saying so; an idle second window no longer wins the phase-boundary splits.
  The note tells page reloads, rollovers to a new file and other windows
  apart.
- Schema-1 browser records from 0.20–0.23 convert once into migrated
  segments and upload to their own unit on the next page load, once their
  slot has ended (an older tab may still be writing one); the old keys are
  kept. The browser journal also uploads what a crash or a stopped server
  left behind. The upload script answers 413 itself for a body over
  256 KiB, so an oversized migrated record is refused at once instead of
  retried as a network error ahead of newer ones.

## 0.23.2

- The laser pointer tracks over interactive animations. An embedded page is
  its own document and kept the mouse to itself, so the dot froze at the
  animation's edge. While the laser is on, interactive frames now let the
  mouse through. Switching it off (L) gives the animation its mouse back.
  Reported by the owner on 2026-10-14; reproduced on a real deck's
  animations with 0.21.0 and fixed there with this viewer. A browser test
  covers the dot over a frame and the frame getting its mouse back.

## 0.23.1

- Backup slides show where the presenter is: the counter and footer read
  `B4 / 92` (position and backup total) instead of bare `B4`; screen readers
  hear "Backup slide B4 of 92". Main slides keep `21 / 57`. Overview cards,
  the pacing report and its `label` field keep the bare `B4`. Decks without
  `appendix: true` are unchanged (owner request, 2026-10-13: a bare `B4`
  did not say how deep the backup goes, and `B4 / B92` reads strangely).
- The blank-page PDF regression test now sweeps 18–28 gloss lines, one
  slide each. The bug appears only in a narrow, font-dependent band of
  overflow, and the single 24-line slide caught it only with Calibri. Without
  containment the sweep now fails under every font tried; with it, it passes.
  The test's docstring no longer names a consuming course.

## 0.23.0

- `#/N` links in a PDF export now jump inside the document. Print mode gives
  each page the anchor `slide-N` and points every `#/N` link at it, resolved
  as the live viewer resolves the hash. Chromium writes them as named
  destinations instead of dead URLs into the export's temporary localhost
  server. External links stay links.
- A slide whose body overflowed its page, even by a pixel, printed blank
  under its title: Chromium pushed the body past the page, out of the
  clipped frame. Print frames are now contained (`contain: size layout
  paint`), so each slide is one page that is never fragmented. Found on five
  formula pages of a 149-page lecture. The other pages are unchanged apart
  from anti-aliasing.

## 0.22.0

- Add `lecturedeck narration [UNIT] [--deck PATH] [--outline] [--output
  FILE]`: a Markdown skeleton of each slide's visible content for
  spoken-text translation, or a JSON outline (schema 1) of chapters, ids,
  labels (`12`, `B3`) and titles. Both carry the deck's sha256 with BOM and
  CRLF normalized.
- Chapters follow section slides, the appendix marker and its later
  sections; decks without sections fall back to eyebrow changes. Layout
  gating, `chrome: false`, eyebrow overrides, `#/N` navigation, figures,
  cards, interactives and video mirror the viewer; MathML is linearized
  and kept beside its TeX annotation. Output is UTF-8/LF on any console.
- Escaped markup such as `&lt;v&gt;` stays text in the skeleton, a table
  nested in a cell becomes one line, and text outside table cells is kept.
  Markup nested past 200 levels is read flat instead of overflowing the
  stack, and a reader that closes the pipe early ends the output quietly.
  Legacy `slides.js` ids must be kebab-case, and a unit name that would
  break the header is refused.
- `python -m lecturedeck` now exits with the command's status (it always
  exited 0 before); the installed `lecturedeck` script was unaffected.

## 0.21.0

- Mark backup material with an optional `appendix: true` slide field. Main
  slides count against the main total (`21 / 46`); the appendix reads B1, B2,
  … in the counter, footer, overview, aria labels and pacing report. Paging,
  Home/End, history and `#/N` deep links keep raw positions.
- Expose `data-appendix` on appendix frames and `in-appendix` on the body for
  unit styling. Validation requires a boolean and at most one marker; decks
  without it render exactly as before.

## 0.20.0

- Add an opt-in presenter clock with scheduled time remaining, last-five-minute
  and overdue states, a menu toggle, timezone support and wake/reload recovery.
  Configure with webdeck/presentation-time.json; static releases retain it.
- Optionally record per-slide dwell during configured teaching dates/slots,
  preserving visits locally across reloads with a pacing report/JSON export.

## 0.19.0

- Tap the small gear or swipe up to open phone/touch controls without a
  persistent toolbar covering slides.
  Overview, previous/next, fullscreen, appearance, laser and selector remain
  reachable; swipe down or Close menu dismisses the menu. Overview has an
  always-reachable close control while scrolling.
- Restrict paging swipes to horizontal single-finger gestures outside overview,
  settings, media and interactive controls. Pinch gestures retain their own
  behavior; vertical gestures on the slide open/close the touch menu.

## 0.18.1

- Preserve the current slide when leaving native video fullscreen. Only an
  unexpected exit from deck-root fullscreen opens the overview. Add a browser
  regression for the player return-to-normal path.

## 0.18.0

- Add optional stable tab titles and declarative selector title/icon identity.
  Keep existing slide-title tabs and generic selectors as defaults; conflicting
  selector identities fall back to generic branding. Validate local icon assets
  and preserve their offline release copying.

## Shipped

- **v0.17.6** — Let a repository choose its default teaching selector folder
  in lecturedeck.toml. Plain serve and managed restarts use that selection;
  explicit --folder and named-unit commands retain their existing behavior.

- **v0.17.5** — Measure the expanded controls consistently so opening tools
  cannot oscillate safe-space placement. Prevent legacy span styling from
  drawing a second gear border or enlarging the tools wrapper.

- **v0.17.4** — Keep overview jumps in browser history so Back returns to
  the screen a reader left and Forward restores the selected destination.
  Ordinary next/previous paging still updates the current location without
  creating a history entry for every slide. Re-selecting the current slide
  closes overview without adding a duplicate entry.

- **v0.17.3** — Give the shared server and searchable deck selector a generic
  Lecturedeck favicon. The stable `/favicon.svg` endpoint also lets service
  launchers show a recognizable icon for every discovered course. Keep the
  presentation-controls gear available in full screen so the overview,
  appearance, laser, and exit controls remain reachable while presenting.
  Quiet the selector into the shared WebUI top-bar and sticky-rail vocabulary,
  keep search available while scrolling, group lectures, homeworks, and extras,
  and let `meta.selectorHero` add an optional image to a deck card.

- **v0.17.2** — Centre native display formulas, honor per-slide eyebrow
  labels, and keep beat codes in author metadata instead of the footer.
  Flush the serving address to redirected logs before accepting requests.
  Clarify managed preview entry points and MathML fraction grouping.

- **v0.17.1** — Fill non-16:9 displays in full screen without stretching or
  cropping. Presentation mode now expands the fixed slide canvas into the
  viewport's spare dimension, while windowed slides, overview thumbnails, and
  PDF output keep their authored 16:9 frame.

- **v0.17.0** — Point at the slide with a laser pointer. `L` or the new
  **Laser** control toggles a glowing dot that tracks the pointer and hides
  the arrow over the slide, for presenting and for screen-recorded lectures.
  The dot carries the current slide's accent colour over a white core, turns
  itself off when the overview opens, and hides while the pointer is over an
  interactive iframe or outside the window. It is created after the
  print-mode branch returns, so PDF export never contains the element.

- **v0.16.1** — Polish selector navigation and compact presentation controls.
  Decks opened through the selector now show a home action back to its root;
  directly served decks keep it hidden. The cramped `Controls` handle becomes
  an accessible gear button and sits slightly farther from the slide edge.

- **v0.16.0** — Select and serve decks from one presentations folder. Running
  `lecturedeck serve` without a unit opens a searchable selector for the
  auto-detected course, while `--folder PATH` selects an explicit parent
  folder. Discovery stays shallow, uses declarative deck titles when
  available, supports legacy units by folder name, and gives each deck an
  isolated route that still exposes only its `webdeck/` tree.

- **v0.15.0** — Give concurrent decks distinct browser identities. Deck
  metadata can select built-in complex-number, calculus, or plasma favicons,
  or point to a validated custom image under `assets/`; the browser viewer
  applies either form in served and frozen offline decks.

- **v0.14.1** — Keep native video controls at the media's intrinsic aspect
  ratio. Video slides now center the player within unusually wide stages
  instead of stretching its element across the row and introducing black
  pillar bars around ordinary widescreen media.

- **v0.14.0** — Replace the binary theme toggle with an accessible Appearance
  dialog. Separate radio groups persist color mode and presentation style as
  browser preferences without changing deck data; the first curated presets
  reuse the saved accent-gradient and title-rule vocabulary. `T` opens the
  dialog, `Escape` closes it without opening the overview, and PDF export
  ignores saved style presets for deterministic output.

- **v0.13.0** — Export checked decks to PDF with `lecturedeck pdf`. The
  optional Playwright/Chromium path serves only the unit's `webdeck/`, waits
  for local images and fonts, renders one fixed 16:9 slide per page, and
  writes atomically without overwriting an existing file. Light output is the
  default, dark output is explicit, and video or interactive content becomes
  a poster or labeled static placeholder. The runtime remains standard-library
  only; the Chromium smoke suite covers the all-slides print contract.

- **v0.12.2** — Align multi-line derivations on the relation column. MathML
  Core dropped `columnalign`, so the viewer now honors the declared
  two-column derivation form (`mtable columnalign="right left"`) with CSS:
  the left-hand side right-aligns to the axis and each relation row starts
  at it, matching LaTeX `align`. Document the composing rule and cover it in
  the smoke suite.

- **v0.12.1** — Keep the presentation controls in one place. Collapsed tools
  no longer shrink and wrap into a taller hidden block (the counter and theme
  button previously doubled the strip height), and positioning re-measures
  after applying the collapse state, so the strip no longer jumps between
  positions on clicks and slide changes. Scope formula-gloss dividers to the
  generated item spans so inline markup inside a gloss phrase no longer grows
  its own divider bars, and use the themed border color. Document composing
  rules for glosses and `mtext` whitespace in the README.

- **v0.12.0** — Show the viewer version in the presentation controls. The
  expanded bottom-left strip carries a small `vX.Y.Z` label, so a served deck
  reveals the installed viewer and a frozen release reveals the viewer it was
  built with, including when deck data fails to load. The `VIEWER_VERSION`
  constant joins the version canon; the test suite enforces lockstep with the
  package version.

- **v0.11.1** — Auto-fit oversized formulas. MathML does not wrap and math
  font metrics differ per browser, so an authored formula can exceed its
  stage; the viewer now measures real ink (scroll metrics, since client
  rects clamp MathML to its max-width) and shrinks only formulas that
  overflow, in slides and overview thumbnails alike. Formulas that fit keep
  their stylesheet size, so existing decks render unchanged. Found when a
  unit migrated off its local viewer fork, whose equation style was 42px
  against the packaged 72px.

- **v0.11.0** — Add a Chromium smoke suite for the presenter contract as an
  optional Playwright dev extra. Fifteen headless tests cover the `deck.json`
  and legacy `slides.js` loading paths, keyboard navigation, discrete-wheel
  and trackpad-glide input, overview, fullscreen with the Escape behavior,
  theme persistence, video attributes and key guarding, pointer-driven
  interactive iframes, touch swipe, declarative figure geometry, deck-error
  reporting, the slashless-root redirect, and both geometry-adjust guards.
  The suite skips itself when Playwright or Chromium is absent and asserts
  mechanical behavior only; visual judgment of real decks remains a human
  release step. The runtime keeps zero dependencies.

- **v0.10.1** — Keep geometry adjustment off the overview: `G` is inert while
  the overview grid is open, opening the overview closes an active adjustment
  HUD, and a single `Escape` closes the overview again. Verified against real
  course decks (content-only, unit-local runtime, and figure-heavy units) with
  the `v0.10.0` viewer.

- **v0.10.0** — Make schema-validated `deck.json` the primary browser
  contract. The viewer fetches it over HTTP, reports schema and data problems
  on the slide surface, and falls back to legacy executable `slides.js`
  automatically; new scaffolds emit JSON only. `check` validates the schema
  version, viewer requirement, field types, enums, stable slide and figure
  IDs, figure geometry ranges, and every declared local asset. Resolve
  nested-interactive references relative to the file that declares them and
  extend scanning to CSS `url()`/`@import` targets and static ES-module
  imports, still rejecting path escapes and external runtime dependencies.
  Redirect the slashless `/webdeck` root so relative deck URLs resolve, and
  stop geometry-adjust keys from also paging the deck or opening the overview.

- **v0.9.0** — Keep presentation controls clear of slide footers: the full
  toolbar uses spare space around the fitted slide, collapses to an accessible
  handle when it must overlay content, and hides in fullscreen. Add reusable
  accent-gradient and title-rule style options with a public style guide.
  Define the remaining `1.0.0` gates and make the canonical external install,
  rather than course-local source submodules, the consumer workflow.

- **v0.8.0** — Let concurrent `lecturedeck serve` processes coexist. Without an
  explicit `--port`, each server advances from 4173 to the next available port
  and prints or opens the selected URL; explicit ports remain strict.

- **v0.7.0** — Add a persistent dark/light theme control (`T`) to the viewer.
  Native-fullscreen controls remain visible, and an Escape-driven exit now
  opens the overview; `F` exits full screen without opening it.

- **v0.6.0** — Add serve-only keyboard geometry adjustment for figure slides.
  `G` opens a HUD with pasteable `shift`/`scale` values; arrows, brackets,
  `Tab`, and `R` adjust, select, and reset figures without writing source
  files. The packaged viewer renders accepted declarative geometry in every
  context, while static releases omit the adjustment controls.

- **v0.5.0** — Split deck content from the viewer. New units contain only
  `slides.js`, unit-owned `deck.css`, and `assets/`; serving supplies the
  installed HTML/CSS/JavaScript viewer, while local legacy viewer files still
  override it. Validation accepts content-only units and static releases
  materialize the installed viewer into self-contained bundles.

- **v0.4.0** — Add `lecturedeck refresh`, which updates a unit's runtime
  snapshot to the installed version: clean snapshots of any published version
  are replaced, locally modified files are kept unless `--force`, and
  `slides.js`, `index.html`, and `assets/` are never touched. Upstream three
  unit-proven runtime features: figures without captions render no empty
  figcaption, slides inherit their accent from the enclosing section
  (`meta.openingAccent` sets the opening), and `slide.className` adds custom
  classes to the slide frame.

- **v0.3.0** — Serve only the unit's `webdeck/` tree so scripts and briefs
  beside it stay private even on `--lan`, and disable directory listings. Add
  trackpad-aware wheel navigation, deck styles for links, ordered lists, code,
  and tables, adaptive overview thumbnails, and keyboard paging that keeps
  working after chrome clicks. Untitled slides no longer break rendering,
  edge navigation no longer restarts playing media, live-reload polling stops
  when disabled or offline, and a busy port reports a friendly error.

- **v0.2.0** - Add first-class offline video slides with local source and caption
  validation, poster-based overview placeholders, explicit original-video
  attribution links, and media-safe keyboard and touch navigation.

- **v0.1.1** — Validate the local stylesheet and presentation runtime declared
  by `index.html` instead of forcing scaffold filenames. Existing self-contained
  unit snapshots can move to the shared CLI without runtime renames or release
  hash churn; new scaffolds still use `lecturedeck.css` and `lecturedeck.js`.
- **v0.1.0** — Initial public extraction. Generic `lecturedeck` CLI and browser
  runtime; responsive 16:9 presentation shell; native MathML; keyboard, touch,
  overview, fullscreen, and immersive interactive navigation; cache-free local
  and LAN serving; live reload; strict self-contained bundle validation; static
  release copying; and public privacy/versioning workflows.
