# Commit and versioning culture

Standing conventions for this public, independently versioned tool.

## Authorship

- Do not add AI `Co-Authored-By`, `Signed-off-by`, or vendor trailers.
- An agent-authored commit ends with one plain line: `agent: <model name>`.
- The repository author and committer remain the user's configured identity.

## Commit messages

- Use a short factual title, normally about 50 characters, with no period.
- Wrap the body near 62 columns; use bullets for scannable implementation notes.
- Put the version in the title when the commit bumps it.
- Keep one cohesive change per commit.

## Branching and pushing

This is a solo personal tool. When the user asks to commit or publish, commit
directly to `main` and push `origin main`; do not add branch/PR ceremony unless
the user requests it.

Stage explicit paths. Never use `git add -A` in a mixed worktree. Never stage
caches, environments, generated releases, course content, or `.agents/log/`.

## Version canon

The version lives in two files and must change together:

- `pyproject.toml` → `[project] version`
- `src/lecturedeck/__init__.py` → `__version__`

Use pragmatic semantic versioning:

| Change | Version |
|---|---|
| still establishing the tool | `0.x` |
| first dependable multi-course runtime | `1.0.0` |
| incompatible runtime or unit-contract change | major |
| user-visible capability | minor |
| compatible fix or polish | patch |
| docs/refactor with no behavior change | no bump |

Bump both files in the same commit as the behavior being marked and add the
matching entry to `.agents/CHANGELOG.md`.

Git tags are rare and belong to the user. Agents do not create or suggest tags
unless the user explicitly asks.

## Gates

Before committing:

```text
<venv-python> -m unittest discover -s tests -v
<venv-python> -m ruff check src tests
git diff --check
```

Before pushing a public revision, also complete the privacy and tracked-file
audit in `release-workflow.md`.
