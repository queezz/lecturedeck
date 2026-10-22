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
  pacing-records/
```

`deck.json` and `assets/` are the deck content. `deck.css` is an optional,
unit-owned override loaded after the installed viewer styles. While serving,
`index.html`, `lecturedeck.css`, and `lecturedeck.js` come from the installed
package; `release` materializes them into the static bundle. Only `webdeck/`
content is exposed or copied, and `lecturedeck` never reads adjacent lecture
scripts, source books, agent notes, or other course materials.
`pacing-records/` is the only place `lecturedeck` writes: it is machine-written
by `serve` on scheduled teaching dates (see
[Lecture pacing records](#lecture-pacing-records)) and holds no student data.

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
  `source`, `accent`, `className`, `chrome`, `appendix`, `formula`, and one
  content block among `figure`/`figures`, `cards`, `interactive`, or `video`.
  `body`, `quote`, and captions hold compiled HTML; `formula.mathml` holds
  native MathML.
- Slide HTML may mark elements with `data-step="N"`, and figures, cards, an
  object `formula`, `interactive` and `video` accept a numeric `step`, to
  reveal a slide piece by piece; see
  [Step-by-step reveals](#step-by-step-reveals).
- A figure (`figure`, or an item of `figures`) may carry `hotspots`: points
  of its picture with a popup, such as the people in a group photograph;
  see [Photo hotspots](#photo-hotspots).
- `eyebrow` overrides the current part label on that slide. Omit it or leave
  it empty to use the part label. Optional `beat` is author metadata only;
  it is accepted in source data but never shown to the audience.
- `appendix: true` on one slide marks where backup material starts. Slides
  before it count against the main total (`21 / 46` in the counter and
  footer); that slide and every later one is numbered `B1`, `B2`, …. The
  counter and footer add the backup total (`B4 / 92`, never `B4 / B92`), and
  screen readers hear "Backup slide B4 of 92". The overview and the pacing
  report show the bare `B4`. Navigation and
  `#/N` deep links keep the raw zero-based position. Appendix frames carry
  `data-appendix="true"` and the body gains `in-appendix` while one is shown,
  so `deck.css` can style them. `check` requires a boolean and rejects more
  than one `appendix: true`; without it, numbering stays plain `i / N`.
- `review: true` marks a slide as part of a homework review that a meeting
  opens with (since 0.28.0). Review slides are numbered `H1`, `H2`, … in deck
  order and leave the main count, so the lecture's own slides read `1 … N`
  wherever the review sits: title `1 / 41`, the review `H1 / 38` … `H38 / 38`,
  then the first lecture slide `2 / 41`. Screen readers hear "Review slide H4
  of 38"; the overview and the pacing report show the bare `H4`. Review frames
  carry `data-review="true"` and the body gains `in-review` while one is
  shown, so `deck.css` can give them their own shade. `check` requires a
  boolean and rejects `review: true` on or after the appendix slide. A deck
  without the marker numbers exactly as before.
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
- Group a fraction and its parentheses in the same `mrow`, then apply a
  power to that entire group with `msup`. Check the result in the target
  browser: parentheses outside the fraction's group may stay small. An
  inline slash such as `(a/b)²` is a readable alternative for a short factor.
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

## Step-by-step reveals

A slide can guide attention through its content one piece at a time instead
of showing every block at once. Give any element of the slide's HTML (claim,
body, quote, formula MathML and gloss, card text, captions, title, source)
the attribute `data-step="N"`, where `N` is a positive integer. Objects the
viewer draws itself take a numeric `step` field instead: `figure`, each item
of `figures`, each card, an object `formula`, `interactive` and `video`.
Content without a step is always on screen. Elements that share a number
appear together.

```json
{
  "id": "one-reading-path",
  "title": "One reading path",
  "claim": "The claim is on screen from the start.",
  "body": "<p data-step=\"1\">Then this sentence appears.</p><p data-step=\"2\">These two</p><p data-step=\"2\">appear together.</p>",
  "figure": {
    "src": "assets/diagram.png",
    "alt": "The diagram the sentences lead to",
    "step": 3
  }
}
```

