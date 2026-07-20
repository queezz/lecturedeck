# lecturedeck

`lecturedeck` is a small, filesystem-first server and scaffold for self-contained
web lecture presentations. It keeps the reusable runtime separate from course
content: this repository contains the generic server, browser shell, validation,
and tests; each course repository owns its scripts, figures, citations, and
interactive exports.

The runtime uses only Python's standard library plus local HTML, CSS, and
JavaScript. Checked release bundles work offline and do not require a CDN.
PDF export is an optional authoring capability backed by local headless
Chromium; it does not add a runtime dependency to serving or static releases.

## Install outside synchronized course folders

Keep virtual environments outside Dropbox, OneDrive, or other synchronized
course trees:

```powershell
py -3 -m venv "$env:USERPROFILE\.venvs\lecturedeck"
& "$env:USERPROFILE\.venvs\lecturedeck\Scripts\python.exe" -m pip install -e .
```

On macOS or Linux:

```bash
python3 -m venv ~/.venvs/lecturedeck
~/.venvs/lecturedeck/bin/python -m pip install -e .
```

Activation is optional. Call the environment's `lecturedeck` executable
directly for automation.

Install the shared environment editable from one canonical `lecturedeck`
checkout only. Course repositories invoke that environment's `lecturedeck`
executable; they do not copy or submodule the package. A checked static release
freezes the viewer used for publication, so source pinning inside every course
repository is unnecessary.

## Course repository contract

A consuming course repository keeps presentation units under:

```text
Studio/work/presentations/<unit>/
  brief.md
  script.md
  workflow-state.yaml
  webdeck/
    deck.json
    deck.css
    assets/
```

`deck.json` and `assets/` are the deck content. `deck.css` is an optional,
unit-owned override loaded after the installed viewer styles. While serving,
`index.html`, `lecturedeck.css`, and `lecturedeck.js` come from the installed
package; `release` materializes them into the static bundle. Only `webdeck/`
content is exposed or copied, and `lecturedeck` never reads adjacent lecture
scripts, source books, agent notes, or other course materials.

Legacy units may instead carry an executable `slides.js`; the viewer falls back
to it automatically when no `deck.json` exists, and it remains a supported
input throughout the `1.x` line. Legacy units may also retain local copies of
any viewer file. Those files override the installed package while serving and
are preserved in releases, so migration to content-only, declarative units can
happen deliberately.

## Declarative deck data

`deck.json` is the schema-validated browser contract: pure data, fetched over
HTTP, with no functions or executable deck code. A minimal deck looks like:

```json
{
  "deck": 1,
  "requires": ">=0.15",
  "meta": {
    "title": "Sample deck",
    "section": "COURSE TITLE",
    "opening": "OPENING",
    "favicon": "complex"
  },
  "slides": [
    {
      "id": "opening-title",
      "type": "title",
      "title": "Sample deck",
      "claim": "One idea per slide.",
      "accent": "red"
    }
  ]
}
```

- `deck` is the schema version; this release reads version `1`. `requires`
  optionally states the minimum viewer as `">=MAJOR.MINOR"`, and `check`
  rejects a deck that needs a newer installed viewer.
- Every slide carries a stable kebab-case `id`, unique within the deck.
  Figures may carry ids too; the viewer stamps both into the DOM so future
  tooling can address them.
- `meta.favicon` gives the deck a recognizable browser identity. Select the
  built-in `complex`, `calculus`, or `plasma` icon, or name a deck-owned image
  such as `assets/favicon.svg`. Custom favicon paths are validated and remain
  self-contained in static releases. Omit the field to leave the browser's
  default icon unchanged.
- Slide fields mirror the rendering vocabulary: `type` (`title`, `section`,
  `content`), optional `layout`, `title`, `eyebrow`, `claim`, `body`, `quote`,
  `source`, `beat`, `accent`, `className`, `chrome`, `formula`, and one
  content block among `figure`/`figures`, `cards`, `interactive`, or `video`.
  `body`, `quote`, and captions hold compiled HTML; `formula.mathml` holds
  native MathML.
