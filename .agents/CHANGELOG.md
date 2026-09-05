# Changelog — shipped version history

## Shipped

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