- **Next and Previous.** Next (`→`, `↓`, `PageDown`, `Space`, the Next
  control, a wheel notch, a swipe, a clicker, or an interactive page's
  `lecturedeck:navigate` message with direction `1`) reveals the next step
  number still hidden. On a fully shown slide it advances, and the next slide
  opens with only its unstepped content. Previous hides the last step shown;
  on a slide with nothing revealed it goes back, and the previous slide
  arrives fully revealed, as it was left. `Shift` with an arrow, `PageDown`
  or `PageUp` moves by whole slides past the steps, for rewinding: the next
  slide opens bare, the previous one whole. While the overview is open,
  every press moves by whole slides.
- **Jumps.** A `#/N` deep link, an in-deck link and a choice in the overview
  open a slide with no steps shown. `Home` opens the first slide that way and
  `End` shows the last slide whole. Closing the overview without choosing
  another slide keeps the step you were on.
- **Address.** The address reads `#/N` while no step is shown and `#/N.k`
  once steps up to `k` are shown, so a reload or a live reload returns to the
  same step. `#/N.k` also works as a deep link or an in-deck link; a `k` past
  the last step shows the whole slide.
- **Layout and motion.** A hidden step keeps its place (it is made invisible,
  not removed), so nothing moves when it appears. A step that is the whole
  content of a box the viewer draws (a figure or video caption, the quote, a
  formula gloss item) takes that box with it, so no empty caption bar or
  gloss divider waits on screen. A step fades in over about a quarter of a
  second, or appears at once when the system asks for reduced motion. A
  hidden step is hidden from screen readers and cannot take keyboard focus
  (focus inside it, also inside an embedded page, leaves as it hides), and a
  video stepped back out of view is paused. A stepped `interactive` page
  loads when its step first appears, so an animation starts in front of the
  audience instead of running unseen; stepped back, it stays loaded.
- **What counts as a step.** A press reveals the next number among the
  steps the layout shows right now. A step `deck.css` does not display (one
  twin of a dark/light figure pair, a block dropped below some width) waits
  hidden and joins the count when it appears; switching the theme or
  resizing the window keeps the step on screen. A step nested in a later one
  (a caption numbered below its figure's `step`, an element inside a later
  element) cannot show first: it appears with the later step. A section
  slide's stepped title or eyebrow steps only that slide; the slides after it
  show it whole in their eyebrow.
- **Always whole.** The overview, `?print=1` and `lecturedeck pdf`, the
  narration skeleton, and printing a live page show every step. Opening the
  Appearance or Pacing dialog changes nothing on the slide behind it.
- **Counter and pacing.** The counter keeps counting slides. On a slide with
  steps, small dots under the page number in the slide's footer, and under
  the number inside the counter in the controls, show the steps shown
  (filled) and still to come (open). The dots take no room: the page
  number, the course name, the source line, the counter and the controls
  beside it keep the same place on every slide, with or without steps and
  at every step. The page number and the counter also keep the width of the
  deck's widest position, so nothing moves from 9 to 10 either. A
  `chrome: false` slide has no footer and shows only the counter's dots.
  Pacing records keep one visit per slide: revealing a step is not a slide
  change.
- **Checking.** `check` rejects a `step` or `data-step` that is not a
  positive integer (`0`, `"2"`, `1.5`, `01`, an empty attribute), and a step
  in content the slide never shows: the title, eyebrow or source of a
  `chrome: false` slide, the claim, formula, body or quote of a full-canvas
  interactive (`chrome: false`), or a block its layout does not draw. It
  also rejects a `data-step` in `meta.section` or `meta.opening`, which
  appear on many slides. Step numbers with a gap, such as 1 and 3, and a
  step nested in a later one only print a warning: each press still reveals
  the next number used.