- `check` validates field types, enum values, ids, figure geometry ranges, and
  every declared asset reference before serving or releasing. Unknown fields
  are rejected, so typos surface immediately. Declared media and interactive
  entry points must be local paths inside `webdeck/`; an interactive entry
  point must lie under `assets/`.
- A present-but-broken `deck.json` is reported on the slide surface by the
  viewer rather than silently falling back to legacy data.

### Composing rules for formulas and glosses

These rules apply equally to `deck.json` content and legacy `slides.js`
objects:

- `formula.gloss` entries are standalone phrases. The viewer lays the items
  out in one row and draws a divider between adjacent items, so punctuation
  belongs inside each phrase and one sentence must never be split across
  items.
- Claim, body, caption, and gloss strings may carry inline markup. The
  viewer styles only the structure it generates (for example the gloss item
  spans); nested content spans keep their own appearance.
- MathML trims ASCII whitespace at the edges of token elements. Write
  `<mtext>if&#160;</mtext>` when a visible trailing space is needed inside
  `mtext`.
- A derivation broken across lines is a two-column
  `<mtable columnalign="right left">`: the left-hand side (right-aligned) in
  the first cell, and each relation with its expression
  (`<mo form="infix">≤</mo>…`) in the second. Continuation rows leave the
  first cell empty. The viewer honors this alignment even though MathML Core
  dropped the attribute; never stack centered rows or fake indentation with
  `mspace`.
- Formulas that overflow their stage are automatically scaled down to fit,
  but auto-fit is a safety net, not a layout tool: compose formulas for the
  slide's formula size, and split proofs that need to shrink dramatically.

Reusable visual options, accent names, and the boundary between viewer styles
and unit-owned CSS are documented in [STYLE_GUIDE.md](STYLE_GUIDE.md).

## Compatibility

Starting with `1.0.0`, newer `lecturedeck` releases in the same major line will
continue to accept content-only units checked by earlier releases in that line.
Documented CLI commands and flags follow the same rule; deprecations warn for at
least one minor release before removal. An incompatible unit or CLI contract
change requires a new major version and focused consumer QA.

Static release bundles are frozen and self-contained, so an installed runtime
upgrade never rewrites an existing publication. Legacy unit-local viewer
overrides remain supported as migration inputs, but their custom behavior is
owned by the course and is not covered by the post-`1.0.0` compatibility
promise.

## Commands

Run from a course repository, or pass `--repo PATH` explicitly:

```text
lecturedeck init <unit> --title "Presentation title"
lecturedeck refresh <unit>
lecturedeck check <unit>
lecturedeck serve <unit> --livereload
lecturedeck release <unit> --output <new-output-directory>
lecturedeck pdf <unit> --output <new-file.pdf>
```

`init` creates `deck.json`, `deck.css`, and an `assets/` directory without
overwriting existing files. `check` validates the deck schema and the content
against the installed viewer; it rejects missing files, references that escape
`webdeck/`, and external runtime dependencies. References inside nested
interactive pages — their HTML, CSS `url()`/`@import` targets, and static
ES-module imports — resolve relative to the file that declares them and must
stay local. Normal citation links in `<a href="https://...">` remain allowed.
`release` validates first, freezes the installed viewer into one
self-contained static bundle, and refuses to overwrite its destination.

`pdf` validates first, starts a temporary localhost-only server, and prints
every slide through headless Chromium. The result has one 16:9 slide per page,
uses the light theme by default, and refuses to overwrite an existing file.
Pass `--theme dark` to preserve the dark presentation surface. Videos export
their poster (or a labeled placeholder) and interactive iframes export a
labeled placeholder, since a PDF cannot retain their live behavior.

Install the optional PDF toolchain once in the shared environment:

