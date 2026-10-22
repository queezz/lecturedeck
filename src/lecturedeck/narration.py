"""Markdown narration skeletons and JSON outlines of a deck's visible content.

``lecturedeck narration`` turns what the audience sees on each slide into a
Markdown skeleton for spoken-text translation, plus a JSON outline that other
tools can code against. Both carry the sha256 of the deck file, so a
narration written against one revision can detect later edits.

Everything here is a pure function over deck data; nothing reads beyond the
deck file. HTML-bearing fields pass through one ``html.parser`` converter;
MathML is linearized from the same tree, because ElementTree rejects
MathML's named entities.

Anchors carry ids and unit names exactly as authored. Ids are lowercase
kebab-case (legacy slides.js ids are held to the deck.json rule), so one
containing ``--`` appears verbatim inside its HTML comment, which HTML5
permits; every anchor keeps a space before the closing ``-->``. Decoded text
that would read as a raw tag in Markdown is escaped (``<v>`` -> ``&lt;v>``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path

from . import __version__
from .deckdata import _ID, FIGURE_LAYOUTS, effective_layout, validate_deck_file

OUTLINE_SCHEMA = 1
LEGACY_REFUSAL = "narration needs deck.json; this slides.js is not a plain JSON literal"

_BOM = b"\xef\xbb\xbf"
_LEGACY_PREFIX = re.compile(r"\s*window\.LECTUREDECK\s*=\s*")
_LEGACY_SUFFIX = re.compile(r"\s*;?\s*")


# --------------------------------------------------------------------------
# Deck input


class NarrationError(Exception):
    """A deck the narration command refuses; ``errors`` holds every reason."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def _normalized(raw: bytes) -> bytes:
    if raw.startswith(_BOM):
        raw = raw[len(_BOM):]
    return raw.replace(b"\r\n", b"\n")


def deck_digest(raw: bytes) -> str:
    """sha256 of deck bytes with a leading UTF-8 BOM dropped and CRLF as LF."""
    return sha256(_normalized(raw)).hexdigest()


def legacy_deck_data(text: str) -> dict | None:
    """Parse ``window.LECTUREDECK = {...};`` when the object is plain JSON."""
    text = text.lstrip("\ufeff")
    prefix = _LEGACY_PREFIX.match(text)
    if prefix is None:
        return None
    try:
        data, end = json.JSONDecoder().raw_decode(text, prefix.end())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not _LEGACY_SUFFIX.fullmatch(text, end):
        return None
    return data


def _legacy_errors(data: dict) -> list[str]:
    """Structure narration needs from a legacy deck: slides with stable ids."""
    errors: list[str] = []
    if "meta" in data and not isinstance(data["meta"], dict):
        errors.append("slides.js: meta must be an object")
    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        return [*errors, "slides.js: slides must be a non-empty list"]
    seen: set[str] = set()
    starts = 0
    for position, slide in enumerate(slides):
        where = f"slides.js: slides[{position}]"
        if not isinstance(slide, dict):
            errors.append(f"{where} must be an object")
            continue
        slide_id = slide.get("id")
        if not isinstance(slide_id, str) or not _ID.fullmatch(slide_id):
            errors.append(f"{where}.id must be a lowercase kebab-case identifier")
        elif slide_id in seen:
            errors.append(f"slides.js: duplicate slide id {slide_id!r}")
        else:
            seen.add(slide_id)
        starts += slide.get("appendix") is True
    if starts > 1:
        errors.append("slides.js: only one slide may set appendix to true")
    return errors


def read_deck(path: Path) -> tuple[dict, str]:
    """Load and check a deck.json (or plain-JSON legacy slides.js).

    Returns ``(data, sha256)``; raises NarrationError for a refused deck.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise NarrationError([f"{path.name}: unreadable ({exc})"]) from exc
    digest = deck_digest(raw)
    if path.suffix.lower() == ".js":
        try:
            data = legacy_deck_data(_normalized(raw).decode("utf-8"))
        except UnicodeDecodeError:
            data = None
        if data is None:
            raise NarrationError([LEGACY_REFUSAL])
        errors = _legacy_errors(data)
    else:
        errors = validate_deck_file(path)
        data = None if errors else json.loads(_normalized(raw).decode("utf-8"))
    if errors:
        raise NarrationError(errors)
    return data, digest


# --------------------------------------------------------------------------
# Numbering and chapters


@dataclass(frozen=True)
class Numbering:
    """Port of lecturedeck.js slideNumbering: the appendix is a suffix, and
    review slides before it (H1, H2, ...) leave the main count."""

    total: int
    start: int | None
    reviews: frozenset[int] = frozenset()

    def in_appendix(self, index: int) -> bool:
        return self.start is not None and index >= self.start

    def in_review(self, index: int) -> bool:
        return not self.in_appendix(index) and index in self.reviews

    @property
    def review_total(self) -> int:
        return sum(1 for index in self.reviews if not self.in_appendix(index))

    @property
    def main_total(self) -> int:
        end = self.total if self.start is None else self.start
        return end - self.review_total

    @property
    def backup_total(self) -> int:
        return 0 if self.start is None else self.total - self.start

    def label(self, index: int) -> str:
        if self.in_appendix(index):
            return f"B{index - self.start + 1}"
        same = sum(1 for i in range(index + 1) if self.in_review(i) == self.in_review(index))
        return f"H{same}" if self.in_review(index) else str(same)


def numbering(slides: list) -> Numbering:
    start = next(
        (
            position
            for position, slide in enumerate(slides)
            if isinstance(slide, dict) and slide.get("appendix") is True
        ),
        None,
    )
    reviews = frozenset(
        position
        for position, slide in enumerate(slides)
        if isinstance(slide, dict) and slide.get("review") is True
    )
    return Numbering(len(slides), start, reviews)


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _same(first: str, second: str) -> bool:
    return first.casefold() == second.casefold()


def _section_title(slide: dict) -> str:
    return plain_text(_string(slide.get("title"))) or plain_text(
        _string(slide.get("eyebrow"))
    ) or _string(slide.get("id"))


def chapters(data: dict) -> list[dict]:
    """Group slides into chapters: {"title", "backup", "indices"}."""
    slides = data["slides"]
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    marks = numbering(slides)
    opening = plain_text(_string(meta.get("opening"))) or "Opening"
    has_sections = any(slide.get("type") == "section" for slide in slides)
    result: list[dict] = []

    def start(title: str, backup: bool) -> dict:
        chapter = {"title": title, "backup": backup, "indices": []}
        result.append(chapter)
        return chapter

    current = None
    for index, slide in enumerate(slides):
        backup = marks.in_appendix(index)
        if index == marks.start:
            if slide.get("type") == "section":
                title = _section_title(slide)
            else:
                title = plain_text(_string(slide.get("eyebrow"))) or "Backup"
            current = start(title, True)
        elif slide.get("type") == "section":
            current = start(_section_title(slide), backup)
        elif not has_sections:
            eyebrow = plain_text(_string(slide.get("eyebrow")))
            if eyebrow and (current is None or not _same(eyebrow, current["title"])):
                current = start(eyebrow, backup)
        if current is None:
            current = start(opening, False)
        current["indices"].append(index)
    return result


def slide_title(slide: dict, index: int) -> str:
    """Plain title the way the viewer's labels name a slide."""
    title = plain_text(_string(slide.get("title")))
    for block in ("interactive", "video"):
        if not title and isinstance(slide.get(block), dict):
            title = _squash(_string(slide[block].get("title"))).strip()
    return title or f"Slide {index + 1}"


