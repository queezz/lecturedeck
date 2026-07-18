"""Create content-only webdecks and refresh legacy runtime snapshots."""

from __future__ import annotations

import json
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

RUNTIME_FILES = ("lecturedeck.css", "lecturedeck.js")
CONTENT_FILES = ("deck.css", "deck.json")

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
        "ccde58190cea3d80ab6b14cd708aaead1c97592ebe330b61bf5dd76726d8798a",  # css v0.6.0
        "8ce2c24057be95c8f6988b2366966e0aba8750ef1c7c17e9ea0506975e943ebf",  # js v0.6.0
        "8e19f06ba6478ada711165bd13ed372df445190175cb153e8468062360c23f12",  # css v0.7.0
        "87c4097f4962b7b3f065e957e88f4012b6dd37c3b5b2ce4e6f82aa13a80ec103",  # js v0.7.0
        "4cb7b8b73484cfef8c3a8edfe4864cece5c88cb4f63efbffab8520dbd5c7190a",  # css v0.9.0
        "a92ed82bb172eb1e923518e0bfffb45f16d36bafa60133ac989ccf79d546e54c",  # js v0.9.0
        "f2c5f4702bbbf298bf4c70f65dfc3446cf4a1ea7e232f697b002737df87787f0",  # css v0.10.0
        "f511cc9230d307fb5b2ea00560249312a79136ef8366debc6590e132871f25b7",  # js v0.10.0
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
    if not any((webdeck / name).is_file() for name in ("deck.json", "slides.js")):
        raise FileNotFoundError(f"web deck not found: {webdeck} has no deck.json or slides.js")
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
    for name in CONTENT_FILES:
        target = webdeck / name
        if target.exists():
            continue
        content = asset_root.joinpath(name).read_text(encoding="utf-8")
        if name == "deck.json":
            content = content.replace("{{TITLE}}", json.dumps(title)[1:-1])
        target.write_text(content, encoding="utf-8", newline="\n")
        created.append(target)
    (webdeck / "assets").mkdir(exist_ok=True)
    return created
