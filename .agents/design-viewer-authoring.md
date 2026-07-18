# Design directions — viewer split, authoring, guarded editing

Status: agreed with the instructor and revised after the presentation-system
orientation on 2026-07-18. This file holds design intent; `directions.md`
tracks the open work items and `CHANGELOG.md` records what shipped. Update this
document when a phase ships or the design changes.

## Why

- Units currently hold runtime snapshots; they drift from the tool and needed
  the `v0.4.0` `refresh` command as a band-aid. Decks should be content only,
  with the presentation runtime detached.
- `slides.js` authoring (HTML in JS strings, hand-written MathML) is the main
  friction in making slides. The instructor wants human-editable decks that
  lean on standards — not another PowerPoint, and not a full web editor.
- Figure placement is judged visually; iterating numeric offsets against a
  reload is slow. Figures commonly need to occupy more of the slide, followed
  by small on-the-glass position and crop corrections.
- Presentation always happens through a local HTTP server. Direct `file://`
  opening is not a supported requirement and must not force executable course
  content or distort the runtime-data design.
- Mature presentation systems remain reference implementations, not product
  dependencies. The current evidence does not justify replacing the viewer;
  borrow proven authoring and interaction ideas without importing a second
  general presentation framework.

## 1. Viewer/content split (shipped in v0.5.0)

`lecturedeck` becomes a viewer; a deck is files.

- Serve `index.html`, `lecturedeck.css`, and `lecturedeck.js` from the
  installed package. A unit's `webdeck/` currently holds only content:
  `slides.js`, optional `deck.css`, and `assets/`. Section 2 replaces
  executable `slides.js` as the target contract while retaining it as a
  compatibility input.
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

## 2. Declarative runtime data and Markdown authoring (JSON shipped in v0.10.0)

Markdown in, schema-validated JSON out. Authoring remains separate from the
viewer, and course-owned deck data no longer executes in the parent page.
Since `v0.10.0` the viewer fetches and validates schema-version-1 `deck.json`
over HTTP, falls back to legacy `slides.js`, and new scaffolds emit JSON;
`slides.md` compilation, the source digest, and `adjustments.json` are the
remaining pieces.

### Unit files

A new content-only unit uses:

```text
webdeck/
  slides.md
  deck.json
  adjustments.json   # optional, created after accepted visual changes
  deck.css            # optional
  assets/
```

- `slides.md` is the human-owned narrative and structural source: CommonMark
  body, YAML front matter for deck metadata, one slide per top-level heading
  with constrained attributes (`{layout=figure accent=blue}`), a claim field,
  and standard image syntax where that is sufficient.
- Small fenced YAML blocks express parts that ordinary Markdown cannot:
  cards, formula glosses, local video, interactive iframes, multi-panel
  figures, and other named schema components. They are data, not arbitrary
  browser programs.
- Math is written in TeX-like notation and compiled to native MathML. Raw
  MathML and tightly bounded raw HTML remain escape hatches for reviewed edge
  cases, not the normal equation or layout language.
- `deck.json` is the generated browser contract. It contains a schema version,
  viewer requirement, stable slide and component IDs, compiled content, and
  explicit local asset references. It contains no functions, helpers, dynamic
  imports, or executable deck code.
- `deck.json` is committed. This lets the standard-library runtime serve and
  release a checked deck without installing the optional authoring toolchain.
  The generated file records a source digest; `serve` and `check` must report
  stale output rather than silently presenting an old compilation.
- `adjustments.json` is a structured, reviewable overlay keyed by stable slide
  and component IDs. The compiler merges it into `deck.json`. This keeps
  browser-approved visual corrections out of generated data and avoids
  brittle Markdown rewriting.

### Loading, releases, and compatibility

- The viewer fetches and validates `deck.json` over HTTP. `lecturedeck serve`
  is the supported development and presentation path; direct `file://` use is
  deliberately unsupported.
- A frozen release is a static directory containing the viewer, `deck.json`,
  optional `deck.css`, and local assets. It works offline when served by any
  ordinary static HTTP server and requires no rebuild or package registry.
  Self-contained means no network runtime dependencies, not double-clickable
  HTML.
- `release` may omit authoring-only `slides.md` while preserving the compiled
  deck, adjustment result, attribution, and every runtime asset needed to
  reproduce the presentation.
- `slides.js` remains accepted as a legacy input throughout the `1.x` line so
  existing units can migrate deliberately. It is executable trusted content,
  cannot receive the full schema-safety guarantee, and is not created by new
  scaffolds once `deck.json` ships.
- Dependencies for Markdown and TeX-to-MathML compilation are an optional
  authoring extra. The viewer, server, validation of generated JSON, and
  release path remain Python-standard-library-only and CDN-free.

### Schema and validation boundary

- Validate field types, enum values, IDs, schema compatibility, layouts,
  figure geometry, media metadata, and every declared local asset before
  serving or releasing a JSON deck.
- Normal attribution links may remain remote. Runtime scripts, styles, fonts,
  media, caption tracks, figures, and interactive dependencies must be local.
- A custom interactive is an explicit iframe component whose entry point lies
  under `webdeck/assets/`. Its Canvas, SVG, WebGL, Bokeh, Plotly, or bespoke
  JavaScript implementation remains free to be application-specific inside
  that iframe; executable code does not move into `deck.json` or the parent
  deck.
- A video component declares local source encodings, MIME types, poster,
  caption tracks, loading policy, classroom caption, and optional attribution
  link. The viewer retains native controls and media-safe keyboard, pointer,
  touch, overview, and theme behavior; JSON changes the data carrier, not the
  supported media capability.