def outline(data: dict, *, unit: str, deck: str, digest: str) -> dict:
    """The JSON outline contract (schema 1)."""
    slides = data["slides"]
    marks = numbering(slides)
    return {
        "schema": OUTLINE_SCHEMA,
        "lecturedeck": __version__,
        "unit": unit,
        "deck": deck,
        "sha256": digest,
        "main_total": marks.main_total,
        "backup_total": marks.backup_total,
        **({"review_total": marks.review_total} if marks.review_total else {}),
        "chapters": [
            {
                "title": chapter["title"],
                "backup": chapter["backup"],
                "slides": [
                    {
                        "id": slides[index]["id"],
                        "label": marks.label(index),
                        "index": index,
                        "title": slide_title(slides[index], index),
                    }
                    for index in chapter["indices"]
                ],
            }
            for chapter in chapters(data)
        ],
    }


# --------------------------------------------------------------------------
# Markdown skeleton


def skeleton(data: dict, *, unit: str, digest: str) -> str:
    """The Markdown narration skeleton, LF newlines, ending in one newline."""
    slides = data["slides"]
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    marks = numbering(slides)
    backup = (
        f"backup B1-B{marks.backup_total}" if marks.start is not None else "no backup"
    )
    if marks.review_total:
        backup = f"review H1-H{marks.review_total}; {backup}"
    parts = [
        f"<!-- deck: {unit} sha256 {digest} -->\n"
        f"<!-- lecturedeck {__version__} narration skeleton; "
        f"{marks.main_total} main slides; {backup} -->"
    ]

    def nav(target: str) -> tuple[str, str] | None:
        # "#/N" names a slide; "#/N.k" also names the step it opens at.
        number, dot, step = target.partition(".")
        if not number.isdigit() or not number.isascii():
            return None
        if dot and (not step.isdigit() or not step.isascii()):
            return None
        position = int(number)
        if position >= len(slides):
            return None
        label = marks.label(position)
        if dot and int(step):
            label += f", step {int(step)}"
        return _string(slides[position].get("id")), label

    markdown = _Markdown(nav=nav)
    labels = _part_labels(slides, meta)
    announced = False
    for chapter in chapters(data):
        heading = f"## {_no_tags(chapter['title'])}"
        if chapter["backup"] and not announced:
            announced = True
            first = _string(slides[marks.start].get("id"))
            heading = f"<!-- backup: starts at {first} (B1) -->\n{heading}"
        parts.append(heading)
        for index in chapter["indices"]:
            parts.append(
                _slide_text(slides[index], markdown, labels[index], chapter["title"])
            )
    return "\n\n".join(parts) + "\n"


def _part_labels(slides: list, meta: dict) -> list[str]:
    """Label each slide inherits from its part, ignoring its own eyebrow."""
    part = plain_text(_string(meta.get("opening"))) or "OPENING"
    inherited = []
    for slide in slides:
        if slide.get("type") == "section":
            title = plain_text(_string(slide.get("title")))
            inherited.append(title or part)
            part = plain_text(_string(slide.get("eyebrow"))) or title or part
        else:
            inherited.append(part)
    return inherited


def _figures(slide: dict) -> list[dict]:
    if isinstance(slide.get("figures"), list):
        return [figure for figure in slide["figures"] if isinstance(figure, dict)]
    if isinstance(slide.get("figure"), dict):
        return [slide["figure"]]
    return []


