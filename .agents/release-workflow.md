# Public release and consumer-validation workflow

This is the canonical workflow for changing `lecturedeck`, publishing it to
GitHub, and validating course repositories that consume it.

## 1. Bound the change

State the runtime behavior being changed and which public contract it touches:
CLI, unit layout, browser runtime, interactive iframe, validation, or release
copying. Course-specific claims, styles, figures, and scripts are out of scope.

## 2. Implement in the independent repository

Work in the `lecturedeck` checkout, not in a copied course-local fork. Keep the
runtime standard-library-only. Add or update focused tests for every behavior
change.

The canonical development checkout is the only permitted editable-install
source for the shared `lecturedeck` environment. Course repositories do not
vendor, submodule, or otherwise pin the package source. They invoke the shared
environment's `lecturedeck` executable, and checked static release bundles are
the reproducible, self-contained record of the runtime used for publication.

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

Follow `commit-culture.md`. Keep the three version strings synchronized. Add the
user-visible change to `.agents/CHANGELOG.md`; keep unresolved work in
`.agents/directions.md` and remove items when they ship.

## 6. Commit and publish

Review the complete diff, stage explicit paths, commit directly to `main`, and
push `origin main`. Do not tag unless the user requested it.

## 7. Validate consumers

Runtime publication does not require coordinated commits in course
repositories. For each consumer that should adopt the change:

1. update the canonical checkout and shared environment;
2. run the consumer's focused deck checks with that environment;
3. create and review a new static release when the published deck should adopt
   the new runtime;
4. commit only course-owned content or release artifacts according to that
   repository's policy.

Never copy or submodule the package source into lecture repositories. New and
migrated consumer units are content-only: `deck.json` (or legacy `slides.js`),
optional `deck.css`, and `assets/` belong to the unit, while the installed
canonical package supplies the viewer. Course-local `index.html`,
`lecturedeck.css`, or `lecturedeck.js` are legacy overrides and require an
explicit migration decision.
