# Changelog — shipped version history

## Shipped

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