def _slide_text(slide: dict, markdown: _Markdown, inherited: str, chapter: str) -> str:
    chrome = slide.get("chrome") is not False
    blocks: list[str] = []
    eyebrow = plain_text(_string(slide.get("eyebrow")))
    if chrome and eyebrow and not _same(eyebrow, inherited) and not _same(eyebrow, chapter):
        blocks.append(f"Eyebrow: {_no_tags(eyebrow)}")
    title = plain_text(_string(slide.get("title")))
    if title:
        blocks.append(f"**{_no_tags(title)}**" + ("" if chrome else " (title not shown)"))
    blocks.extend(markdown.convert(_string(slide.get("claim"))))
    blocks.extend(_formula_blocks(slide.get("formula"), markdown))
    blocks.extend(markdown.convert(_string(slide.get("body"))))
    quote = markdown.convert(_string(slide.get("quote")))
    if quote:
        blocks.append(_quoted("\n\n".join(quote)))
    blocks.extend(_layout_blocks(slide, markdown))
    source = markdown.line(_string(slide.get("source")))
    if source:
        blocks.append(("Source: " if chrome else "Source (not shown): ") + source)
    anchor = f"<!-- slide: {_string(slide.get('id'))} -->"
    return "\n".join([anchor, "\n\n".join(blocks)]) if blocks else anchor


def _layout_blocks(slide: dict, markdown: _Markdown) -> list[str]:
    layout = effective_layout(slide)
    if layout in FIGURE_LAYOUTS:
        return _figure_blocks(_figures(slide), markdown)
    if layout == "cards" and isinstance(slide.get("cards"), list):
        lines = [_card_line(card, markdown) for card in slide["cards"] if isinstance(card, dict)]
        lines = [line for line in lines if line]
        return ["\n".join(lines)] if lines else []
    if layout == "interactive" and isinstance(slide.get("interactive"), dict):
        interactive = slide["interactive"]
        title = _inline_text(_string(interactive.get("title"))) or "Interactive demonstration"
        return [f"[interactive: {title}] {_asset_path(_string(interactive.get('src')))}"]
    if layout == "video" and isinstance(slide.get("video"), dict):
        video = slide["video"]
        title = _inline_text(_string(video.get("title"))) or "Lecture video"
        details = [
            markdown.line(_string(video.get("caption"))),
            markdown.line(_string(video.get("source"))),
        ]
        url = _inline_text(_string(video.get("originalUrl")))
        if url:
            details.append(f"original: {url}")
        details = [detail for detail in details if detail]
        return [f"[video: {title}]" + (f" {' / '.join(details)}" if details else "")]
    return []


_THEME_SUFFIX = re.compile(r"-(?:dark|light)(?=[^/]*$)")


def _theme_pair(first: dict, second: dict) -> bool:
    one, two = _string(first.get("src")), _string(second.get("src"))
    return (
        one != two
        and _THEME_SUFFIX.sub("-*", one) == _THEME_SUFFIX.sub("-*", two)
        and first.get("alt") == second.get("alt")
        and first.get("caption") == second.get("caption")
    )


def _figure_blocks(figures: list[dict], markdown: _Markdown) -> list[str]:
    blocks = []
    folded: set[int] = set()
    for position, figure in enumerate(figures):
        if position in folded:
            continue
        twin = next(
            (
                other
                for other in range(position + 1, len(figures))
                if other not in folded and _theme_pair(figure, figures[other])
            ),
            None,
        )
        name = _inline_text(_string(figure.get("id"))) or str(position + 1)
        line = f"[figure {name}] {_asset_path(_string(figure.get('src')))}"
        if twin is not None:
            folded.add(twin)
            line += " (dark/light pair)"
        alt = _inline_text(_string(figure.get("alt")))
        lines = [line, f"Alt: {alt or '(missing)'}"]
        caption = markdown.line(_string(figure.get("caption")))
        if caption:
            lines.append(f"Caption: {caption}")
        credit = markdown.line(_string(figure.get("source")))
        if credit:
            lines.append(f"Credit: {credit}")
        blocks.append("\n".join(lines))
    return blocks


def _card_line(card: dict, markdown: _Markdown) -> str:
    label = _no_tags(plain_text(_string(card.get("label"))))
    value = markdown.line(_string(card.get("value")))
    detail = markdown.line(_string(card.get("detail")))
    text = f"{value} — {detail}" if value and detail else value or detail
    if label:
        text = f"**{label}**" + (f": {text}" if text else "")
    return f"- {text}" if text else ""


def _fence(info: str, body: str) -> str:
    ticks = "```"
    while ticks in body:
        ticks += "`"
    return f"{ticks}{info}\n{body}\n{ticks}"


