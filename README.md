# lecturedeck

`lecturedeck` is a small, filesystem-first server and scaffold for self-contained
web lecture presentations. It keeps the reusable runtime separate from course
content: this repository contains the generic server, browser shell, validation,
and tests; each course repository owns its scripts, figures, citations, and
interactive exports.

The runtime uses only Python's standard library plus local HTML, CSS, and
JavaScript. Checked release bundles work offline and do not require a CDN.

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

## Course repository contract

A consuming course repository keeps presentation units under:

```text
Studio/work/presentations/<unit>/
  brief.md
  script.md
  workflow-state.yaml
  webdeck/
    slides.js
    deck.css
    assets/
```

`slides.js` and `assets/` are the deck content. `deck.css` is an optional,
unit-owned override loaded after the installed viewer styles. While serving,
`index.html`, `lecturedeck.css`, and `lecturedeck.js` come from the installed
package; `release` materializes them into the static bundle. Only `webdeck/`
content is exposed or copied, and `lecturedeck` never reads adjacent lecture
scripts, source books, agent notes, or other course materials.

Legacy units may retain local copies of any viewer file. Those files override
the installed package while serving and are preserved in releases, so migration
to content-only units can happen deliberately.

## Commands

Run from a course repository, or pass `--repo PATH` explicitly:

```text
lecturedeck init <unit> --title "Presentation title"
lecturedeck refresh <unit>
lecturedeck check <unit>
lecturedeck serve <unit> --livereload
lecturedeck release <unit> --output <new-output-directory>
```

`init` creates `slides.js`, `deck.css`, and an `assets/` directory without
overwriting existing files. `check` validates the content against the installed
viewer and rejects missing files, references that escape `webdeck/`, and
external runtime dependencies. Normal citation links in
`<a href="https://...">` remain allowed. `release` validates first, freezes the
installed viewer into one self-contained static bundle, and refuses to
overwrite its destination.

`refresh` remains a migration aid for legacy units. It updates local copies of
`lecturedeck.css` and `lecturedeck.js` to the installed runtime. A snapshot
matching any published runtime version is replaced; a file with local
modifications is kept and reported until `--force`, and `slides.js`,
`index.html`, `deck.css`, and `assets/` are never touched. Content-only units
report the viewer files as missing because they already use the installed
viewer. Review any resulting diff in the course repository afterward.

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
- **Theme:** `T` or the **Light theme**/**Dark theme** control; the selection
  stays on the same browser.

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

```js
{
  src: "assets/example.png",
  alt: "Example figure",
  shift: [4, -12],
  scale: 1.08
}
```

The viewer applies these values in both served decks and static releases.

Each discrete wheel click turns exactly one slide with no lock-out, so rapid
clicking pages quickly. Trackpad glides turn one slide per gesture and absorb
the inertia tail. Wheel navigation ignores pinch-zoom gestures and stays
inactive over videos and embedded interactives so their own scrolling keeps
working.

## Embedded interactive illustrations

An interactive page is a local, self-contained asset embedded by iframe:

```js
{
  title: "Explore the transformation",
  chrome: false,
  interactive: {
    src: "assets/transformation/index.html",
    title: "Interactive transformation"
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
unit's `webdeck/assets/` tree before `lecturedeck check` can pass.

## Local video excerpts

Video slides use local, rights-cleared media under the unit's `webdeck/assets/`
tree. The runtime loads metadata only until the presenter presses play, does not
autoplay in overview, and leaves the video's keyboard and touch controls alone.

```js
{
  title: "Hamilton's leap",
  claim: "Three-dimensional rotations require four parameters.",
  video: {
    src: "assets/hamilton-bridge-excerpt.mp4",
    type: "video/mp4",
    poster: "assets/hamilton-bridge-poster.jpg",
    title: "Hamilton and the quaternion rule",
    caption: "A short classroom excerpt.",
    source: "Video creator",
    originalUrl: "https://www.youtube.com/watch?v=example",
    originalLabel: "Watch the original video",
    tracks: [
      {
        src: "assets/hamilton-bridge-en.vtt",
        kind: "captions",
        srclang: "en",
        label: "English",
        default: true
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

See `AGENTS.md` and `.agents/commit-culture.md` for the public development,
versioning, privacy, and release gates.
