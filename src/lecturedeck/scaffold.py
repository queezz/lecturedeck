"""Create and refresh unit-local webdecks from the shared runtime scaffold."""

from __future__ import annotations

from hashlib import sha256
from importlib.resources import files
from pathlib import Path

RUNTIME_FILES = ("lecturedeck.css", "lecturedeck.js")

# sha256 of every published runtime file (BOM stripped, CRLF normalized).
# Append the new hashes whenever a release changes a runtime asset; a unit
# file matching one of these is a clean snapshot that refresh may replace.
PUBLISHED_RUNTIME_HASHES = frozenset(
    {
        "d9bd409148b18d1616f8eac3d062679676dffd5a71cd58cd0ef13d153fdec738",  # css v0.1.0
        "a4583362a8af52b188271fe4af069bf0d840797aaa6b346980f863ec9de64b08",  # js v0.1.0
        "3c9e25948dd7a8d135709d77d09b5dcbfb9986f9c7d9d87504c7bc05a80256fe",  # css v0.2.0
        "c1d317b86567b5dc8f5eb5b7d4f0c118238b071d3aca86cd3c89352fc4ac78f6",  # js v0.2.0
        "05fb40d8e95899e7e0f7f55ee96089349f2c91551784097bde6bec4801ce08b5",  # css v0.3.0
        "dde8d9366bdc95159b37609f8d36fa1ad15351e8852b1e916ec9cd5b542eb2a1",  # js v0.3.0
        "6941b10008cc4137f7205b0bc04f4d9e392995ea46766ad9ddb9ab9fd44dbce8",  # js v0.4.0
    }
)


def runtime_hash(text: str) -> str:
    return sha256(text.lstrip("﻿").replace("\r\n", "\n").encode("utf-8")).hexdigest()


def refresh_unit(unit_root: Path, force: bool = False) -> list[tuple[str, str]]:
    """Update scaffold-owned runtime files; never touch slides.js or assets.

    Returns (filename, state) pairs where state is one of: "current",
    "refreshed", "kept" (locally modified and force is off), or "missing"
    (the unit retained its own runtime filenames).
    """
    webdeck = unit_root / "webdeck"
    if not (webdeck / "index.html").is_file():
        raise FileNotFoundError(f"web deck not found: {webdeck / 'index.html'}")
    asset_root = files("lecturedeck").joinpath("assets")
    results: list[tuple[str, str]] = []
    for name in RUNTIME_FILES:
        target = webdeck / name
        if not target.is_file():
            results.append((name, "missing"))
            continue
        packaged = asset_root.joinpath(name).read_text(encoding="utf-8")
        current = target.read_text(encoding="utf-8")
        if runtime_hash(current) == runtime_hash(packaged):
            results.append((name, "current"))
        elif runtime_hash(current) in PUBLISHED_RUNTIME_HASHES or force:
            target.write_text(packaged, encoding="utf-8", newline="\n")
            results.append((name, "refreshed"))
        else:
            results.append((name, "kept"))
    return results


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