def _quoted(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _formula_blocks(formula: object, markdown: _Markdown) -> list[str]:
    if isinstance(formula, str):
        text = _lf(formula).strip("\n")
        return [_fence("formula", text)] if text.strip() else []
    if not isinstance(formula, dict):
        return []
    mathml = _string(formula.get("mathml"))
    source = mathml or _string(formula.get("html"))
    root = _parse(source)
    lines = []
    label = _squash(_string(formula.get("label"))).strip()
    if label:
        lines.append(f"label: {label}")
    linear = _formula_linear(root)
    if len(linear) == 1:
        lines.append(f"linear: {linear[0]}")
    elif linear:
        lines.append("linear:")
        lines.extend(f"  {line}" for line in linear)
    tex = [line for item in _tex_annotations(root) for line in item.split("\n") if line.strip()]
    if len(tex) == 1:
        lines.append(f"tex: {tex[0].strip()}")
    elif tex:
        lines.append("tex:")
        lines.extend(f"  {line.rstrip()}" for line in tex)
    blocks = [_fence("formula", "\n".join(lines))] if lines else []
    if source.strip():
        blocks.append(_fence("mathml" if mathml else "html", _lf(source).strip()))
    gloss = formula.get("gloss")
    if isinstance(gloss, list):
        items = [markdown.line(item) for item in gloss if isinstance(item, str)]
        items = [f"- Gloss: {item}" for item in items if item]
        if items:
            blocks.append("\n".join(items))
    return blocks


def _asset_path(src: str) -> str:
    src = _inline_text(src)
    if not src:
        return "(no src)"
    if src.startswith("data:"):
        return "(embedded data)"
    if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:|/", src):
        return src
    return "webdeck/" + src.removeprefix("./")


# --------------------------------------------------------------------------
# HTML tree


_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
     "param", "source", "track", "wbr"}
)
_FOREIGN = frozenset({"math", "svg"})
_BLOCK = frozenset(
    {"address", "article", "aside", "blockquote", "caption", "dd", "details", "dialog",
     "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2",
     "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "li", "main", "nav", "ol", "p",
     "pre", "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
     "ul"}
)
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP = frozenset({"script", "style", "template", "noscript", "head"})


class _Element:
    __slots__ = ("tag", "attrs", "children", "block")

    def __init__(self, tag: str, attrs=()):
        self.tag = tag
        self.attrs = {name: value or "" for name, value in attrs}
        self.children: list = []
        self.block: bool | None = None  # cached _Markdown.is_block

    def elements(self) -> list[_Element]:
        return [child for child in self.children if isinstance(child, _Element)]

    def text(self) -> str:
        return "".join(
            child if isinstance(child, str) else child.text() for child in self.children
        )


class _TreeBuilder(HTMLParser):
    """Lenient HTML tree; elements past MAX_DEPTH stay flat so walks never recurse deeper."""

    MAX_DEPTH = 200

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Element("#root")
        self.stack = [self.root]

    def _foreign(self) -> bool:
        return any(node.tag in _FOREIGN for node in self.stack)

    def _close(self, tags: set[str], stop: set[str]) -> None:
        for depth in range(len(self.stack) - 1, 0, -1):
            tag = self.stack[depth].tag
            if tag in tags:
                del self.stack[depth:]
                return
            if tag in stop:
                return

    def handle_starttag(self, tag, attrs):
        foreign = self._foreign()
        if not foreign:
            if tag == "li":
                self._close({"li"}, {"ul", "ol"})
            elif tag in ("td", "th"):
                self._close({"td", "th"}, {"tr", "table"})
            elif tag == "tr":
                self._close({"tr"}, {"table", "thead", "tbody", "tfoot"})
            if tag in _BLOCK and self.stack[-1].tag == "p":
                self.stack.pop()
        node = _Element(tag, attrs)
        self.stack[-1].children.append(node)
        if (foreign or tag not in _VOID) and len(self.stack) < self.MAX_DEPTH:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Element(tag, attrs))

    def handle_endtag(self, tag):
        for depth in range(len(self.stack) - 1, 0, -1):
            if self.stack[depth].tag == tag:
                del self.stack[depth:]
                return

    def handle_data(self, data):
        children = self.stack[-1].children
        if children and isinstance(children[-1], str):
            children[-1] += data
        else:
            children.append(data)


def _parse(html: str) -> _Element:
    builder = _TreeBuilder()
    builder.feed(_lf(html))
    builder.close()
    return builder.root


# Soft hyphen, zero-width characters, BOM, and MathML invisible operators.
_INVISIBLE = dict.fromkeys(
    map(ord, "\u00ad\u200b\u200c\u200d\u2060\u2061\u2062\u2063\u2064\ufeff")
)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_INVISIBLE))


_TAG_START = re.compile(r"<(?=[A-Za-z/!?])")
_COMMENT_END = re.compile(r"--+(?=!?>)")


def _no_tags(text: str) -> str:
    """Keep decoded text from reading as raw HTML in Markdown: ``<v>`` -> ``&lt;v>``."""
    return _TAG_START.sub("&lt;", text)


def _inline_text(text: str) -> str:
    """A plain value on one Markdown line: whitespace squashed, no raw tags."""
    return _no_tags(_squash(text).strip())


def _comment_safe(text: str) -> str:
    """Text that cannot end the HTML comment it sits in (``-->`` or ``--!>``)."""
    return _COMMENT_END.sub("-", _squash(text).strip())


def _bracketed(text: str) -> bool:
    """Whether one bracket pair encloses the whole text."""
    if len(text) < 2 or text[0] not in "([{" or text[-1] not in ")]}":
        return False
    depth = 0
    for position, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0 and position != len(text) - 1:
                return False
    return depth == 0


def _script(text: str) -> str:
    text = text.strip()
    return f"({text})" if len(text) > 1 and not _bracketed(text) else text


_TEX_HINT = re.compile(r"\\[A-Za-z]+|[\^_]\{|^\$.+\$$", re.DOTALL)


def _math_image(node: _Element) -> bool:
    classes = node.attrs.get("class", "").lower()
    if any(word in classes for word in ("math", "latex", "equation")):
        return True
    return bool(_TEX_HINT.search(node.attrs.get("alt", "").strip()))


def _tex_alt(alt: str) -> str:
    alt = _squash(alt).strip()
    for left, right in (("$$", "$$"), ("$", "$"), ("\\(", "\\)"), ("\\[", "\\]")):
        if len(alt) > len(left) + len(right) and alt.startswith(left) and alt.endswith(right):
            return alt[len(left):-len(right)].strip()
    return alt


