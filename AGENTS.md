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
| Fleet context | `../fleet` (`fleet`, github.com/queezz/fleet) | `RULES.md` house rules and `MAP.md` sibling map |

Workflows in `.agents/` are the single source of truth. Tool-specific skills
must remain thin pointers and must not duplicate the recipes.

## Invariants

- Runtime dependencies remain Python standard library only.
- A checked release is self-contained and works offline.
- External source links are allowed; external runtime scripts/styles are not.
- `lecturedeck` reads and copies only a unit's `webdeck/` directory, with one
  exception: while serving, it writes pacing records to
  `<unit>/pacing-records/<YYYY-MM-DD>_<HHMM>_<unit>_<segment>.json`, beside
  `webdeck/` and never inside it. It writes only when all of these hold:
  - serving was not started with `--no-pacing-records`;
  - the request is a same-origin JSON POST carrying the `X-Lecturedeck-Pacing`
    header;
  - it comes from a browser on the serving machine: a loopback peer, or the
    connection's own local address; a `localhost` or IP-literal `Host` on the
    server's port; an exactly matching `Origin`; and no proxy headers;
  - the body is at most 256 KiB and passes the pacing-record schema;
  - the date is listed in that unit's `webdeck/presentation-time.json`;
  - no stored record for that segment has an equal or higher revision.

  The server chooses the path itself from validated fields and writes
  atomically (temp file, fsync, replace). It never deletes, and it reads back
  only the one file it is about to replace. The pacing write script is
  injected only for such browsers. `pacing-records/` is never served, checked,
  released, copied or hashed for live reload. Static releases and PDF exports
  contain no write code and no write endpoint.
- A pacing record contains only:
  - the unit name, deck path and deck title;
  - the schedule;
  - the viewer version;
  - a random segment id;
  - per slide: id, number, label, title, section and backup flag;
  - per visit: slide id, start, duration and phase;
  - pauses, with start, duration and reason;
  - time in fullscreen;
  - the server's save time, host name and version.

  It never contains page input, free text beyond slide and section titles, or
  anything about the audience.
- `pyproject.toml`, `src/lecturedeck/__init__.py`, and the `VIEWER_VERSION`
  constant in `src/lecturedeck/assets/lecturedeck.js` carry the same version.
- Do not create git tags unless the user explicitly requests one.
