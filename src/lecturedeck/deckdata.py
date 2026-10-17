"""Schema validation for declarative deck.json browser data."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from . import __version__

DECK_SCHEMA_VERSION = 1
ACCENTS = frozenset({"red", "gold", "green", "aqua", "blue", "purple"})
FAVICON_PRESETS = frozenset({"calculus", "complex", "plasma"})
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
# Layouts whose renderer draws the slide's figure block (lecturedeck.js).
FIGURE_LAYOUTS = frozenset({"figure", "figure-dominant", "figure-stage", "title", "figures"})

DECK_KEYS = frozenset({"deck", "requires", "meta", "slides"})
META_KEYS = frozenset(
    {
        "title",
        "section",
        "opening",
        "openingAccent",
        "favicon",
        "selectorGroup",
        "selectorHero",
        "tabTitle",
        "selectorTitle",
        "selectorFavicon",
    }
)
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
        "appendix",
        "formula",
        "cards",
        "figure",
        "figures",
        "interactive",
        "video",
    }
)
FIGURE_KEYS = frozenset({"id", "src", "alt", "caption", "source", "shift", "scale", "step"})
FORMULA_KEYS = frozenset({"mathml", "label", "gloss", "step"})
CARD_TEXT_KEYS = ("label", "value", "detail")
CARD_KEYS = frozenset({*CARD_TEXT_KEYS, "step"})
INTERACTIVE_KEYS = frozenset({"src", "title", "step"})
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
        "step",
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


def _validate_favicon(errors: list[str], meta: dict) -> None:
    if "favicon" not in meta:
        return
    favicon = meta["favicon"]
    if not isinstance(favicon, str) or not favicon:
        errors.append("deck.json: meta.favicon must be a non-empty string")
    elif favicon not in FAVICON_PRESETS and not favicon.startswith("assets/"):
        presets = ", ".join(sorted(FAVICON_PRESETS))
        errors.append(
            f"deck.json: meta.favicon must be a preset ({presets}) or a path under assets/"
        )


def _validate_selector_metadata(errors: list[str], meta: dict) -> None:
    if "selectorGroup" in meta and (
        not isinstance(meta["selectorGroup"], str) or not meta["selectorGroup"].strip()
    ):
        errors.append("deck.json: meta.selectorGroup must be a non-empty string")
    if "selectorFavicon" in meta:
        icon = meta["selectorFavicon"]
        if not isinstance(icon, str) or not icon:
            errors.append("deck.json: meta.selectorFavicon must be a non-empty string")
        elif not icon.startswith("assets/") or "\\" in icon or ".." in icon.split("/"):
            errors.append("deck.json: meta.selectorFavicon must be a path under assets/")
    if "selectorHero" in meta:
        hero = meta["selectorHero"]
        if not isinstance(hero, str) or not hero:
            errors.append("deck.json: meta.selectorHero must be a non-empty string")
        elif not hero.startswith("assets/"):
            errors.append("deck.json: meta.selectorHero must be a path under assets/")


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
        for key in CARD_TEXT_KEYS:
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
    _check_bool(errors, where, slide, "appendix")
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
    _validate_steps(errors, where, slide)


def effective_layout(slide: dict) -> str:
    """lecturedeck.js slideMarkup's layout inference."""
    layout = slide.get("layout")
    if isinstance(layout, str) and layout:
        return layout
    if slide.get("interactive"):
        return "interactive"
    if slide.get("video"):
        return "video"
    figures = slide.get("figures")
    count = len(figures) if isinstance(figures, list) else 1 if slide.get("figure") else 0
    if count > 1:
        return "figures"
    if count:
        return "figure"
    if slide.get("type") == "title":
        return "title"
    if isinstance(slide.get("cards"), list) and slide["cards"]:
        return "cards"
    if slide.get("formula"):
        return "equation"
    return "statement"


# --------------------------------------------------------------------------
# Step-by-step reveals
#
# An element of slide HTML with data-step="N" is a step; a figure, card,
# formula, interactive or video declares one with its own "step" field. N is
# a positive integer. The viewer reveals the distinct numbers in ascending
# order, so a gap costs nothing but reads like a mistake: check warns about
# it. A step in content the slide never shows is an error, because the press
# meant to reveal it would show nothing. A step nested in a later one (a
# caption step below its figure's step, an element inside a later element)
# cannot show before it: the viewer shows it with the later step, and check
# warns.

_STEP_VALUE = re.compile(r"[1-9][0-9]*")
# Elements that never hold content, so they never enclose another step.
_VOID_TAGS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)