- Validation must resolve references relative to the file that contains them,
  including nested `index.html` files and static CSS/ES-module imports. It must
  reject path escapes and external runtime dependencies without mistaking
  ordinary attribution links for dependencies.
- Parent/iframe communication remains a small versioned `postMessage`
  protocol. The parent accepts messages only from the active known iframe and
  validates message type and payload.

## 3. Figure sizing and geometry adjustment (stage one shipped in v0.6.0)

Figure shifting and scaling happen on the glass, persist as data.

- Stage one: in serve mode, `G` enters keyboard-only geometry mode on slides
  with figures. Arrow keys nudge the selected figure, brackets scale, `R`
  restores its source values, and `Tab` changes selection. Rendering currently
  uses a CSS transform on the figure card.
- Stage two treats "make the figure bigger" as the primary operation. It
  adjusts the figure-stage allocation or panel weight so layout reflows before
  applying content-scale and position corrections. The declarative geometry
  vocabulary covers stage share/width, `fit` (`contain` or `cover`), scale,
  two-axis shift, and multi-panel proportions. Exact field names and ranges
  are frozen with the JSON schema.
- Geometry is always source data, never a persisted DOM mutation. For a
  Markdown/JSON unit, accepted values are written to `adjustments.json` under
  stable IDs and then compiled into `deck.json`. A legacy `slides.js` unit
  retains the stage-one copy/paste workflow until migrated.
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
- Writes are structured and whitelisted. The first writable surface is
  `adjustments.json`: figure-stage allocation, fit, scale, shift, and panel
  proportions keyed by stable IDs. Possibly allow typo-level source patches
  later through the same channel. Never accept freeform HTML or DOM state.
- Every write lands in a file under git so edits arrive as reviewable diffs.
- Releases contain no write code and no endpoints.

## 5. Compatibility promise (decided 2026-07-18)

The shared installation replaces per-course source pins, so compatibility is a
runtime responsibility rather than a consumer-orchestration task.

- Starting with `1.0.0`, a newer viewer in the same major release line accepts
  content-only units that passed `check` under an earlier release in that line.
  Additive content fields are ignored or receive stable defaults.
- `deck.json` is the primary `1.x` browser contract. Its schema version and
  viewer requirement are checked independently from the CLI package version.
  Existing `slides.js` units remain supported compatibility inputs throughout
  `1.x`, but new capabilities may require migration to declarative JSON.
- CLI commands and flags used by the documented course workflow remain
  compatible within a major line. Deprecations must warn for at least one minor
  release before removal.
- A major release may change the content or CLI contract. Consumers adopting a
  new major version must run focused checks and review a fresh static release.
- Static release bundles are frozen artifacts. They remain viewable without an
  installed package and are not rewritten merely because the shared runtime
  changes.
- Legacy unit-local viewer overrides are a migration bridge, not part of the
  post-`1.0.0` compatibility promise. Their files remain preserved, but custom
  behavior is owned and tested by the consumer.
- Pre-`1.0.0` releases continue to use pragmatic `0.x` evolution; the project
  applies the future promise where practical but does not claim it retroactively.

The public README states the user-facing form of this contract. Compatibility
fixes within a major line are patch releases; additive capabilities are minor
releases; incompatible contract changes wait for a major release.

## 6. Theme and style system (started; required for `1.0.0`)

Theme has two independent axes:

- **Color mode** controls readability and ambient use. Dark and light are the
  two current modes and persist as a viewer preference.
- **Presentation style** controls visual treatment without changing content.
  Named, composable slide classes are the low-level vocabulary; a future theme
  selector may expose curated presets built from them.

The first saved options are `style-gradient`, an accent-tinted surface, and
`style-title-rule`, an accent underline for the slide title. They were promoted
from a successful downstream treatment but are generic runtime styles; no
course identity or content belongs here. The public `STYLE_GUIDE.md` documents
their contract and examples.

Before `1.0.0`, the viewer needs an accessible selector that presents color
mode and style distinctly, plus a reviewed style guide covering typography,
layout, accents, figures, formulas, and extension boundaries. The supported
names then enter the `1.x` compatibility promise.

## Boundaries that hold across all phases

- Offline and CDN-free; releases are self-contained static directories served
  over HTTP. They contain no write endpoints or presentation-time build step.
- Runtime and server remain standard-library-only; authoring dependencies
  are an optional extra.
- Deck content stays in human-owned files under version control. Generated
  data is schema-validated and never executable parent-deck code. The browser
  is a viewer plus, at most, a structured-edit surface.
- Arbitrary custom code belongs in an explicitly declared, local iframe
  interactive. The parent viewer owns navigation, layout, theme, media policy,
  validation, and the adjustment protocol.
- Not building: a WYSIWYG editor, drag-and-drop layout, or any edit that
  persists DOM state instead of source data.

## Suggested order

1. §1 viewer/content split (shipped in v0.5.0; ends snapshot drift).
2. Nested-interactive dependency validation (shipped in v0.10.0).
   Browser-level smoke tests for the presenter contract remain open and now
   cover both loading paths.
3. §2 JSON schema and loader, with legacy `slides.js` compatibility (shipped
   in v0.10.0).
4. §2 Markdown/TeX compiler targeting `deck.json`, including stale-source
   detection and a reversible representative-unit spike.
5. §4 guarded write-back to `adjustments.json`, then §3 stage two for
   reflowing figure size, placement, fit, and panel proportions.
