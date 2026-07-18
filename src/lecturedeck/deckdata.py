"""Schema validation for declarative deck.json browser data."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import __version__

DECK_SCHEMA_VERSION = 1
ACCENTS = frozenset({"red", "gold", "green", "aqua", "blue", "purple"})
SLIDE_TYPES = frozenset({"title", "section", "content"})
LAYOUTS = frozenset(
    {
        "title",
        "statement",
        "equation",
        "cards",
        "figure",
        "figures",
        "figure-dominant",
        "figure-stage",
        "interactive",
        "video",
    }
)
TRACK_KINDS = frozenset({"captions", "subtitles", "descriptions", "chapters", "metadata"})

DECK_KEYS = frozenset({"deck", "requires", "meta", "slides"})
META_KEYS = frozenset({"title", "section", "opening", "openingAccent"})
SLIDE_KEYS = frozenset(
    {
        "id",
        "type",
        "layout",
        "title",
        "eyebrow",
        "claim",
        "body",
        "quote",
        "source",
        "beat",
        "accent",
        "className",
        "chrome",
        "formula",
        "cards",
        "figure",
        "figures",
        "interactive",
        "video",
    }
)
FIGURE_KEYS = frozenset({"id", "src", "alt", "caption", "source", "shift", "scale"})
FORMULA_KEYS = frozenset({"mathml", "label", "gloss"})
CARD_KEYS = frozenset({"label", "value", "detail"})
INTERACTIVE_KEYS = frozenset({"src", "title"})
VIDEO_KEYS = frozenset(
    {
        "src",
        "type",
        "sources",
        "poster",
        "title",
        "caption",
        "source",
        "originalUrl",
        "originalLabel",
        "muted",
        "loop",
        "tracks",
    }
)
VIDEO_SOURCE_KEYS = frozenset({"src", "type"})
TRACK_KEYS = frozenset({"src", "kind", "srclang", "label", "default"})

MAX_SHIFT = 2000
MAX_SCALE = 10

_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CLASS_NAMES = re.compile(r"^[A-Za-z][\w-]*(?: [A-Za-z][\w-]*)*$")
_REQUIRES = re.compile(r"^>=(\d+)\.(\d+)$")


def _unknown_keys(errors: list[str], where: str, value: dict, known: frozenset) -> None:
    for key in sorted(set(value) - known):
        errors.append(f"deck.json: {where} has unknown field {key!r}")


def _check_string(errors: list[str], where: str, value: dict, key: str) -> None:
    if key in value and not isinstance(value[key], str):
        errors.append(f"deck.json: {where}.{key} must be a string")


def _check_bool(errors: list[str], where: str, value: dict, key: str) -> None:
    if key in value and not isinstance(value[key], bool):
        errors.append(f"deck.json: {where}.{key} must be true or false")


def _check_required_string(errors: list[str], where: str, value: dict, key: str) -> bool:
    if not isinstance(value.get(key), str) or not value[key]:
        errors.append(f"deck.json: {where}.{key} must be a non-empty string")
        return False
    return True


def _check_enum(errors: list[str], where: str, value: dict, key: str, allowed: frozenset) -> None:
    if key in value and value[key] not in allowed:
        errors.append(
            f"deck.json: {where}.{key} must be one of {', '.join(sorted(allowed))}"
        )


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and abs(value) != float("inf")
    )


def _validate_figure(errors: list[str], where: str, figure: object) -> None:
    if not isinstance(figure, dict):
        errors.append(f"deck.json: {where} must be an object")
        return
    _unknown_keys(errors, where, figure, FIGURE_KEYS)
    _check_required_string(errors, where, figure, "src")
    for key in ("alt", "caption", "source"):
        _check_string(errors, where, figure, key)
    if "id" in figure and (
        not isinstance(figure["id"], str) or not _ID.fullmatch(figure["id"])
    ):
        errors.append(f"deck.json: {where}.id must be a lowercase kebab-case identifier")
    if "shift" in figure:
        shift = figure["shift"]
        if (
            not isinstance(shift, list)
            or len(shift) != 2
            or not all(_finite_number(part) and abs(part) <= MAX_SHIFT for part in shift)
        ):
            errors.append(
                f"deck.json: {where}.shift must be [x, y] numbers within ±{MAX_SHIFT}"
            )
    if "scale" in figure:
        scale = figure["scale"]
        if not _finite_number(scale) or not 0 < scale <= MAX_SCALE:
            errors.append(f"deck.json: {where}.scale must be a number in (0, {MAX_SCALE}]")


def _validate_formula(errors: list[str], where: str, formula: object) -> None:
    if isinstance(formula, str):
        return
    if not isinstance(formula, dict):
        errors.append(f"deck.json: {where} must be a string or an object")
        return
    _unknown_keys(errors, where, formula, FORMULA_KEYS)
    _check_required_string(errors, where, formula, "mathml")
    _check_string(errors, where, formula, "label")
    if "gloss" in formula and (
        not isinstance(formula["gloss"], list)
        or not all(isinstance(item, str) for item in formula["gloss"])
    ):
        errors.append(f"deck.json: {where}.gloss must be a list of strings")


def _validate_cards(errors: list[str], where: str, cards: object) -> None:
    if not isinstance(cards, list) or not cards:
        errors.append(f"deck.json: {where} must be a non-empty list")
        return
    for position, card in enumerate(cards):
        card_where = f"{where}[{position}]"
        if not isinstance(card, dict):
            errors.append(f"deck.json: {card_where} must be an object")
            continue
        _unknown_keys(errors, card_where, card, CARD_KEYS)
        for key in CARD_KEYS:
            _check_string(errors, card_where, card, key)


def _validate_interactive(errors: list[str], where: str, interactive: object) -> None:
    if not isinstance(interactive, dict):
        errors.append(f"deck.json: {where} must be an object")
        return
    _unknown_keys(errors, where, interactive, INTERACTIVE_KEYS)
    if _check_required_string(errors, where, interactive, "src") and not interactive[
        "src"
    ].startswith("assets/"):
        errors.append(f"deck.json: {where}.src must lie under assets/")
    _check_string(errors, where, interactive, "title")


def _validate_video(errors: list[str], where: str, video: object) -> None:
    if not isinstance(video, dict):
        errors.append(f"deck.json: {where} must be an object")
        return
    _unknown_keys(errors, where, video, VIDEO_KEYS)
    if "sources" in video:
        if "src" in video or "type" in video:
            errors.append(f"deck.json: {where} must not mix sources with src/type")
        sources = video["sources"]
        if not isinstance(sources, list) or not sources:
            errors.append(f"deck.json: {where}.sources must be a non-empty list")
        else:
            for position, source in enumerate(sources):
                source_where = f"{where}.sources[{position}]"
                if not isinstance(source, dict):
                    errors.append(f"deck.json: {source_where} must be an object")
                    continue
                _unknown_keys(errors, source_where, source, VIDEO_SOURCE_KEYS)
                _check_required_string(errors, source_where, source, "src")
                _check_string(errors, source_where, source, "type")
    else:
        _check_required_string(errors, where, video, "src")
        _check_string(errors, where, video, "type")
    for key in ("poster", "title", "caption", "source", "originalUrl", "originalLabel"):
        _check_string(errors, where, video, key)
    for key in ("muted", "loop"):
        _check_bool(errors, where, video, key)
    if "tracks" in video:
        tracks = video["tracks"]
        if not isinstance(tracks, list):
            errors.append(f"deck.json: {where}.tracks must be a list")
        else:
            for position, track in enumerate(tracks):
                track_where = f"{where}.tracks[{position}]"
                if not isinstance(track, dict):
                    errors.append(f"deck.json: {track_where} must be an object")
                    continue
                _unknown_keys(errors, track_where, track, TRACK_KEYS)
                _check_required_string(errors, track_where, track, "src")
                _check_enum(errors, track_where, track, "kind", TRACK_KINDS)
                _check_string(errors, track_where, track, "srclang")
                _check_string(errors, track_where, track, "label")
                _check_bool(errors, track_where, track, "default")


def _validate_slide(errors: list[str], where: str, slide: object, seen_ids: set[str]) -> None:
    if not isinstance(slide, dict):
        errors.append(f"deck.json: {where} must be an object")
        return
    _unknown_keys(errors, where, slide, SLIDE_KEYS)
    if _check_required_string(errors, where, slide, "id"):
        if not _ID.fullmatch(slide["id"]):
            errors.append(f"deck.json: {where}.id must be a lowercase kebab-case identifier")
        elif slide["id"] in seen_ids:
            errors.append(f"deck.json: duplicate slide id {slide['id']!r}")
        else:
            seen_ids.add(slide["id"])
    _check_enum(errors, where, slide, "type", SLIDE_TYPES)
    _check_enum(errors, where, slide, "layout", LAYOUTS)
    _check_enum(errors, where, slide, "accent", ACCENTS)
    for key in ("title", "eyebrow", "claim", "body", "quote", "source", "beat"):
        _check_string(errors, where, slide, key)
    if "className" in slide and (
        not isinstance(slide["className"], str)
        or not _CLASS_NAMES.fullmatch(slide["className"])
    ):
        errors.append(f"deck.json: {where}.className must be space-separated class names")
    _check_bool(errors, where, slide, "chrome")
    if "formula" in slide:
        _validate_formula(errors, f"{where}.formula", slide["formula"])
    if "cards" in slide:
        _validate_cards(errors, f"{where}.cards", slide["cards"])
    blocks = [key for key in ("figure", "figures", "interactive", "video") if key in slide]
    if "cards" in slide:
        blocks.append("cards")
    if len(blocks) > 1:
        errors.append(
            f"deck.json: {where} must use only one of figure, figures, cards, "
            f"interactive, video (found {', '.join(sorted(blocks))})"
        )
    if "figure" in slide:
        _validate_figure(errors, f"{where}.figure", slide["figure"])
    if "figures" in slide:
        figures = slide["figures"]
        if not isinstance(figures, list) or not figures:
            errors.append(f"deck.json: {where}.figures must be a non-empty list")
        else:
            figure_ids: set[str] = set()
            for position, figure in enumerate(figures):
                _validate_figure(errors, f"{where}.figures[{position}]", figure)
                if isinstance(figure, dict) and isinstance(figure.get("id"), str):
                    if figure["id"] in figure_ids:
                        errors.append(
                            f"deck.json: {where} has duplicate figure id {figure['id']!r}"
                        )
                    figure_ids.add(figure["id"])
    if "interactive" in slide:
        _validate_interactive(errors, f"{where}.interactive", slide["interactive"])
    if "video" in slide:
        _validate_video(errors, f"{where}.video", slide["video"])


def validate_deck(data: object) -> list[str]:
    """Validate deck.json structure; returns error strings, empty when valid."""
    if not isinstance(data, dict):
        return ["deck.json: top level must be a JSON object"]
    errors: list[str] = []
    _unknown_keys(errors, "top level", data, DECK_KEYS)
    if data.get("deck") != DECK_SCHEMA_VERSION:
        errors.append(
            f"deck.json: deck must be the schema version {DECK_SCHEMA_VERSION} "
            f"(found {data.get('deck')!r})"
        )
    if "requires" in data and (
        not isinstance(data["requires"], str) or not _REQUIRES.fullmatch(data["requires"])
    ):
        errors.append('deck.json: requires must look like ">=MAJOR.MINOR"')
    meta = data.get("meta")
    if not isinstance(meta, dict):
        errors.append("deck.json: meta must be an object")
    else:
        _unknown_keys(errors, "meta", meta, META_KEYS)
        _check_required_string(errors, "meta", meta, "title")
        for key in ("section", "opening"):
            _check_string(errors, "meta", meta, key)
        _check_enum(errors, "meta", meta, "openingAccent", ACCENTS)
    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("deck.json: slides must be a non-empty list")
    else:
        seen_ids: set[str] = set()
        for position, slide in enumerate(slides):
            _validate_slide(errors, f"slides[{position}]", slide, seen_ids)
    return errors


def viewer_requirement_error(data: dict) -> str | None:
    """Compare a valid deck's requires field against the installed viewer."""
    requires = data.get("requires")
    if not isinstance(requires, str):
        return None
    match = _REQUIRES.fullmatch(requires)
    if match is None:
        return None
    needed = (int(match[1]), int(match[2]))
    installed = tuple(int(part) for part in __version__.split(".")[:2])
    if installed < needed:
        return (
            f"deck.json: deck requires viewer {requires} but installed "
            f"lecturedeck is {__version__}"
        )
    return None


