"""Static-bundle checks and release copying."""

from __future__ import annotations

import re
import shutil
from importlib.resources import files
from pathlib import Path

from .deckdata import validate_deck_file

VIEWER_FILES = ("index.html", "lecturedeck.css", "lecturedeck.js")
OPTIONAL_DECK_CSS = "deck.css"
# Root-index references that the server satisfies from the installed package.
PACKAGED_FALLBACK_NAMES = frozenset({*VIEWER_FILES, OPTIONAL_DECK_CSS})
SCANNED_SUFFIXES = frozenset({".html", ".css", ".js", ".mjs"})

_REFERENCE = re.compile(
    r"<(?P<tag>[a-z][a-z0-9-]*)\b[^>]*?\b(?P<attr>src|href)\s*=\s*"
    r"[\"'](?P<html_ref>[^\"']+)[\"']|[\"'](?P<asset_ref>assets/[^\"']+)[\"']",
    re.IGNORECASE,
)
_CSS_URL = re.compile(
    r"url\(\s*(?P<quote>[\"']?)(?P<ref>[^\"'()\s]+)(?P=quote)\s*\)", re.IGNORECASE
)
_CSS_IMPORT = re.compile(r"@import\s+[\"'](?P<ref>[^\"']+)[\"']", re.IGNORECASE)
_MODULE_IMPORTS = (
    re.compile(r"\b(?:import|export)\s+[\w$*{},\s]*?\bfrom\s*[\"']([^\"']+)[\"']"),
    re.compile(r"\bimport\s*[\"']([^\"']+)[\"']"),
    re.compile(r"\bimport\s*\(\s*[\"']([^\"']+)[\"']\s*\)"),
)


def deck_entry(unit_root: Path) -> Path | None:
    """The unit's deck data file: deck.json, or legacy slides.js."""
    webdeck = unit_root / "webdeck"
    for name in ("deck.json", "slides.js"):
        candidate = webdeck / name
        if candidate.is_file():
            return candidate
    return None


def _collect_references(text: str, suffix: str, errors: list[str], label: str):
    """(tag, attr, reference) triples found in one source file."""
    references: list[tuple[str, str, str]] = []
    for match in _REFERENCE.finditer(text):
        reference = match.group("html_ref") or match.group("asset_ref")
        if reference:
            references.append((match.group("tag") or "", match.group("attr") or "", reference))
    if suffix == ".css":
        for pattern in (_CSS_URL, _CSS_IMPORT):
            for match in pattern.finditer(text):
                references.append(("", "", match.group("ref")))
    if suffix in {".js", ".mjs"}:
        for pattern in _MODULE_IMPORTS:
            for match in pattern.finditer(text):
                specifier = match.group(1)
                if specifier.startswith(("./", "../", "/", "http://", "https://", "//")):
                    references.append(("", "", specifier))
                else:
                    errors.append(f"unresolvable module import in {label}: {specifier}")
    return references


def validate_unit(unit_root: Path) -> list[str]:
    webdeck = unit_root / "webdeck"
    errors: list[str] = []
    deck_json = webdeck / "deck.json"
    if not deck_json.is_file() and not (webdeck / "slides.js").is_file():
        return ["missing webdeck/deck.json (or legacy webdeck/slides.js)"]
    if deck_json.is_file():
        errors.extend(validate_deck_file(deck_json))

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

    webdeck_root = webdeck.resolve()
    # (source, reference base directory, is the served root index, message label)
    scanned: list[tuple[object, Path, bool, str]] = [
        (source, source.parent, source == local_index, source.relative_to(webdeck).as_posix())
        for source in sorted(webdeck.rglob("*"))
        if source.is_file() and source.suffix.lower() in SCANNED_SUFFIXES
    ]
    if not local_index.is_file():
        scanned.append((asset_root.joinpath("index.html"), webdeck, True, "index.html"))

    for source, base, is_root_index, label in scanned:
        text = source.read_text(encoding="utf-8", errors="replace")
        suffix = Path(label).suffix.lower()
        for tag, attr, reference in _collect_references(text, suffix, errors, label):
            if "${" in reference or reference.startswith(("#", "data:", "mailto:")):
                continue
            if reference.startswith(("http://", "https://", "//")):
                if tag == "a" and attr == "href":
                    continue
                errors.append(f"external dependency in {label}: {reference}")
                continue
            ref_path = reference.split("?", 1)[0].split("#", 1)[0]
            if not ref_path:
                continue
            target = (base / ref_path).resolve()
            fallback = (
                asset_root.joinpath(ref_path)
                if is_root_index and ref_path in PACKAGED_FALLBACK_NAMES
                else None
            )
            if webdeck_root not in (target, *target.parents):
                errors.append(f"reference escapes webdeck in {label}: {reference}")
            elif not target.is_file() and not (fallback is not None and fallback.is_file()):
                errors.append(f"missing reference in {label}: {reference}")
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
