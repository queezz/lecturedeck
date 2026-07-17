# Public release and consumer-sync workflow

This is the canonical workflow for changing `lecturedeck`, publishing it to
GitHub, and updating course repositories that consume it.

## 1. Bound the change

State the runtime behavior being changed and which public contract it touches:
CLI, unit layout, browser runtime, interactive iframe, validation, or release
copying. Course-specific claims, styles, figures, and scripts are out of scope.

## 2. Implement in the independent repository

Work in the `lecturedeck` checkout, not in a copied course-local fork. Keep the
runtime standard-library-only. Add or update focused tests for every behavior
change.

## 3. Verify the public boundary

Inspect every tracked path:

```text
git ls-files
```

Search tracked text for at least:

```text
C:\Users   /Users/   Dropbox   OneDrive   token   password
student-data terms   assessment-result terms   known course names
course-material folder names   private workspace names
```

Investigate every hit. Generic documentation may mention a platform or the word
"course" but must not expose local paths, private directions, lecture content,
or student data. Confirm `.agents/log/`, media, PDFs, releases, caches, and
course assets are absent.

## 4. Run gates

```text
<venv-python> -m unittest discover -s tests -v
<venv-python> -m ruff check src tests
git diff --check
lecturedeck --help
```

Create a temporary sample course tree outside synchronized folders, run
`init`, `check`, and `release`, then verify the static bundle contains only its
`webdeck/` files.

## 5. Version and record

Follow `commit-culture.md`. Keep the two version strings synchronized. Add the
user-visible change to `.agents/CHANGELOG.md`; keep unresolved work in
`.agents/directions.md` and remove items when they ship.

## 6. Commit and publish

Review the complete diff, stage explicit paths, commit directly to `main`, and
push `origin main`. Do not tag unless the user requested it.

## 7. Synchronize consumers

Each course repository consumes the same GitHub origin at `tools/lecturedeck`
as a git submodule. In every consumer:

1. fetch the submodule origin;
2. check out the intended `lecturedeck` commit;
3. run the consumer's focused deck checks;
4. stage only `.gitmodules` and the submodule pointer;
5. commit in that course repository according to its own policy.

Never copy the package source into multiple lecture repositories. Course-local
webdeck runtime files are generated snapshots and remain owned by their unit;
update them deliberately when a runtime change is needed.
