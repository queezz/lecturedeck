"""Create a unit-local webdeck from the shared runtime scaffold."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def scaffold_unit(unit_root: Path, title: str) -> list[Path]:
    if not unit_root.is_dir():
        raise FileNotFoundError(f"presentation unit not found: {unit_root}")
    webdeck = unit_root / "webdeck"
    webdeck.mkdir(exist_ok=True)
    asset_root = files("lecturedeck").joinpath("assets")
    created: list[Path] = []
    names = ("index.html", "lecturedeck.css", "lecturedeck.js", "slides.js")
    for name in names:
        target = webdeck / name
        if target.exists():
            continue
        content = asset_root.joinpath(name).read_text(encoding="utf-8")
        if name in {"index.html", "slides.js"}:
            content = content.replace("{{TITLE}}", title)
        target.write_text(content, encoding="utf-8", newline="\n")
        created.append(target)
    (webdeck / "assets").mkdir(exist_ok=True)
    return created
