# Changelog — shipped version history

## Shipped

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