def _paragraph(text: str, escape: bool = True) -> str:
    """Finish an inline run: trim lines, drop edge blanks, escape line starts."""
    lines = [re.sub(r" {2,}", " ", line).strip() for line in text.split("\n")]
    kept: list[str] = []
    for line in lines:
        if line or (kept and kept[-1]):
            kept.append(line)
    while kept and not kept[-1]:
        kept.pop()
    return "\n".join(_escape_line(line) if escape else line for line in kept)


_BARE_SCRIPT = re.compile(r"[_^][^\s()]$")


def _after_script(parts: list[str], piece: str) -> str:
    """Separate a bare one-character script from a following word: n_e T."""
    if parts and _BARE_SCRIPT.search(parts[-1]) and piece[:1].isalnum():
        return " " + piece
    return piece


def _escape_line(line: str) -> str:
    """Keep converted text from forming headings, fences or quotes."""
    if re.match(r"#{1,6}(?:\s|$)|>|```|~~~", line) or re.fullmatch(r"=+|-+", line):
        return "\\" + line
    return line


class _Markdown:
    """HTML fragment to Markdown (or plain text) for one deck.

    ``in_cell`` converts a table cell's contents: a table nested there
    becomes one line of text, since a pipe table cannot sit inside a cell.
    """

    def __init__(self, plain: bool = False, nav=None, in_cell: bool = False):
        self.plain = plain
        self.nav = nav
        self.in_cell = in_cell

    # Public entry points -------------------------------------------------

    def convert(self, html: str) -> list[str]:
        """Markdown blocks for an HTML fragment."""
        return self.blocks(_parse(html)) if html.strip() else []

    def line(self, html: str) -> str:
        """The fragment on one line."""
        return _squash(" ".join(self.convert(html))).strip()

    # Blocks --------------------------------------------------------------

    def is_block(self, node: _Element) -> bool:
        if node.block is None:
            if node.tag in _FOREIGN:
                node.block = node.tag == "math" and node.attrs.get("display") == "block"
            elif node.tag in _BLOCK:
                node.block = True
            elif node.tag == "img":
                node.block = not _math_image(node)
            else:
                node.block = any(
                    child.tag not in _SKIP and self.is_block(child)
                    for child in node.elements()
                )
        return node.block

    def blocks(self, node: _Element) -> list[str]:
        out: list[str] = []
        run: list[str] = []

        def flush():
            paragraph = _paragraph("".join(run), escape=not self.plain)
            run.clear()
            if paragraph:
                out.append(paragraph)

        for child in node.children:
            if isinstance(child, str):
                run.append(_after_script(run, self.text(child)))
            elif child.tag in _SKIP:
                continue
            elif self.is_block(child):
                flush()
                out.extend(self.block(child))
            else:
                run.append(_after_script(run, self.inline(child)))
        flush()
        return out

    def block(self, node: _Element) -> list[str]:
        tag = node.tag
        if tag == "math":
            math = self.math(node)
            return [math] if math else []
        if tag in ("ul", "ol"):
            items = self.list_block(node)
            return [items] if items else []
        if tag == "table":
            return self.table(node)
        if tag == "pre":
            text = node.text().translate(_INVISIBLE).strip("\n")
            if not text.strip():
                return []
            return [_squash(text).strip()] if self.plain else [_fence("", text)]
        if tag == "hr":
            return [] if self.plain else ["* * *"]
        if tag == "img":
            return [self.image(node)]
        if tag == "blockquote":
            inner = self.blocks(node)
            if not inner:
                return []
            return inner if self.plain else [_quoted("\n\n".join(inner))]
        if tag in _HEADINGS:
            text = _squash(" ".join(self.blocks(node))).strip()
            return [self.strong(text)] if text else []
        return self.blocks(node)

    def list_block(self, node: _Element) -> str:
        ordered = node.tag == "ol"
        start = node.attrs.get("start", "").strip()
        number = int(start) if ordered and start.isdigit() else 1
        lines: list[str] = []
        for child in node.children:
            if isinstance(child, str):
                item = [_paragraph(self.text(child), not self.plain)] if child.strip() else []
            elif child.tag in _SKIP:
                continue
            elif child.tag in ("ul", "ol"):
                nested = self.list_block(child)
                if nested:
                    lines.extend(f"  {line}" if line else "" for line in nested.split("\n"))
                continue
            elif child.tag == "li" or self.is_block(child):
                item = self.blocks(child)
            else:
                item = [_paragraph(self.inline(child), not self.plain)]
            item = [block for block in item if block]
            if not item:
                continue
            marker = f"{number}. " if ordered else "- "
            if ordered:
                number += 1
            body = "\n".join(item).split("\n")
            lines.append(marker + body[0])
            lines.extend(" " * len(marker) + line if line else "" for line in body[1:])
        return "\n".join(lines)

    def table(self, node: _Element) -> list[str]:
        caption: list[str] = []
        rows: list[list[str]] = []
        # Content outside any cell, which a browser moves out in front of the table.
        loose = _Element("#loose")

        def walk(parent: _Element):
            implied: list = []  # cells outside any <tr> form one row
            for child in parent.children:
                if isinstance(child, str) and not child.strip():
                    continue
                tag = child.tag if isinstance(child, _Element) else ""
                if tag in ("td", "th"):
                    implied.append(child)
                    continue
                if implied:
                    rows.append(self.row(implied, loose))
                    implied = []
                if tag == "caption":
                    caption.extend(self.blocks(child))
                elif tag in ("thead", "tbody", "tfoot"):
                    walk(child)
                elif tag == "tr":
                    rows.append(self.row(child.children, loose))
                elif tag not in ("colgroup", "col"):
                    loose.children.append(child)
            if implied:
                rows.append(self.row(implied, loose))

        walk(node)
        before = [*self.blocks(loose), *caption]
        rows = [row for row in rows if any(row)]
        if not rows:
            return before
        if self.plain:
            return [*before, " ".join(cell for row in rows for cell in row if cell)]
        if self.in_cell:
            lines = (" · ".join(cell for cell in row if cell) for row in rows)
            return [*before, "; ".join(lines)]
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        lines = [f"| {' | '.join(rows[0])} |", f"|{' --- |' * width}"]
        lines.extend(f"| {' | '.join(row)} |" for row in rows[1:])
        return [*before, "\n".join(lines)]

    def row(self, children: list, loose: _Element) -> list[str]:
        cells: list[str] = []
        outer = not (self.plain or self.in_cell)
        contents = _Markdown(nav=self.nav, in_cell=True) if outer else self
        for cell in children:
            if not isinstance(cell, _Element) or cell.tag not in ("td", "th"):
                if isinstance(cell, _Element) or cell.strip():
                    loose.children.append(cell)
                continue
            text = _squash(" ".join(contents.blocks(cell))).strip()
            if outer:
                text = text.replace("|", "\\|")
            span = cell.attrs.get("colspan", "").strip()
            cells.append(text)
            if span.isdigit() and int(span) > 1:
                cells.extend([""] * (min(int(span), 50) - 1))
        return cells

    # Inline --------------------------------------------------------------

    def text(self, value: str) -> str:
        value = _squash(value)
        return value if self.plain else _no_tags(value)

    def inline_children(self, node: _Element) -> str:
        parts: list[str] = []
        for child in node.children:
            if isinstance(child, str):
                piece = self.text(child)
            elif child.tag in _SKIP:
                continue
            else:
                piece = self.inline(child)
            parts.append(_after_script(parts, piece))
        return "".join(parts)

    def inline(self, node: _Element) -> str:
        tag = node.tag
        if tag == "br":
            return " " if self.plain else "\n"
        if tag in ("strong", "b"):
            return self.strong(self.inline_children(node))
        if tag in ("sub", "sup"):
            script = _script(_squash(self.inline_children(node)))
            return ("_" if tag == "sub" else "^") + script if script else ""
        if tag == "code":
            return self.code(node)
        if tag == "a":
            return self.link(node)
        if tag == "img":
            return self.image(node)
        if tag == "math":
            return self.math(node)
        if tag == "svg":
            label = _squash(node.attrs.get("aria-label", "")).strip()
            if not label:
                return ""
            return label if self.plain else f"[math: {_no_tags(label)}]"
        if self.is_block(node):
            return " " + " ".join(self.block(node)) + " "
        return self.inline_children(node)

    def strong(self, inner: str) -> str:
        core = inner.strip()
        if self.plain or not core:
            return inner
        lead = " " if inner[:1].isspace() else ""
        trail = " " if inner[-1:].isspace() else ""
        return f"{lead}**{core}**{trail}"

    def code(self, node: _Element) -> str:
        # A code span shows its text literally, so it takes plain text: no
        # Markdown emphasis inside, and a ``<`` that needs no escaping.
        inner = (self if self.plain else _Markdown(plain=True)).inline_children(node)
        core = inner.strip()
        if self.plain or not core:
            return inner
        if "`" in core:
            return f"`` {core} ``"
        return f"`{core}`"

    def link(self, node: _Element) -> str:
        inner = self.inline_children(node)
        if self.plain:
            return inner
        href = _squash(node.attrs.get("href", "")).strip()
        if href.startswith("#/"):
            label = _Markdown(plain=True).inline_children(node).replace('"', "'")
            label = _comment_safe(label)
            target = href[2:]
            resolved = self.nav(target) if self.nav else None
            if resolved:
                note = f'<!-- nav: "{label}" -> slide {resolved[0]} ({resolved[1]}) -->'
            else:
                note = f'<!-- nav: "{label}" -> slide unknown (#/{_comment_safe(target)}) -->'
            return f"{inner} {note}"
        if not href or href.startswith("#"):
            return inner
        core = inner.strip()
        if not core:
            return f"<{href}>"
        lead = " " if inner[:1].isspace() else ""
        trail = " " if inner[-1:].isspace() else ""
        return f"{lead}[{core}]({href}){trail}"

    def image(self, node: _Element) -> str:
        alt = node.attrs.get("alt", "")
        if _math_image(node):
            tex = _tex_alt(alt)
            if not tex:
                return ""
            return tex if self.plain else f"[math: {_no_tags(tex)}]"
        if self.plain:
            return _squash(alt).strip()
        alt = _inline_text(alt)
        return f"[figure] {_asset_path(node.attrs.get('src', ''))} Alt: {alt or '(missing)'}"

    def math(self, node: _Element) -> str:
        linear = "; ".join(_math_lines(node))
        if not linear:
            return ""
        return linear if self.plain else f"[math: {_no_tags(linear)}]"