- **Styling.** While a live slide has steps, its frame carries
  `data-step-count`, `data-step-shown` and `data-step-current`; hidden steps
  carry the class `step-hidden` and the most recently revealed ones
  `step-current`; the footer dots carry `step-cue`.
  [STYLE_GUIDE.md](STYLE_GUIDE.md) shows a `deck.css` example and how to
  order steps. Legacy `slides.js` decks use the same fields; `check` does
  not validate them.

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
lecturedeck serve
lecturedeck serve <unit> --livereload
lecturedeck serve --folder <presentations-directory>
lecturedeck serve --no-pacing-records
lecturedeck release <unit> --output <new-output-directory>
lecturedeck pdf <unit> --output <new-file.pdf>
lecturedeck narration <unit> [--outline] [--output <new-file>]
lecturedeck narration --deck <deck.json|webdeck|unit-folder> [--outline]
```

`init` creates `deck.json`, `deck.css`, and an `assets/` directory without
overwriting existing files. `check` validates the deck schema and the content
against the installed viewer; it rejects missing files, references that escape
`webdeck/`, and external runtime dependencies. References inside nested
interactive pages — their HTML, CSS `url()`/`@import` targets, and static
ES-module imports — resolve relative to the file that declares them and must
stay local. Normal citation links in `<a href="https://...">` remain allowed.
`check` also prints `WARNING:` lines for advice that does not fail it, such
as a gap in a slide's step numbers.
`release` validates first, freezes the installed viewer into one
self-contained static bundle, and refuses to overwrite its destination.

`pdf` validates first, starts a temporary localhost-only server, and prints
every slide through headless Chromium. The result has one 16:9 slide per page,
uses the light theme by default, and refuses to overwrite an existing file.
Pass `--theme dark` to preserve the dark presentation surface. Links between
slides (`#/N`) become jumps inside the PDF, and external links stay links.
Videos export their poster (or a labeled placeholder) and interactive iframes
export a labeled placeholder, since a PDF cannot retain their live behavior.

`narration` validates like `check` and prints a Markdown skeleton of what the
audience sees, for translation into spoken text: chapters are the only `##`
headings, each slide opens with `<!-- slide: ID -->`, `#/N` links become
`<!-- nav: … -->` notes, MathML is linearized beside its source, and blocks the
layout hides are left out. Line 1 carries the deck's sha256 (BOM and CRLF
normalized) so stale narration can be detected. `--outline` prints the same
structure as JSON (`schema: 1`) with labels `12` or `B3`. Output is UTF-8 with
LF on any console; `--output` only creates a new file outside `webdeck/`.
Legacy `slides.js` is read only when it assigns a plain JSON literal whose ids
are lowercase kebab-case, as in `deck.json`. Ids and unit names are emitted as
authored, including any `--`; a unit name containing `-->` or a line break is
refused. Piping the output into `head` or a pager ends it without a traceback.

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

