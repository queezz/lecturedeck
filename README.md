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
    index.html
    lecturedeck.css
    lecturedeck.js
    slides.js
    assets/
```

Only `webdeck/` is served or copied into a static release. `lecturedeck` never
reads adjacent lecture scripts, source books, agent notes, or other course
materials.

## Commands

Run from a course repository, or pass `--repo PATH` explicitly:

```text
lecturedeck init <unit> --title "Presentation title"
lecturedeck check <unit>
lecturedeck serve <unit> --livereload
lecturedeck release <unit> --output <new-output-directory>
```

`init` creates the four runtime files and an `assets/` directory without
overwriting existing files. `check` rejects missing files, references that
escape `webdeck/`, and external runtime dependencies. Normal citation links in
`<a href="https://...">` remain allowed. `release` validates first, copies one
static bundle, and refuses to overwrite its destination.

Serving is localhost-only by default. For a trusted local network:

```text
lecturedeck serve <unit> --lan --livereload
```

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
& "$env:USERPROFILE\.venvs\lecturedeck\Scripts\python.exe" -m compileall -q src tests
```

See `AGENTS.md` and `.agents/commit-culture.md` for the public development,
versioning, privacy, and release gates.