def plain_text(html: str) -> str:
    """One line of plain text from an HTML fragment (math linearized)."""
    return _plain(_parse(html)) if html.strip() else ""


def _plain(root: _Element) -> str:
    return _squash(" ".join(_Markdown(plain=True).blocks(root))).strip()


def html_to_markdown(html: str) -> str:
    """Markdown for an HTML fragment; ``#/N`` links resolve to unknown."""
    return "\n\n".join(_Markdown().convert(html))


# --------------------------------------------------------------------------
# MathML


_TOKENS = frozenset({"mi", "mn", "mtext", "ms"})
_SCRIPTED = frozenset(
    {"msub", "msup", "msubsup", "mover", "munder", "munderover", "mmultiscripts"}
)
_SILENT = frozenset(
    {"mphantom", "annotation", "annotation-xml", "none", "mprescripts", "malignmark",
     "maligngroup"}
)
_UNWRAP = frozenset({"math", "mrow", "mstyle", "mpadded", "menclose", "merror", "mtd"})
_ATOMS = frozenset(
    {"mi", "mn", "mo", "mtext", "ms", "msub", "msup", "msubsup", "mover", "munder",
     "munderover", "msqrt", "mroot", "mfenced", "mglyph"}
)
_RELATIONS = frozenset("=<>≤≥≈∝→≡∼≠⇒⇔←↔⟶⟹⟺↦≪≫≲≳≃≅") | {"≔", ":="}
_BINARY = frozenset("+−-±∓×÷")
_OPENERS = frozenset("([{⟨")
_PRIMES = frozenset("′″‴⁗'")
_LARGE_SIGNS = frozenset("∑∏∐∫∬∭∮⋃⋂⨁⨂⨀⋁⋀")
_LARGE = _LARGE_SIGNS | {"lim", "max", "min", "sup", "inf", "limsup", "liminf"}
_OVER_ACCENTS = {
    "^": "hat", "ˆ": "hat", "\u0302": "hat",
    "¯": "bar", "‾": "bar", "\u0304": "bar", "\u0305": "bar",
    ".": "dot", "˙": "dot", "\u0307": "dot",
    "¨": "ddot", "..": "ddot", "\u0308": "ddot",
    "~": "tilde", "˜": "tilde", "\u0303": "tilde", "∼": "tilde",
    "→": "vec", "\u20d7": "vec", "⇀": "vec", "⟶": "vec",
}
_UNDER_ACCENTS = {"_": "underline", "\u0332": "underline", "¯": "underline", "‾": "underline"}
_TEX_ENCODINGS = frozenset({"application/x-tex", "application/x-latex", "text/x-tex"})