```powershell
& "$env:USERPROFILE\.venvs\lecturedeck\Scripts\python.exe" -m pip install -e ".[pdf]"
& "$env:USERPROFILE\.venvs\lecturedeck\Scripts\python.exe" -m playwright install chromium
```

The equivalent macOS/Linux commands use `~/.venvs/lecturedeck/bin/python`.
The `dev` extra already includes Playwright, so contributors only need the
one-time Chromium installation.

`refresh` remains a migration aid for legacy units. It updates local copies of
`lecturedeck.css` and `lecturedeck.js` to the installed runtime. A snapshot
matching any published runtime version is replaced; a file with local
modifications is kept and reported until `--force`, and `deck.json`,
`slides.js`, `index.html`, `deck.css`, and `assets/` are never touched.
Content-only units report the viewer files as missing because they already use
the installed viewer. Review any resulting diff in the course repository
afterward.

Serving is localhost-only by default. For a trusted local network:

```text
lecturedeck serve <unit> --lan --livereload
```

Without `--port`, the first server uses port 4173. If that port is occupied,
another deck automatically advances to 4174, then 4175, and so on; the printed
URL and `--open` always use the selected port. Passing `--port PORT` is strict
and reports an error when that exact port is unavailable.

The server exposes only the unit's `webdeck/` tree (plus the live-reload
endpoint). Adjacent unit files such as `script.md`, `brief.md`, and
`workflow-state.yaml` are never reachable, and directory listings are off.

## Presenter controls

- **Next / previous:** arrow keys, `PageDown`/`PageUp`, `Space`, mouse wheel
  or trackpad scroll, and horizontal swipe on touch screens.
- **First / last slide:** `Home` / `End`.
- **Overview grid:** `O` or `Escape`; click a thumbnail to jump.
- **Full screen:** `F` (falls back to a pseudo-fullscreen on iPad Safari;
  `Escape` leaves it).
- **Appearance:** `T` or the **Appearance** control opens separate color-mode
  and presentation-style choices. Both preferences stay in the same browser
  and do not change deck data.
- **Viewer version:** the expanded controls strip shows a small `vX.Y.Z`
  label, so a served deck reveals the installed viewer and a frozen release
  reveals the viewer it was built with.

The presentation controls sit outside the fitted slide whenever the viewport
has spare space. At tighter aspect ratios they collapse to a small **Controls**
handle so they do not cover the footer. The desktop strip is hidden in full
screen, where the keyboard shortcuts remain active.

Browsers reserve `Escape` while using native full screen, so it cannot open the
overview directly. `O` and the always-visible fullscreen control bar still open
the overview. When `Escape` exits native full screen, lecturedeck opens the
overview automatically; press `F` when you want to leave full screen without
opening it.

### Serve-only figure adjustment

On a slide with one or more figures, press `G` while using `lecturedeck serve`
to enter geometry adjustment mode. Arrow keys nudge the selected figure,
`Shift`+arrow keys move it 10 px, `[` and `]` scale it, `Tab` selects another
figure, and `R` restores that figure's source values. The on-screen panel shows
a pasteable result such as `shift: [4, -12], scale: 1.08`; `G` or `Escape`
leaves adjustment mode. These controls never write files and are absent from
static releases.

Store an accepted adjustment on the figure itself:

```json
{
  "id": "example-figure",
  "src": "assets/example.png",
  "alt": "Example figure",
  "shift": [4, -12],
  "scale": 1.08
}
```

The viewer applies these values in both served decks and static releases.
Legacy `slides.js` figures use the same fields as JavaScript object literals.

Each discrete wheel click turns exactly one slide with no lock-out, so rapid
clicking pages quickly. Trackpad glides turn one slide per gesture and absorb
the inertia tail. Wheel navigation ignores pinch-zoom gestures and stays
inactive over videos and embedded interactives so their own scrolling keeps
working.