def deck_asset_references(data: dict) -> list[tuple[str, str]]:
    """(context, reference) pairs for every local file the deck declares."""
    references: list[tuple[str, str]] = []

    def add(where: str, container: object, key: str) -> None:
        if isinstance(container, dict) and isinstance(container.get(key), str):
            references.append((f"{where}.{key}", container[key]))

    slides = data.get("slides")
    if not isinstance(slides, list):
        return references
    for position, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        where = f"slides[{position}]"
        add(f"{where}.figure", slide.get("figure"), "src")
        figures = slide.get("figures")
        if isinstance(figures, list):
            for figure_position, figure in enumerate(figures):
                add(f"{where}.figures[{figure_position}]", figure, "src")
        add(f"{where}.interactive", slide.get("interactive"), "src")
        video = slide.get("video")
        if isinstance(video, dict):
            add(f"{where}.video", video, "src")
            add(f"{where}.video", video, "poster")
            sources = video.get("sources")
            if isinstance(sources, list):
                for source_position, source in enumerate(sources):
                    add(f"{where}.video.sources[{source_position}]", source, "src")
            tracks = video.get("tracks")
            if isinstance(tracks, list):
                for track_position, track in enumerate(tracks):
                    add(f"{where}.video.tracks[{track_position}]", track, "src")
    return references