def _token(node: _Element) -> str:
    text = node.text().translate(_INVISIBLE).strip(" \t\n\r\f")
    return re.sub(r"\s+", " ", text)


def _one_line(text: str) -> str:
    return "; ".join(line.strip() for line in text.split("\n") if line.strip())


def _unwrapped(node):
    while isinstance(node, _Element):
        if node.tag == "semantics":
            inner = [child for child in node.elements() if not child.tag.startswith("annotation")]
            if not inner:
                break
            node = inner[0]
            continue
        if node.tag not in _UNWRAP:
            break
        stray = any(isinstance(child, str) and child.strip() for child in node.children)
        children = node.elements()
        if stray or len(children) != 1:
            break
        node = children[0]
    return node


def _is_atom(node) -> bool:
    node = _unwrapped(node)
    return isinstance(node, str) or node.tag in _ATOMS


def _operand(node: _Element) -> str:
    text = _one_line(_linear(node)).strip()
    return text if _is_atom(node) or _bracketed(text) else f"({text})"


def _linear(node) -> str:
    """Linear text for a MathML node; table rows become separate lines."""
    if isinstance(node, str):
        return _squash(node).strip()
    tag = node.tag
    children = node.elements()
    if tag in _TOKENS or tag == "mo":
        return _token(node)
    if tag == "mspace":
        return " "
    if tag in _SILENT:
        return ""
    if tag == "semantics":
        inner = [child for child in children if not child.tag.startswith("annotation")]
        return _linear(inner[0]) if inner else ""
    if tag == "maction":
        return _linear(children[0]) if children else ""
    if tag == "mglyph":
        return node.attrs.get("alt", "")
    if tag == "mfrac" and len(children) >= 2:
        return f"{_operand(children[0])}/{_operand(children[1])}"
    if tag in ("msub", "msup", "msubsup", "mover", "munder", "munderover") and children:
        return _scripted(tag, node, children)
    if tag == "msqrt":
        return f"sqrt({_one_line(_concat(node.children)).strip()})"
    if tag == "mroot" and len(children) >= 2:
        index = _one_line(_linear(children[1])).strip()
        return f"root({index})({_one_line(_linear(children[0])).strip()})"
    if tag == "mfenced":
        return _fenced(node, children)
    if tag == "mtable":
        rows = (_linear(row) for row in children)
        return "\n".join(row for row in rows if row.strip())
    if tag in ("mtr", "mlabeledtr"):
        cells = children[1:] if tag == "mlabeledtr" else children
        texts = (_one_line(_linear(cell)).strip() for cell in cells)
        return " ".join(text for text in texts if text)
    if tag == "mmultiscripts" and children:
        return _multiscripts(children)
    return _concat(node.children)


