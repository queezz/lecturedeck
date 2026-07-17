# Changelog — shipped version history

## Shipped

- **v0.1.1** — Validate the local stylesheet and presentation runtime declared
  by `index.html` instead of forcing scaffold filenames. Existing self-contained
  unit snapshots can move to the shared CLI without runtime renames or release
  hash churn; new scaffolds still use `lecturedeck.css` and `lecturedeck.js`.
- **v0.1.0** — Initial public extraction. Generic `lecturedeck` CLI and browser
  runtime; responsive 16:9 presentation shell; native MathML; keyboard, touch,
  overview, fullscreen, and immersive interactive navigation; cache-free local
  and LAN serving; live reload; strict self-contained bundle validation; static
  release copying; and public privacy/versioning workflows.