On a unit's scheduled teaching dates, `serve` saves pacing records to
`<unit>/pacing-records/`, and only for a browser on the serving computer (see
[Lecture pacing records](#lecture-pacing-records)). `--no-pacing-records`
switches this off. Serve directly, not behind a reverse proxy, SSH tunnel or
port forwarder: proxied requests never save, and a forwarder on the same
computer is unsupported.

Omit the unit to open a searchable selector for the current course's
`Studio/work/presentations/` folder. The selector discovers only immediate
child directories containing `webdeck/deck.json` or legacy
`webdeck/slides.js`. JSON decks use `meta.title` and optional `meta.section`.
Use `meta.selectorGroup` to override the inferred Lectures, Homeworks, or Extras
group, and `meta.selectorHero` with a path under `assets/` to add a scannable
card image. Legacy decks fall back to the unit directory name. To select from
an arbitrary presentations folder instead, run `lecturedeck serve --folder
PATH`. A unit may also be named with `--folder` to serve that one deck directly.

The selector exposes every chosen unit at its own `/decks/<unit>/webdeck/`
route. It reads selector labels only from `deck.json`, never executes deck data
to build the list, and preserves the same boundary as single-deck serving:
files beside `webdeck/` are not reachable.

The commands above describe foreground CLI use. Agent entry points and
background previews should use the local service manager (for Fleet, the
course's `lab` alias). Test with scratch `LAB_CONFIG`, `LAB_RUNTIME_ROOT`, and
`LAB_LOG_ROOT`, a disposable sample deck, an explicit free `--port`, and
`--no-pacing-records`.
Stop through `lab stop` and verify the listening port is free; on Windows,
stopping only a launcher PID can leave its Python child serving. `init`
creates deck content, not a course `AGENTS.md` or service entry point.

Without `--port`, the first server uses port 4173. If that port is occupied,
another deck automatically advances to 4174, then 4175, and so on; the printed
URL and `--open` always use the selected port. Passing `--port PORT` is strict
and reports an error when that exact port is unavailable.

The server exposes only the unit's `webdeck/` tree, plus the live-reload
endpoint and a write-only pacing endpoint that accepts records from a browser
on the serving computer. Records are never served. Adjacent unit files such as
`script.md`, `brief.md`, and `workflow-state.yaml` are never reachable, and
directory listings are off.

## Presenter controls

- **Next / previous:** arrow keys, `PageDown`/`PageUp`, `Space`, mouse wheel
  or trackpad scroll, and horizontal swipe on touch screens. On a slide with
  [step-by-step reveals](#step-by-step-reveals) they show or hide one step
  before they change slide; `Shift` with the arrow and page keys moves by
  whole slides.
- **Mobile review:** tap the small gear or swipe up on a slide to open the
  touch menu. Overview, fullscreen and the remaining controls are available
  there; Close menu or a downward swipe dismisses it. Horizontal swipes page
  slides. Overview scrolling, pinch zoom, media and interactive controls do
  not page the deck. Overview keeps a Close overview button within reach.
- **First / last slide:** `Home` / `End`. `Home` opens the first slide with
  no steps shown; `End` shows the last slide whole.
- **Overview grid:** `O` or `Escape`; click a thumbnail to jump.
- **Full screen:** `F` (falls back to a pseudo-fullscreen on iPad Safari;
  `Escape` leaves it).
- **Appearance:** `T` or the **Appearance** control opens separate color-mode
  and presentation-style choices. Both preferences stay in the same browser
  and do not change deck data.
- **Laser pointer:** `L` or the **Laser** control toggles a glowing dot that
  follows the pointer and hides the arrow over the slide. The dot takes the
  current slide's accent colour and keeps a white core so it stays visible on
  any figure. It also tracks over interactive animations: while the laser is
  on they let the mouse through, so press `L` again to click or drag one. It
  switches off when the overview opens, hides while the pointer is outside the
  window, and never appears in a PDF export.
- **Photo viewer:** a click on any photo or figure of the slide opens it
  over the whole window, with big **Brightness**, **Contrast** and **Zoom**
  controls for a projector that eats contrast; a video opens from a small
  expand control on its corner. **Use on all photos** applies the same
  correction to every photo and video of the deck. Any paging or clicker
  key only closes it. See [Photo viewer](#photo-viewer).
- **Photo hotspots:** on a figure with `hotspots`, faint rings mark every
  hotspot while the pointer is over the picture; hovering (or tapping) a
  ring shows its popup, on the slide and in the photo viewer. `H` turns the
  hint rings off and on for the whole deck. See
  [Photo hotspots](#photo-hotspots).
- **Deck selector:** the home button returns to the selector when the deck was
  opened from one; it stays hidden for a directly served deck.
- **Viewer version:** the expanded controls strip shows a small `vX.Y.Z`
  label, so a served deck reveals the installed viewer and a frozen release
  reveals the viewer it was built with.

The presentation controls sit outside the fitted slide whenever the viewport
has spare space. At tighter aspect ratios they collapse to a small gear button
so they do not cover the footer. The gear remains available in full screen,
where keyboard shortcuts also remain active. Full screen also expands the live
slide canvas into a display's spare dimension, so 16:10, 3:2, and ultrawide
screens are filled without stretching or cropping authored content. Windowed
slides, overview thumbnails, and PDF pages remain 16:9.

Browsers reserve `Escape` while using native full screen, so it cannot open the
overview directly. `O` and the always-visible fullscreen control bar still open
the overview. When `Escape` exits native full screen, lecturedeck opens the
overview automatically; press `F` when you want to leave full screen without
opening it. While any dialog (Appearance, Pacing, the photo viewer) is open,
keys, the wheel, the trackpad and swipes belong to the dialog: they scroll it
and never page the deck, and `Escape` only closes the dialog.

### Photo viewer

A projector eats contrast. A click or tap on a content image of the live
slide opens it in an overlay that fills the window, scaled to fit, with big
plain controls along the bottom edge: brightness `−`/`+`, contrast `−`/`+`,
zoom `−`/`+`, **Use on all photos**, **Reset** and **Close**, each value
shown as it changes (`Brightness 130 %`). The zoom-in cursor marks every
image that opens: figures, figure grids, and images in slide HTML such as a
photo card. A click on a `<video>` still plays and pauses it, so a video
opens from a small expand control on its top right corner instead; the
viewer plays a copy of it from the moment the slide's video had reached,
and closing leaves the slide's video paused where the viewer left it. (The
copy seeks only where the server allows it: Chromium cannot seek a video
from `lecturedeck serve`, which answers no HTTP range requests, so there it
starts from the beginning; Firefox and Zen seek either way.)

Nothing else opens: interactive pages, the chrome, the overview, an image
inside a link, button, summary or label (the control wins), an image
formula (MathML, `.formula`, or an image with a `math-…` class such as
`img.math-display`), and anything inside an element marked
`data-photo="off"`. The viewer shows a picture as the slide does: it keeps
a filter that `deck.css` gives it (an invert for the dark theme, say) and,
behind a transparent drawing, the slide's background, so dark ink stays
readable on the black stage.

| Key | In the photo viewer |
|---|---|
| `B` / `Shift`+`B` | brightness up / down by 10 % (50–300 %) |
| `C` / `Shift`+`C` | contrast up / down by 10 % (50–300 %) |
| `+` / `-` (also `=` / `_`) | zoom in / out by √2 (1× fit to 8×) |
| `0` | reset brightness, contrast and zoom |
| `A` | toggle **Use on all photos** |
| `L` | laser pointer, which keeps tracking over the photo |
| `H` | hint rings of [photo hotspots](#photo-hotspots), as on the slide |
| `Escape`, `PageDown`, `PageUp`, arrows, `Space`, `Home`, `End` | close |

The keys were free in the viewer and stay local to the overlay. A paging or
clicker key only closes the photo, on exactly the slide and step it opened
from: it never pages or steps, so the presenter can never get stuck in the
overlay or skip content. **Close** and a click on the dark backdrop around
the photo close it too. Every other deck shortcut (`O`, `F`, `T`, `G`)
waits behind the photo. In native full screen the browser takes the first
`Escape` to leave full screen; the viewer then closes the photo too, and
does not open the overview.

**Zoom.** The mouse wheel, a trackpad scroll or a pinch zooms around the
cursor; dragging pans, and the picture never leaves a gap at an edge; a
double-click toggles between fit and 2× at the point clicked; two fingers
pinch on a touch screen. A video keeps its own clicks and double-click
(the player's full screen), and pans only while zoomed.

**Remembered per deck.** The last brightness and contrast, and **Use on all
photos**, are kept in this browser's local storage per deck (its address and
title), so the next photo opens with the same correction. Zoom always starts
at fit. Without local storage everything still works for the open page and
nothing is remembered.

**Use on all photos.** The toggle, in the overlay and as a checkbox in the
**Appearance** dialog, applies the viewer's brightness and contrast with CSS
`filter` to every content photo and video of the slides and the overview
thumbnails, so the presenter corrects the whole deck for the room once at
the start of class. It never touches a drawn SVG figure (an `.svg` image),
a formula, the chrome, print or a PDF export. The rule is as weak as one
class, so a filter that `deck.css` sets on an image keeps priority; keep a
raster drawing out of the correction with `data-photo="off"` in slide HTML
or a `deck.css` rule such as `[data-figure-id="drawn-field"] img { filter:
none; }`.

**Nothing moves.** The overlay is a modal dialog above everything, sized
from the viewport. The page counter, step dots, footer and controls strip
keep their boxes to the pixel while it opens, changes and closes, and a
video's expand control sits out of the slide's layout. Pacing records count
the time in the viewer as time on its slide: opening it is no slide change
and no pause. Print pages and PDF exports contain no viewer.

### Photo hotspots

Something a slide program cannot do: point at a person in a group photo and
get who they are. A figure, a single `figure` or an item of `figures`, may
carry `hotspots`:

```json
"figure": {
  "src": "assets/solvay-1927.jpg",
  "alt": "The participants of the fifth Solvay conference, 1927",
  "hotspots": [
    {"x": 0.2025, "y": 0.389, "r": 0.017, "label": "Max Planck",
     "html": "<strong>Max Planck</strong> (1858–1947)<br>Energy quanta, 1900; Nobel 1918."}
  ]
}
```

- `x` and `y` give the centre as fractions of the picture's natural width
  and height (the image file as served, so measure on the cropped file);
  both lie in [0, 1]. `r` is the radius as a fraction of the natural width,
  0 < `r` ≤ 0.5.
- `label` is required plain text: the hotspot's accessible name, and the
  popup when there is no `html`.
- `html` is the optional popup body, slide HTML: inline MathML and links
  work. It holds no `data-step`; a popup is never stepped. Keep it to two
  or three short lines: the popup is 22 px text, the captions' size, at
  most 440 px wide on the 1280×720 stage.
- `check` rejects anything else: an empty list, a missing or blank label,
  a coordinate outside its range, an unknown key. Add `"requires": ">=0.27"`
  so an older viewer refuses the deck rather than ignoring the hotspots.

On the live slide the rings lie exactly on the picture as the browser draws
it: its content box, `object-fit` and `object-position`, a `deck.css`
`width`, `max-height`, padding or border, and the figure's `shift` and
`scale`; they follow full screen, the theme and a late font. They stay
invisible until the pointer is over the picture; then a faint ring marks
every hotspot, the presenter's hint of where to point. The ring under the
pointer shows at full strength with its popup beside it (on the side with
more room, else below or above), always inside the slide; the pointer can
move into the popup to follow a link. A click on a ring opens the photo
viewer like a click on the picture. On a touch screen, which has no hover,
the faint rings always show; a tap on a ring shows its popup, a second tap
or a tap anywhere else hides it. A keyboard reaches the rings with `Tab`
(the popup shows on focus) and `Enter` toggles it; paging keys still page.

The [photo viewer](#photo-viewer) lays the same rings over its copy. They
follow zoom and pan exactly, sit outside its brightness and contrast filter,
and show their popups the same way, in the viewer's own dark colors, with
the text as large as on the slide (never under 22 px). Every viewer key,
the clicker's close, double-click zoom (also on a ring) and the laser work
as without hotspots.

| Key | Photo hotspots |
|---|---|
| `H` | hint rings off / on for the whole deck, on the slide and in the viewer |

`H` was free. With the rings off, nothing marks the hotspots, but the one
under the pointer still shows its ring and popup, so the presenter can keep
the photo clean and still name a face. Turned on, every ring shows for a
moment, even without the pointer over the photo. The switch is also a
checkbox in the **Appearance** dialog on a deck with hotspots, and it lasts
for the browser tab (session storage), so a reload keeps it and a new
lecture starts with the rings on.

**Nothing moves.** The rings and the popup are children of the slide frame
(the viewer's stage), positioned out of the layout; the figure card itself
is never restyled. A stepped figure's rings wait hidden with it and fade in
with it; a popup closes when its figure steps out of view. The overview,
print pages and PDF exports show the photo without rings or popups.

`deck.css` hooks: `.hotspot-layer` (one per figure, with the figure's
`data-figure-id`), `.hotspot` (a ring; `.is-active` with its popup),
`.hotspot-popup` (`#hotspot-popup-slide` on the slide,
`#hotspot-popup-viewer` in the viewer), `body.hotspot-rings-off`, and the
ring colors `--hotspot-ring` and `--hotspot-active`, set on the layer:

```css
/* Darker hint rings on one pale photo. */
.hotspot-layer[data-figure-id="solvay-1927"] { --hotspot-ring: rgba(29, 32, 33, .9); }
```

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

Direction `1` acts as the Next key and `-1` as Previous, so on a slide with
step reveals the page reveals or hides a step before it changes slide. A
page may forward its own `Home` and `End` keys as
`{type: "lecturedeck:navigate", to: "first"}` or `to: "last"`; they act as
the deck's `Home` (the first slide, no steps shown) and `End` (the last
slide whole).

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
A small expand control on the video's top right corner opens it in the
[photo viewer](#photo-viewer), for brightness, contrast and zoom.

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
both data-loading paths, navigation, step-by-step reveals, wheel input,
overview, fullscreen, theme, media attributes, iframe interaction, the
geometry-adjust guards, and the pacing recorder, report and same-computer
saving.
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

### Repository selector default

To select a teaching collection for plain `lecturedeck serve` and managed
restarts, add `lecturedeck.toml` at the repository root:

```toml
[selector]
folder = "Studio/release/teaching-selector"
```

The path must stay inside the repository. Explicit `--folder` takes precedence;
named-unit commands continue to use `Studio/work/presentations`.


### Scheduled presenter clock

Add `presentation-time.json` to a unit's `webdeck/` to show the current time
and remaining scheduled minutes in the top-right corner:

```json
{"start": "09:00", "end": "10:30", "timeZone": "Europe/London"}
```

The clock uses today's wall-clock session in that timezone, rather than a
stopwatch started when the deck opens. Before the start it shows the start
time; after the end it shows minutes overdue. Clock in the controls menu
hides/shows it and remembers the preference in this browser. It remains visible
in fullscreen and interactive slides, is hidden in overview and print, and
requires no network service. Omit the file to keep the clock disabled.


Add an optional `dates` array of ISO teaching dates to that file, for example
`"dates": ["2026-01-01"]`, to record slide pacing automatically on those dates.
Nothing needs pressing; see [Lecture pacing records](#lecture-pacing-records).

### Lecture pacing records

**Window and phases.** On a listed date the recorder runs from 30 minutes
before the slot's start to 60 minutes after its end (clipped to that day)
while the page is visible, the overview and every dialog are closed, and a
slide is shown. Opening a deck outside that window records nothing. Each
visit is tagged `before` (earlier than the start), `slot` (start to end) or
`after` (the end or later); a visit crossing a boundary is split exactly at
it. Visits are unbroken spans, so `startedAt + durationMs` is when a visit
ended. The recorder samples once a second and credits nothing across a gap
over 10 s or a disagreement over 2 s between the wall clock and the monotonic
clock (sleep, a closed lid, frozen timers, a clock step); such a gap is logged
as a `suspended` or `clock` pause. Time in the overview, the pacing report,
another dialog or a hidden tab is a pause with that reason (`overview`,
`report`, `dialog`, `hidden`); a gap ends an overview, report or dialog pause
too, while a hidden tab's pause spans it (browsers slow a hidden tab's
timers). Pauses are not slide time. The photo viewer is no pause: time in it
counts for the slide it was opened from.

**Where records land.** While `lecturedeck serve` delivers the deck to a
browser on the serving computer, each page load's recording (a *segment*)
saves itself beside `webdeck/`, never inside it:

```text
<unit>/pacing-records/<YYYY-MM-DD>_<HHMM>_<unit>_<segment>.json
Studio/work/presentations/lecture-02/pacing-records/2026-01-13_0858_lecture-02_3fa9c1d27b0e.json
```

`<HHMM>` is when the segment opened (schedule time zone), `<unit>` is the
unit folder name made safe for a file name, and `<segment>` is 12 random hex
digits drawn per page load. A reload, a live reload or another tab starts a
new segment, and a segment rolls over to a new file past 48 KiB, so a lecture
usually gives one to four files that never overwrite each other. The page
saves 2 s after a slide change, at once at a phase boundary or a pause, every
15 s while a segment is open (recording or paused), and with `keepalive` when
the tab is hidden or closed.
Every save carries the whole segment with a rising `rev`; the server rebuilds
it from whitelisted fields, writes it atomically, keeps only a higher revision
and never deletes a file. One segment (schema 2) looks like:

```json
{"schema": 2, "kind": "lecturedeck-pacing-segment", "segment": "3fa9c1d27b0e",
 "rev": 412, "unit": "lecture-02", "path": "/decks/lecture-02/webdeck/",
 "deck": "Lecture 2", "viewer": "0.24.0", "date": "2026-01-13", "opened": "0858",
 "timeZone": "Europe/London",
 "slot": {"start": "09:00", "end": "10:30",
          "startAt": "2026-01-13T09:00:00.000Z", "endAt": "2026-01-13T10:30:00.000Z"},
 "window": {"before": 30, "after": 60,
            "from": "2026-01-13T08:30:00.000Z", "to": "2026-01-13T11:30:00.000Z"},
 "slides": {"<slide id>": {"number": 12, "label": "12", "title": "…", "section": "…"}},
 "visits": [{"slideId": "<slide id>", "startedAt": "…Z", "durationMs": 61234,
             "phase": "slot"}],
 "pauses": [{"startedAt": "…Z", "durationMs": 17000, "why": "overview"}],
 "fullscreenMs": 4012000,
 "savedAt": "…Z", "savedBy": {"host": "<computer name>", "lecturedeck": "0.24.0"}}
```

Backup slides carry `"backup": true` and labels `B1`, `B2`, …; review
slides carry `"review": true` and labels `H1`, `H2`, …. A record
holds only slide ids, numbers, labels, titles and sections, visit and pause
times, time in full screen, the deck title, path and schedule, and the saving
computer's host name and lecturedeck version: no student data and nothing
typed into the page.

**Same computer only.** The server injects its small saving script, and
accepts a record, only for a browser on the serving computer: a loopback
connection (or one from the server's own address), a `localhost` or
IP-literal `Host` on the server's port, a same-origin JSON POST with an exact
`Origin` and the `X-Lecturedeck-Pacing` header, and no proxy headers. The
date must be listed in that unit's `presentation-time.json`. Open the deck at
`http://127.0.0.1:<port>`; under a host name or `.local` address it records in
the browser only. LAN viewers, other devices, static releases and PDF exports
never receive write code, and `pacing-records/` is never served, checked,
released or watched for live reload. Automated browsers (`navigator.webdriver`
true, as under Playwright) save nothing; any other browser showing a
scheduled deck inside the window writes a segment of its own, which
`savedBy.host` identifies. `--no-pacing-records` switches disk saving off,
for example on scratch instances.

**The report.** Pacing in the controls menu opens this browser's recordings
of the deck, with a date menu when it holds more than one date. The header
(Close) and the footer (status and Export JSON) stay on screen; only the
report scrolls. It leads with the last main-slide change and the signed
overrun against the scheduled end, then time in the slot, before it, after
it and off slides; notes on overlapping windows, merged recordings (page
reloads, rollovers to a new file, other windows) and migrated records; a
section table; the main slides not shown; and collapsed per-slide and
timeline tables. The footer says where the record went: `Saved to disk` with
the file name; `Disk saving ready on this computer` before class, noting any
older recordings this server will not take (another unit, a date no longer
scheduled; they stay in the browser); why it is saved in this browser only
(an older server that needs `lecturedeck serve` restarted, saving switched
off, another computer, a non-local address, a static copy, an automated
browser); older recordings still being retried; or that saving is failing,
retried after 5, 10, 20 and 40 s and then every 60 s. Another unit's or an
unscheduled date's leftovers never stop the open deck from saving. While
recording, the Pacing button's
dot is green when saving to disk, gold in this browser only and red when
saving fails. Export JSON downloads `<date>_<HHMM>_<unit>_export.json`
(`"kind": "lecturedeck-pacing-export"`) with the derived summary and every
segment.

**Before class.** After upgrading, restart `lecturedeck serve`, open any
scheduled deck at the address you present from, and check that Pacing reads
"Disk saving ready on this computer".

**Journal, recovery and older records.** Every second is also kept in this
browser's `localStorage` (`lecturedeck-pacing2:<path>:<date>:<segment>`).
After a crash, a killed browser or a server restart, the next page load of any
deck at the same origin uploads whatever the disk is missing. Static releases
and `file://` copies record in the browser only and keep Export JSON. Records
from viewers 0.20–0.23 (`lecturedeck-pacing:<path>:<date>`, schema 1) are
converted once into migrated segments (`"migratedFrom": 1`: slot time only,
no pauses, `fullscreenMs` null) and uploaded to their own unit; the old keys
are kept. A schema-1 record whose slot has not ended yet is left until it
has, since a tab still running an older viewer may be writing it. The upload
script refuses a body over 256 KiB itself (413), as the server would.

**Derived measures (for agents).** Merge the segments of one host for a date
(`savedBy.host`; a meeting that shows several decks writes into each unit's
folder, so merge across units too). First follow each window through its
segments, in order of first instant: a segment whose first instant is
another's last instant continues it (a rollover); any other segment is a page
load (a reload, a new tab, the deck opened again). Within a window, a visit
changes slide when its slide differs from the window's previous visit; the
first visit of a page load does not. A visit on the previous visit's slide
that starts where that one ended (a phase split, a rollover), or after a
`suspended` or `clock` pause covering the gap, keeps the window's last
slide-change time; any other visit sets it to its own start. Where visits
from different segments overlap, each moment counts once, for the window
whose last slide change is latest (then the later visit start), and the
overlap is reported. On the merged visits:

- An arrival is a merged piece whose slide differs from the previous piece's.
  A slide change is an arrival where its own visit starts and changes slide:
  opening a page and splits at phase boundaries, gaps and rollovers are not
  slide changes. Started is the first slide change.
- The last main-slide change is the latest slide change to a non-backup
  slide other than the last main slide shown, so coming back from the backup
  to the slide shown before it does not count; the overrun is that time
  minus the scheduled end, signed. Leaving the closing slide up during
  questions, paging the backup, or opening the deck again after class to
  read the report does not inflate it. On screen until, the end of the last
  visit, is reported separately. The report shows the overrun in whole
  seconds, floored like the wall times beside it.
- Time before, in and after the slot sums visit time by phase. Off slides in
  the slot is the slot length minus time in it, split into paused (by reason)
  and untracked (deck closed, crashed or asleep).
- The furthest main slide reached and the main slides never shown are
  measured against the current deck. Sections report when they were first
  entered, slides shown, and time in and outside the slot; all backup slides
  form one row.
