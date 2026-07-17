# Design directions — viewer split, authoring, guarded editing

Status: agreed with the instructor on 2026-07-18. This file holds design
intent; `directions.md` tracks the open work items and `CHANGELOG.md` records
what shipped. Update this document when a phase ships or the design changes.

## Why

- Units currently hold runtime snapshots; they drift from the tool and needed
  the `v0.4.0` `refresh` command as a band-aid. Decks should be content only,
  with the presentation runtime detached.
- `slides.js` authoring (HTML in JS strings, hand-written MathML) is the main
  friction in making slides. The instructor wants human-editable decks that
  lean on standards — not another PowerPoint, and not a full web editor.
- Figure placement is judged visually; iterating numeric offsets against a
  reload is slow. Small on-the-glass adjustments are wanted.

## 1. Viewer/content split (shipped in v0.5.0)

`lecturedeck` becomes a viewer; a deck is files.

- Serve `index.html`, `lecturedeck.css`, and `lecturedeck.js` from the
  installed package. A unit's `webdeck/` holds only content: `slides.js`
  (later compiled, see §2), optional `deck.css`, and `assets/`.
- `deck.css` is a unit-owned stylesheet loaded after the runtime stylesheet.
  It replaces whole-runtime forks for unit design (custom block classes,
  size tuning), pairing with the shipped `slide.className` passthrough.
- Migration: unit-local runtime files, when present, override the packaged
  ones so legacy units keep working. Converting a unit means deleting its
  runtime copies and moving custom styling into `deck.css`. `refresh` stays
  as a legacy-unit tool.
- `release` materializes the installed runtime into the bundle: working decks
  always render with the current viewer; released bundles are frozen,
  self-contained snapshots. `check` validates content-only units; releases
  keep passing today's self-containment checks.
- `init` scaffolds only content files. The `{{TITLE}}` substitution in
  `index.html` is dropped; the runtime already titles the document from
  `meta.title`.
- A future soft check may let `meta.requires: ">=0.5"` warn when a deck expects
  a newer viewer; this was not required for the split itself.

## 2. Markdown authoring (target: v0.6.x)

Markdown in, the current deck model out. Authoring sugar, not a new runtime.

- `slides.md`: CommonMark body, YAML front matter for `meta`, one slide per
  top-level heading with brace attributes (`{layout=figure accent=blue}`),
  a `:claim:` line, and standard image syntax for figures. Structured slide
  parts that markdown cannot express (cards, formula gloss, video and
  interactive blocks) ride in small fenced YAML blocks.
- Math is written as TeX and compiled to native MathML. Raw MathML and HTML
  passthrough remain available for edge cases.
- Compilation produces today's `slides.js`, which becomes a generated
  artifact; the served deck format does not change. `serve` recompiles on
  change so the edit-livereload loop stays under a second.
- Dependencies (a Markdown parser, a TeX-to-MathML converter such as
  `latex2mathml`) are an optional authoring extra. The runtime and server
  stay standard-library-only, offline, CDN-free; decks without the extra
  remain fully viewable.

## 3. Geometry adjust mode (stage one shipped in v0.6.0)

Figure shifting and scaling happen on the glass, persist as data.

- Stage one: in serve mode, `G` enters keyboard-only geometry mode on slides
  with figures. Arrow keys nudge the selected figure, brackets scale, `R`
  restores its source values, and `Tab` changes selection. Rendering is a CSS
  transform on the figure card.
- The result is declarative data on the figure — `shift: [dx, dy]`,
  `scale: 1.08` (markdown: `{shift=4,-12 scale=1.08}`) — never a persisted
  DOM mutation. Stage one displays the values on screen for hand-pasting;
  stage two persists them through the guarded write-back channel (§4).
- Stage one controls are injected only by the server; static releases contain
  no adjustment code. Declarative source geometry still renders in releases.

## 4. Guarded write-back (accepted; passkey model)

The instructor accepts authenticated browser write-back — an existing
personal workflow already captures browser notes into local files — and
serving is normally personal, not to students. LAN exposure is a
non-concern once a passkey is required. Guardrails that still hold:

- Off by default; enabled by an explicit serve flag (e.g. `--edit`).
- A simple passkey is required on every write (generated and printed at
  startup or supplied by flag; constant-time comparison; sent as a header,
  not a URL parameter).
- Writes are structured and whitelisted: geometry attributes or a dedicated
  sidecar file first; possibly typo-level text patches later through the
  same channel. Never freeform HTML from the DOM.
- Every write lands in a file under git so edits arrive as reviewable diffs.
- Releases contain no write code and no endpoints.

## Boundaries that hold across all phases

- Offline and CDN-free; releases are self-contained and inert.
- Runtime and server remain standard-library-only; authoring dependencies
  are an optional extra.
- Deck content stays in human-owned files under version control; the browser
  is a viewer plus, at most, a structured-edit surface.
- Not building: a WYSIWYG editor, drag-and-drop layout, or any edit that
  persists DOM state instead of source data.

## Suggested order

1. §1 viewer/content split (unblocks everything; ends snapshot drift).
2. §3 stage one (geometry values on screen).
3. §2 markdown compiler (largest win; decide the optional-extra packaging).
4. §4 write-back endpoint, then §3 stage two (persisted geometry).
