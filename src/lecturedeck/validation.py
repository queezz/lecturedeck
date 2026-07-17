"""Static-bundle checks and release copying."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

_REFERENCE = re.compile(
    r"<(?P<tag>[a-z][a-z0-9-]*)\b[^>]*?\b(?P<attr>src|href)\s*=\s*"
    r"[\"'](?P<html_ref>[^\"']+)[\"']|[\"'](?P<asset_ref>assets/[^\"']+)[\"']",
    re.IGNORECASE,
)


def validate_unit(unit_root: Path) -> list[str]:
    webdeck = unit_root / "webdeck"
    errors: list[str] = []
    for required in ("index.html", "slides.js"):
        if not (webdeck / required).is_file():
            errors.append(f"missing webdeck/{required}")
    if errors:
        return errors

    index_text = (webdeck / "index.html").read_text(encoding="utf-8")
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

    for source in webdeck.rglob("*"):
        if source.suffix.lower() not in {".html", ".css", ".js"}:
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
            target = (source.parent / ref.split("?", 1)[0].split("#", 1)[0]).resolve()
            if webdeck.resolve() not in (target, *target.parents):
                errors.append(f"reference escapes webdeck in {source.name}: {ref}")
            elif not target.is_file():
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
    return output
