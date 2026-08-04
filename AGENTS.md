# Agent entry point

`lecturedeck` is the generic, public runtime for serving and releasing
self-contained web lecture decks. It must remain independent of every course
that consumes it.

## Environment — do this first

Use the project environment outside synchronized folders:

- Windows: `%USERPROFILE%\.venvs\lecturedeck\Scripts\python.exe`
- macOS/Linux: `~/.venvs/lecturedeck/bin/python`

Never create a virtual environment in this repository or in a Dropbox/OneDrive
course tree. If the environment is missing, create it with the user's normal
CPython and install `-e ".[dev]"`, then run `python -m playwright install
chromium` once so the browser smoke suite can run (it skips itself when
Playwright or Chromium is absent). Do not use an application-bundled Python.

Before every commit, run:

```text
<venv-python> -m unittest discover -s tests -v
<venv-python> -m ruff check src tests
```

## Public boundary

This repository contains only reusable runtime code, tests, durable public
workflows, and release history. Never add lecture scripts, source extracts,
figures, citations, course assets, grading/student material, credentials,
machine-local paths, session transcripts, or agent handoff logs. Course-specific
content belongs in the consuming course repository.

Before pushing, inspect `git ls-files` and search tracked text for local paths,
course names, tokens, and private workflow records. `.agents/log/` is ignored and
must not be force-added.

## Agent surfaces

| Layer | Location | Purpose |
|---|---|---|
| Entry point | `AGENTS.md` | Environment, gates, and public boundary |
| Durable policy | `.agents/commit-culture.md` | Commit, version, and push rules |
| Workflow | `.agents/release-workflow.md` | Check, version, publish, and sync recipe |
| State | `.agents/directions.md` | Open work only |
| History | `.agents/CHANGELOG.md` | Shipped version history |
| Codex trigger | `.codex/skills/lecturedeck-maintenance/` | Thin pointer to the workflow |
| Fleet context | `../2026-08-04-repo-map` (`repomap`, github.com/queezz/repomap) | `RULES.md` house rules and `MAP.md` sibling map |

Workflows in `.agents/` are the single source of truth. Tool-specific skills
must remain thin pointers and must not duplicate the recipes.

## Invariants

- Runtime dependencies remain Python standard library only.
- A checked release is self-contained and works offline.
- External source links are allowed; external runtime scripts/styles are not.
- `lecturedeck` reads and copies only a unit's `webdeck/` directory.
- `pyproject.toml`, `src/lecturedeck/__init__.py`, and the `VIEWER_VERSION`
  constant in `src/lecturedeck/assets/lecturedeck.js` carry the same version.
- Do not create git tags unless the user explicitly requests one.