def _concat(nodes: list) -> str:
    """Join sibling pieces, spacing relations, binary operators and words.

    A space also follows a scripted term or a fraction and precedes a
    fraction or large operator that comes after a term, so juxtaposed
    factors stay readable: ``a/π Δk``, ``ΔS ∫_0^1``, ``n_e T_e``.
    """
    out = ""
    previous = "start"  # start | op | term
    previous_wordy = previous_scripted = previous_fraction = False
    for node in nodes:
        fraction = False
        if isinstance(node, str):
            piece = _squash(node).strip()
            if not piece:
                continue
            kind, wordy = "term", True
        elif node.tag == "mspace":
            width = node.attrs.get("width", "").strip().lower()
            if not width.startswith("-") and "negative" not in width:
                out += " "
            continue
        elif node.tag == "mo":
            symbol = _token(node)
            if not symbol:
                continue
            form = node.attrs.get("form", "")
            wordy = len(symbol) > 1 and symbol.isalpha()
            if symbol in _RELATIONS:
                piece, kind = f" {symbol} ", "op"
            elif symbol in _BINARY and form != "prefix" and (
                previous == "term" or form == "infix"
            ):
                piece, kind = f" {symbol} ", "op"
            elif symbol in (",", ";"):
                piece, kind = f"{symbol} ", "op"
            elif symbol in _BINARY or symbol in _OPENERS:
                piece, kind = symbol, "op"
            else:
                piece, kind = symbol, "term"
        else:
            piece = _linear(node)
            if not piece.strip():
                if piece:  # a no-break space in mtext keeps its gap
                    out += " "
                continue
            kind = "term"
            wordy = node.tag in ("mi", "mtext") and len(piece) > 1
            core = _unwrapped(node)
            fraction = isinstance(core, _Element) and core.tag == "mfrac"
        if piece[:1].isalnum() and (
            previous_scripted or ((wordy or previous_wordy) and out[-1:].isalnum())
        ):
            out += " "
        elif previous_fraction and (kind == "term" or piece[:1] in _OPENERS):
            out += " "
        elif previous == "term" and (fraction or piece[:1] in _LARGE_SIGNS):
            out += " "
        out += piece
        previous, previous_wordy = kind, wordy
        previous_scripted = isinstance(node, _Element) and node.tag in _SCRIPTED
        previous_fraction = fraction
    return out


def _scripted(tag: str, node: _Element, children: list) -> str:
    base = children[0]
    base_text = _one_line(_linear(base)).strip()
    core = _unwrapped(base)
    large = isinstance(core, _Element) and core.tag in ("mo", "mi") and _token(core) in _LARGE
    if tag in ("mover", "munder") and len(children) >= 2 and not large:
        script = children[1]
        if script.tag in ("mo", "mi", "mtext"):
            accents = _OVER_ACCENTS if tag == "mover" else _UNDER_ACCENTS
            name = accents.get(_token(script))
            if name:
                return f"{name}({base_text})"
    if not (_is_atom(base) or _bracketed(base_text)):
        base_text = f"({base_text})"
    scripts = [_one_line(_linear(child)).strip() for child in children[1:3]] + ["", ""]
    if tag in ("msup", "mover"):
        lower, upper = "", scripts[0]
    elif tag in ("msub", "munder"):
        lower, upper = scripts[0], ""
    else:
        lower, upper = scripts[0], scripts[1]
    text = base_text
    if upper and all(char in _PRIMES for char in upper):
        text, upper = text + upper, ""  # primes attach to the base: q″_net
    if lower:
        text += "_" + _script(lower)
    if upper:
        text += "^" + _script(upper)
    return text


def _fenced(node: _Element, children: list) -> str:
    opener = node.attrs["open"] if "open" in node.attrs else "("
    closer = node.attrs["close"] if "close" in node.attrs else ")"
    separators = "".join(node.attrs.get("separators", ",").split()) if (
        "separators" in node.attrs
    ) else ","
    parts = [_one_line(_linear(child)).strip() for child in children]
    text = parts[0] if parts else ""
    for position, part in enumerate(parts[1:]):
        separator = separators[min(position, len(separators) - 1)] if separators else ""
        text += separator + (" " if separator in ",;" and separator else "") + part
    return f"{opener}{text}{closer}"


def _multiscripts(children: list) -> str:
    base, rest = children[0], children[1:]
    split = next((i for i, child in enumerate(rest) if child.tag == "mprescripts"), None)
    post, pre = (rest, []) if split is None else (rest[:split], rest[split + 1:])

    def pairs(items: list) -> str:
        text = ""
        for position in range(0, len(items), 2):
            sub = items[position]
            sup = items[position + 1] if position + 1 < len(items) else None
            if sub.tag != "none":
                text += "_" + _script(_one_line(_linear(sub)))
            if sup is not None and sup.tag != "none":
                text += "^" + _script(_one_line(_linear(sup)))
        return text

    base_text = _one_line(_linear(base)).strip()
    return pairs(pre) + base_text + pairs(post)


def _tidy(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = re.sub(r"([(\[{]) ", r"\1", line)
    line = re.sub(r" ([)\]},;])", r"\1", line)
    return line


def _math_lines(node: _Element) -> list[str]:
    lines = (_tidy(line) for line in _linear(node).split("\n"))
    return [line for line in lines if line]


def _math_elements(node: _Element) -> list[_Element]:
    found = []
    for child in node.elements():
        if child.tag == "math":
            found.append(child)
        else:
            found.extend(_math_elements(child))
    return found


def _formula_linear(root: _Element) -> list[str]:
    maths = _math_elements(root)
    if not maths:
        text = _plain(root)
        return [text] if text else []
    return [line for math in maths for line in _math_lines(math)]


def _tex_annotations(node: _Element) -> list[str]:
    found = []
    for child in node.elements():
        if child.tag == "annotation":
            if child.attrs.get("encoding", "").strip().lower() in _TEX_ENCODINGS:
                text = child.text().strip()
                if text:
                    found.append(text)
        else:
            found.extend(_tex_annotations(child))
    return found


def mathml_linear(mathml: str) -> str:
    """Linear text for a MathML fragment; table rows on separate lines."""
    return "\n".join(_formula_linear(_parse(mathml)))


def mathml_tex(mathml: str) -> list[str]:
    """Every TeX annotation carried by a MathML fragment."""
    return _tex_annotations(_parse(mathml))