## Embedded interactive illustrations

An interactive page is a local, self-contained asset embedded by iframe:

```json
{
  "id": "transformation-demo",
  "title": "Explore the transformation",
  "chrome": false,
  "interactive": {
    "src": "assets/transformation/index.html",
    "title": "Interactive transformation"
  }
}
```

The full-canvas mode retains touch-friendly Previous, Full screen, and Next
controls above the iframe. An embedded page may request deck navigation with:

```js
parent.postMessage({type: "lecturedeck:navigate", direction: 1}, "*");
```

Static Bokeh exports should use `bokeh.resources.INLINE`. Plotly exports should
bundle Plotly JavaScript (`include_plotlyjs=True` or an equivalent local file),
not use `"cdn"`. Any other interactive runtime must also be vendored inside the
unit's `webdeck/assets/` tree before `lecturedeck check` can pass. An
interactive page may split itself into further local files — stylesheets,
images, and static ES modules — and validation follows those references from
the file that declares them.

## Local video excerpts

Video slides use local, rights-cleared media under the unit's `webdeck/assets/`
tree. The runtime loads metadata only until the presenter presses play, does not
autoplay in overview, and leaves the video's keyboard and touch controls alone.

```json
{
  "id": "hamilton-leap",
  "title": "Hamilton's leap",
  "claim": "Three-dimensional rotations require four parameters.",
  "video": {
    "src": "assets/hamilton-bridge-excerpt.mp4",
    "type": "video/mp4",
    "poster": "assets/hamilton-bridge-poster.jpg",
    "title": "Hamilton and the quaternion rule",
    "caption": "A short classroom excerpt.",
    "source": "Video creator",
    "originalUrl": "https://www.youtube.com/watch?v=example",
    "originalLabel": "Watch the original video",
    "tracks": [
      {
        "src": "assets/hamilton-bridge-en.vtt",
        "kind": "captions",
        "srclang": "en",
        "label": "English",
        "default": true
      }
    ]
  }
}
```

`sources: [{src, type}, ...]` may replace the single `src`/`type` pair when a
unit provides multiple local encodings. A source link may be remote because it
is ordinary attribution; every playable source, poster, and caption track must
remain local so `lecturedeck check` and static releases work offline.

## Public-repository boundary

This repository is intentionally generic and public. Do not commit:

- lecture scripts, slides, textbook extracts, figures, citations, or course data;
- student, grading, roster, or assessment material;
- session transcripts, agent logs, local handoffs, or private directions;
- absolute local paths, credentials, tokens, build caches, or generated releases.

Course-specific work belongs in the consuming course repository. This project
tracks only reusable runtime code, tests, durable public workflows, and release
history.

## Development

```powershell
& "$env:USERPROFILE\.venvs\lecturedeck\Scripts\python.exe" -m unittest discover -s tests -v
& "$env:USERPROFILE\.venvs\lecturedeck\Scripts\python.exe" -m ruff check src tests
& "$env:USERPROFILE\.venvs\lecturedeck\Scripts\python.exe" -m compileall -q src tests
```

The test run includes a Chromium smoke suite for the presenter contract:
both data-loading paths, navigation, wheel input, overview, fullscreen,
theme, media attributes, iframe interaction, and the geometry-adjust guards.
It requires the optional Playwright dev dependency plus a one-time browser
download, and is skipped automatically when either is absent:

```powershell
& "$env:USERPROFILE\.venvs\lecturedeck\Scripts\python.exe" -m pip install -e ".[dev]"
& "$env:USERPROFILE\.venvs\lecturedeck\Scripts\python.exe" -m playwright install chromium
```

The smoke suite asserts mechanical behavior only. Whether a slide is too
dense or visually wrong remains a human judgment made by presenting real
decks; the runtime itself stays Python-standard-library-only.

See `AGENTS.md` and `.agents/commit-culture.md` for the public development,
versioning, privacy, and release gates.