class _StepScanner(HTMLParser):
    """Collect every data-step value in an HTML fragment, each with the
    highest valid step among the elements around it (0 when none)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values: list[str | None] = []
        self.enclosing: list[int] = []
        self._open: list[tuple[str, int]] = []

    def _start(self, tag: str, attrs, closed: bool) -> None:
        around = self._open[-1][1] if self._open else 0
        own = 0
        for name, value in attrs:
            if name == "data-step":
                self.values.append(value)
                self.enclosing.append(around)
                if isinstance(value, str) and _STEP_VALUE.fullmatch(value):
                    own = max(own, int(value))
        if not closed and tag not in _VOID_TAGS:
            self._open.append((tag, max(around, own)))

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, closed=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, closed=True)

    def handle_endtag(self, tag):
        for depth in range(len(self._open) - 1, -1, -1):
            if self._open[depth][0] == tag:
                del self._open[depth:]
                return


def _scan_steps(html: str) -> _StepScanner | None:
    if "data-step" not in html.lower():
        return None
    scanner = _StepScanner()
    scanner.feed(html)
    scanner.close()
    return scanner


def html_step_values(html: str) -> list[str | None]:
    """Raw data-step values in an HTML fragment (None for a bare attribute)."""
    scanner = _scan_steps(html)
    return scanner.values if scanner else []


def _html_steps(html: str) -> list[tuple[str | None, int]]:
    """(raw data-step value, highest valid step around it) in document order."""
    scanner = _scan_steps(html)
    return list(zip(scanner.values, scanner.enclosing)) if scanner else []


def _owner(field: str, value: object) -> tuple[str, int] | None:
    """(field, step) of an object whose own valid step encloses its HTML."""
    if isinstance(value, dict):
        step = _step_number("field", value.get("step"))
        if step is not None:
            return field, step
    return None


def _step_sources(slide: dict, where: str) -> list[tuple]:
    """(field, kind, value, why it is never shown, owner) for every place a step can sit.

    ``kind`` is ``"html"`` for slide HTML scanned for data-step and
    ``"field"`` for an object's own ``step``. ``owner`` is the ``(field,
    step)`` of the object whose own step encloses that HTML (a figure's
    caption, a card's text), or None. Fields that lecturedeck.js escapes
    (formula labels, media titles, alt text) are text, not markup.
    """
    chrome = slide.get("chrome") is not False
    layout = effective_layout(slide)
    no_chrome = None if chrome else "chrome: false drops the title, eyebrow and source"
    copy_hidden = (
        "a full-canvas interactive slide (chrome: false) hides its claim, formula, "
        "body and quote"
        if not chrome and layout == "interactive"
        else None
    )
    sources: list[tuple] = []

    def html(field: str, value: object, hidden: str | None, owner=None) -> None:
        if isinstance(value, str):
            sources.append((field, "html", value, hidden, owner))

    def own(field: str, value: object, hidden: str | None) -> None:
        if isinstance(value, dict) and "step" in value:
            sources.append((f"{field}.step", "field", value["step"], hidden, None))

    def unshown(block: str) -> str:
        return f"layout {layout!r} does not show the {block}"

    for key in ("title", "eyebrow"):
        html(f"{where}.{key}", slide.get(key), no_chrome)
    for key in ("claim", "body", "quote"):
        html(f"{where}.{key}", slide.get(key), copy_hidden)
    formula = slide.get("formula")
    if isinstance(formula, dict):
        own(f"{where}.formula", formula, copy_hidden)
        owner = _owner(f"{where}.formula", formula)
        html(f"{where}.formula.mathml", formula.get("mathml"), copy_hidden, owner)
        gloss = formula.get("gloss")
        if isinstance(gloss, list):
            for position, item in enumerate(gloss):
                html(f"{where}.formula.gloss[{position}]", item, copy_hidden, owner)
    if isinstance(slide.get("figures"), list):
        figures = [(f"{where}.figures[{n}]", item) for n, item in enumerate(slide["figures"])]
    else:
        figures = [(f"{where}.figure", slide.get("figure"))]
    hidden = None if layout in FIGURE_LAYOUTS else unshown("figure")
    for field, figure in figures:
        if isinstance(figure, dict):
            own(field, figure, hidden)
            for key in ("caption", "source"):
                html(f"{field}.{key}", figure.get(key), hidden, _owner(field, figure))
    cards = slide.get("cards")
    if isinstance(cards, list):
        hidden = None if layout == "cards" else unshown("cards")
        for position, card in enumerate(cards):
            if isinstance(card, dict):
                field = f"{where}.cards[{position}]"
                own(field, card, hidden)
                for key in CARD_TEXT_KEYS:
                    html(f"{field}.{key}", card.get(key), hidden, _owner(field, card))
    own(
        f"{where}.interactive",
        slide.get("interactive"),
        None if layout == "interactive" else unshown("interactive"),
    )
    video = slide.get("video")
    if isinstance(video, dict):
        hidden = None if layout == "video" else unshown("video")
        own(f"{where}.video", video, hidden)
        owner = _owner(f"{where}.video", video)
        for key in ("caption", "source"):
            html(f"{where}.video.{key}", video.get(key), hidden, owner)
    html(f"{where}.source", slide.get("source"), no_chrome)
    return sources


def _step_number(kind: str, value: object) -> int | None:
    """The step a declaration names, or None when it is not a positive integer."""
    if kind == "field":
        return value if type(value) is int and value >= 1 else None
    return int(value) if isinstance(value, str) and _STEP_VALUE.fullmatch(value) else None


def _declared_steps(slide: dict, where: str):
    """(field, kind, raw, step or None, why never shown, around) per declaration.

    ``around`` is None, or ``(what, step)`` naming the highest valid step
    that encloses the declaration: an element around it in the same HTML,
    or the object whose own step owns that HTML.
    """
    for field, kind, value, hidden, owner in _step_sources(slide, where):
        if kind == "field":
            yield field, kind, value, _step_number(kind, value), hidden, None
            continue
        for raw, enclosing in _html_steps(value):
            around = None
            if enclosing and (owner is None or enclosing > owner[1]):
                around = (f'a data-step="{enclosing}" element', enclosing)
            elif owner:
                around = (f"{owner[0]} (step {owner[1]})", owner[1])
            yield field, kind, raw, _step_number(kind, raw), hidden, around


def _validate_steps(errors: list[str], where: str, slide: dict) -> None:
    unshown: set[str] = set()
    for field, kind, raw, step, hidden, _ in _declared_steps(slide, where):
        if step is None:
            if kind == "field":
                errors.append(f"deck.json: {field} must be a positive integer")
            else:
                found = "an empty data-step" if not raw else f"data-step={raw!r}"
                errors.append(
                    f"deck.json: {field} has {found}; data-step must be a positive integer"
                )
        elif hidden and field not in unshown:
            unshown.add(field)
            errors.append(f"deck.json: {field} has a step this slide never shows: {hidden}")


def _ranges(numbers: list[int]) -> str:
    """Sorted integers as compact runs: [2, 3, 4, 7] -> "2-4, 7"."""
    parts: list[str] = []
    start = previous = numbers[0]
    for number in [*numbers[1:], None]:
        if number is not None and number == previous + 1:
            previous = number
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        if number is not None:
            start = previous = number
    return ", ".join(parts)


def deck_warnings(data: object) -> list[str]:
    """Advice that does not stop a deck from presenting: a step nested in a
    later one, and gaps in a slide's step numbers."""
    if not isinstance(data, dict) or not isinstance(data.get("slides"), list):
        return []
    warnings: list[str] = []
    for position, slide in enumerate(data["slides"]):
        if not isinstance(slide, dict):
            continue
        where = f"slides[{position}]"
        levels: set[int] = set()
        for field, _, _, step, hidden, around in _declared_steps(slide, where):
            if step is None or hidden:
                continue
            if around and step < around[1]:
                warnings.append(
                    f'deck.json: {field} has data-step="{step}" inside {around[0]}; '
                    f"it appears with step {around[1]}, not before it"
                )
                step = around[1]
            levels.add(step)
        used = sorted(levels)
        # Gaps as runs, never as a list: a stray data-step="900" is one run.
        gaps, previous = [], 0
        for step in used:
            if step == previous + 2:
                gaps.append(str(previous + 1))
            elif step > previous + 2:
                gaps.append(f"{previous + 1}-{step - 1}")
            previous = step
        if gaps:
            name = f" ({slide['id']})" if isinstance(slide.get("id"), str) else ""
            warnings.append(
                f"deck.json: {where}{name} skips step {', '.join(gaps)} "
                f"(uses {_ranges(used)}); each press still reveals the next number used"
            )
    return warnings


def _validate_appendix(errors: list[str], slides: list) -> None:
    # The appendix slide starts the backup material; a second marker would
    # be ambiguous, so a deck declares at most one boundary.
    starts = [
        f"slides[{position}]"
        for position, slide in enumerate(slides)
        if isinstance(slide, dict) and slide.get("appendix") is True
    ]
    if len(starts) > 1:
        errors.append(
            "deck.json: only one slide may set appendix to true; "
            f"it marks where the appendix starts (found {', '.join(starts)})"
        )


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
        for key in ("section", "opening", "tabTitle", "selectorTitle"):
            _check_string(errors, "meta", meta, key)
        # The course name and the opening part label repeat on many slides;
        # a step there would hide part of every one of them.
        for key, shown in (
            ("section", "every slide's footer"),
            ("opening", "the eyebrow of every slide before the first section"),
        ):
            if isinstance(meta.get(key), str) and html_step_values(meta[key]):
                errors.append(
                    f"deck.json: meta.{key} cannot hold a data-step; it is shown in {shown}"
                )
        _check_enum(errors, "meta", meta, "openingAccent", ACCENTS)
        _validate_favicon(errors, meta)
        _validate_selector_metadata(errors, meta)
    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("deck.json: slides must be a non-empty list")
    else:
        seen_ids: set[str] = set()
        for position, slide in enumerate(slides):
            _validate_slide(errors, f"slides[{position}]", slide, seen_ids)
        _validate_appendix(errors, slides)
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

    meta = data.get("meta")
    if isinstance(meta, dict):
        favicon = meta.get("favicon")
        if isinstance(favicon, str) and favicon.startswith("assets/"):
            references.append(("meta.favicon", favicon))
        selector_icon = meta.get("selectorFavicon")
        if isinstance(selector_icon, str) and selector_icon.startswith("assets/"):
            references.append(("meta.selectorFavicon", selector_icon))
        selector_hero = meta.get("selectorHero")
        if isinstance(selector_hero, str) and selector_hero.startswith("assets/"):
            references.append(("meta.selectorHero", selector_hero))

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
