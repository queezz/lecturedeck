"""Static-bundle checks and release copying."""

from __future__ import annotations

import re
import shutil
from importlib.resources import files
from pathlib import Path

VIEWER_FILES = ("index.html", "lecturedeck.css", "lecturedeck.js")
OPTIONAL_DECK_CSS = "deck.css"

_REFERENCE = re.compile(
    r"<(?P<tag>[a-z][a-z0-9-]*)\b[^>]*?\b(?P<attr>src|href)\s*=\s*"
    r"[\"'](?P<html_ref>[^\"']+)[\"']|[\"'](?P<asset_ref>assets/[^\"']+)[\"']",
    re.IGNORECASE,
)


def validate_unit(unit_root: Path) -> list[str]:
    webdeck = unit_root / "webdeck"
    errors: list[str] = []
    for required in ("slides.js",):
        if not (webdeck / required).is_file():
            errors.append(f"missing webdeck/{required}")
    if errors:
        return errors

    asset_root = files("lecturedeck").joinpath("assets")
    local_index = webdeck / "index.html"
    index_text = (
        local_index.read_text(encoding="utf-8")
        if local_index.is_file()
        else asset_root.joinpath("index.html").read_text(encoding="utf-8")
    )
    index_refs = [
        (match.group("tag"), match.group("attr"), match.group("html_ref"))
        for match in _REFERENCE.finditer(index_text)
        if match.group("html_ref")
    ]
    local_styles = [
        ref
        for tag, attr, ref in index_refs
        if tag == "link"
        and attr == "href"
        and ref.lower().split("?", 1)[0].endswith(".css")
        and not ref.startswith(("http://", "https://", "//"))
    ]
    local_runtime_scripts = [
        ref
        for tag, attr, ref in index_refs
        if tag == "script"
        and attr == "src"
        and ref.lower().split("?", 1)[0].endswith(".js")
        and Path(ref.split("?", 1)[0]).name != "slides.js"
        and not ref.startswith(("http://", "https://", "//"))
    ]
    if not local_styles:
        errors.append("index.html has no local stylesheet")
    if not local_runtime_scripts:
        errors.append("index.html has no local presentation runtime")

    sources = [source for source in webdeck.rglob("*") if source.is_file()]
    if not local_index.is_file():
        sources.append(asset_root.joinpath("index.html"))
    for source in sources:
        if Path(source.name).suffix.lower() not in {".html", ".css", ".js"}:
            continue
        text = source.read_text(encoding="utf-8")
        for match in _REFERENCE.finditer(text):
            ref = match.group("html_ref") or match.group("asset_ref")
            if not ref or "${" in ref or ref.startswith(("#", "data:", "mailto:")):
                continue
            if ref.startswith(("http://", "https://", "//")):
                if match.group("tag") == "a" and match.group("attr") == "href":
                    continue
                errors.append(f"external dependency in {source.name}: {ref}")
                continue
            ref_path = ref.split("?", 1)[0].split("#", 1)[0]
            if Path(source).name == "index.html":
                target = webdeck / ref_path
                packaged_fallback = asset_root.joinpath(Path(ref_path).name)
            else:
                target = (Path(source).parent / ref_path).resolve()
                packaged_fallback = None
            if webdeck.resolve() not in (target, *target.parents):
                errors.append(f"reference escapes webdeck in {source.name}: {ref}")
            elif not target.is_file() and not (
                packaged_fallback is not None and packaged_fallback.is_file()
            ):
                errors.append(f"missing reference in {source.name}: {ref}")
    return sorted(set(errors))


def release_unit(unit_root: Path, output: Path) -> Path:
    errors = validate_unit(unit_root)
    if errors:
        raise ValueError("; ".join(errors))
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    shutil.copytree(unit_root / "webdeck", output)
    asset_root = files("lecturedeck").joinpath("assets")
    for name in (*VIEWER_FILES, OPTIONAL_DECK_CSS):
        target = output / name
        if not target.exists():
            target.write_bytes(asset_root.joinpath(name).read_bytes())
    return output