def _asset_reference_error(webdeck: Path, context: str, reference: str) -> str | None:
    if reference.startswith(("http://", "https://", "//", "data:")):
        return f"deck.json: {context} must be a local path, not {reference}"
    if reference.startswith("/") or "\\" in reference:
        return f"deck.json: {context} must be a relative forward-slash path: {reference}"
    target = (webdeck / reference).resolve()
    if webdeck.resolve() not in (target, *target.parents):
        return f"deck.json: {context} escapes webdeck: {reference}"
    if not target.is_file():
        return f"deck.json: {context} is missing: {reference}"
    return None


def load_deck(path: Path) -> tuple[dict | None, list[str]]:
    """Read and parse deck.json; returns (data, errors)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [f"deck.json: unreadable ({exc})"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"deck.json: invalid JSON ({exc})"]
    if not isinstance(data, dict):
        return None, ["deck.json: top level must be a JSON object"]
    return data, []


def validate_deck_file(path: Path) -> list[str]:
    """Validate structure, viewer requirement, and declared local assets."""
    data, errors = load_deck(path)
    if data is None:
        return errors
    errors = validate_deck(data)
    requirement = viewer_requirement_error(data)
    if requirement:
        errors.append(requirement)
    webdeck = path.parent
    for context, reference in deck_asset_references(data):
        problem = _asset_reference_error(webdeck, context, reference)
        if problem:
            errors.append(problem)
    return errors
