# Durable agent policy

This directory contains public, standing policy for `lecturedeck`:

- `commit-culture.md` — authorship, staging, versioning, and push conventions;
- `release-workflow.md` — the canonical public release and consumer-sync recipe;
- `directions.md` — forward-looking work only;
- `CHANGELOG.md` — shipped per-version history.

Unlike private course repositories, this public repository does not track
session-by-session agent logs or handoffs. Put implementation context in the
commit message, durable open decisions in `directions.md`, and shipped behavior
in `CHANGELOG.md`. Never create or force-add `.agents/log/`.

Tool-specific skills are discovery layers only. They point to the canonical
workflow here and do not restate it.
