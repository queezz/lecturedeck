"""Narration skeleton and outline: a Markdown view of a deck's visible text."""

import errno
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from unittest.mock import patch

import lecturedeck
from lecturedeck import __version__
from lecturedeck.cli import main, write_stdout
from lecturedeck.narration import (
    deck_digest,
    html_to_markdown,
    mathml_linear,
    mathml_tex,
    numbering,
    outline,
    plain_text,
    skeleton,
)
from lecturedeck.scaffold import scaffold_unit

DIGEST = "0" * 64


def base_deck(slides: list, **meta) -> dict:
    return {"deck": 1, "meta": {"title": "Sample deck", **meta}, "slides": slides}


def make_json_unit(root, deck: dict, name: str = "unit") -> Path:
    unit = Path(root) / name
    unit.mkdir(parents=True)
    scaffold_unit(unit, "Sample deck")
    (unit / "webdeck" / "deck.json").write_text(
        json.dumps(deck, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return unit


def render(slides: list, **meta) -> str:
    return skeleton(base_deck(slides, **meta), unit="unit", digest=DIGEST)


def run_cli(*argv, encoding: str = "utf-8") -> tuple[int, bytes, str]:
    raw = BytesIO()
    stdout = TextIOWrapper(raw, encoding=encoding)
    stderr = StringIO()
    with patch("lecturedeck.cli.sys.stdout", stdout), redirect_stderr(stderr):
        code = main([str(arg) for arg in argv])
    stdout.flush()
    return code, raw.getvalue(), stderr.getvalue()


SECTIONED = [
    {"id": "opening", "type": "title", "title": "Sample deck"},
    {"id": "agenda", "title": "Agenda"},
    {"id": "part-a", "type": "section", "title": "Part A"},
    {"id": "a-one", "title": "First idea"},
    {"id": "backup", "type": "section", "title": "Backup", "appendix": True},
    {"id": "backup-one", "title": "Detail one"},
    {"id": "more-backup", "type": "section", "title": "More backup"},
    {"id": "backup-two", "title": "Detail two"},
]


class ChapterTest(unittest.TestCase):
    def chapters(self, slides, **meta):
        document = outline(base_deck(slides, **meta), unit="unit", deck="d", digest=DIGEST)
        return [
            (chapter["title"], chapter["backup"], [s["label"] for s in chapter["slides"]])
            for chapter in document["chapters"]
        ]

    def test_appendix_on_a_section_with_several_backup_sections(self):
        self.assertEqual(
            [
                ("Opening", False, ["1", "2"]),
                ("Part A", False, ["3", "4"]),
                ("Backup", True, ["B1", "B2"]),
                ("More backup", True, ["B3", "B4"]),
            ],
            self.chapters(SECTIONED),
        )
        text = render(SECTIONED)
        lines = text.split("\n")
        self.assertEqual(f"<!-- deck: unit sha256 {DIGEST} -->", lines[0])
        self.assertEqual(
            f"<!-- lecturedeck {__version__} narration skeleton; 4 main slides; "
            "backup B1-B4 -->",
            lines[1],
        )
        self.assertIn("<!-- backup: starts at backup (B1) -->\n## Backup\n", text)
        self.assertEqual(1, text.count("<!-- backup:"))
        headings = [line for line in lines if line.startswith("#")]
        self.assertEqual(
            ["## Opening", "## Part A", "## Backup", "## More backup"], headings
        )

    def test_appendix_on_a_content_slide_opens_a_backup_chapter(self):
        slides = [
            {"id": "part-a", "type": "section", "title": "Part A"},
            {"id": "a-one", "title": "Idea"},
            {"id": "extra", "title": "Extra detail", "appendix": True},
            {"id": "extra-two", "title": "More detail"},
        ]
        self.assertEqual(
            [("Part A", False, ["1", "2"]), ("Backup", True, ["B1", "B2"])],
            self.chapters(slides),
        )
        slides[2]["eyebrow"] = "Reference"
        self.assertEqual("Reference", self.chapters(slides)[1][0])
        self.assertIn(
            "<!-- backup: starts at extra (B1) -->\n## Reference", render(slides)
        )

    def test_no_appendix_numbers_every_slide(self):
        slides = [{"id": "one", "title": "One"}, {"id": "two", "title": "Two"}]
        marks = numbering(slides)
        self.assertEqual((2, 0, None), (marks.main_total, marks.backup_total, marks.start))
        text = render(slides)
        self.assertIn("; 2 main slides; no backup -->", text.split("\n")[1])
        self.assertNotIn("<!-- backup:", text)
        self.assertEqual([("Opening", False, ["1", "2"])], self.chapters(slides))

    def test_slides_before_the_first_section_use_the_opening_label(self):
        self.assertEqual("Welcome", self.chapters(SECTIONED, opening="Welcome")[0][0])
        self.assertEqual(
            "Bold welcome", self.chapters(SECTIONED, opening="<b>Bold</b> welcome")[0][0]
        )

    def test_without_sections_eyebrow_changes_start_chapters(self):
        slides = [
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B", "eyebrow": "Warm-up"},
            {"id": "c", "title": "C", "eyebrow": "Warm-up"},
            {"id": "d", "title": "D"},
            {"id": "e", "title": "E", "eyebrow": "Practice"},
        ]
        self.assertEqual(
            [
                ("Start", False, ["1"]),
                ("Warm-up", False, ["2", "3", "4"]),
                ("Practice", False, ["5"]),
            ],
            self.chapters(slides, opening="Start"),
        )
        self.assertNotIn("Eyebrow:", render(slides))

    def test_without_sections_or_eyebrows_the_deck_is_one_chapter(self):
        slides = [{"id": "a", "title": "A"}, {"id": "b"}, {"id": "c", "title": "C"}]
        self.assertEqual([("Opening", False, ["1", "2", "3"])], self.chapters(slides))

    def test_html_titles_become_plain_text(self):
        slides = [
            {"id": "part-two", "type": "section", "title": "Part <em>two</em>"},
            {"id": "look", "title": "A <em>first</em><br>look at x<sub>i</sub>"},
        ]
        text = render(slides)
        self.assertIn("## Part two\n", text)
        self.assertIn("**A first look at x_i**", text)
        document = outline(base_deck(slides), unit="u", deck="d", digest=DIGEST)
        self.assertEqual("A first look at x_i", document["chapters"][0]["slides"][1]["title"])

    def test_double_hyphen_ids_are_emitted_verbatim(self):
        text = skeleton(
            base_deck([{"id": "part--two", "title": "T"}]), unit="unit--b", digest=DIGEST
        )
        self.assertIn("<!-- slide: part--two -->", text)
        self.assertTrue(text.startswith("<!-- deck: unit--b sha256 "))


class ContentTest(unittest.TestCase):
    def test_nav_links_resolve_into_backup_and_back(self):
        slides = [
            {"id": "opening", "title": "Start",
             "body": '<p>See <a href="#/3">the detail</a>.</p>'},
            {"id": "middle", "title": "Middle",
             "claim": 'Lost: <a href="#/99">gone</a>; <a href="#/x">odd</a>'},
            {"id": "backup", "type": "section", "title": "Backup", "appendix": True},
            {"id": "detail", "title": "Detail",
             "body": '<a href="#/0">back</a> and <a href="https://example.com/r">a ref</a>'},
        ]
        text = render(slides)
        self.assertIn(
            'See the detail <!-- nav: "the detail" -> slide detail (B2) -->.', text
        )
        self.assertIn('back <!-- nav: "back" -> slide opening (1) -->', text)
        self.assertIn('gone <!-- nav: "gone" -> slide unknown (#/99) -->', text)
        self.assertIn('odd <!-- nav: "odd" -> slide unknown (#/x) -->', text)
        self.assertIn("and [a ref](https://example.com/r)", text)

    def test_string_formula_is_fenced_verbatim(self):
        text = render([{"id": "f", "title": "F", "formula": "y = a·x + b  (plain)"}])
        self.assertIn("```formula\ny = a·x + b  (plain)\n```", text)

    def test_formula_object_with_tex_annotation_and_gloss(self):
        mathml = (
            "<math display='block'><semantics><mrow><mi>y</mi><mo>=</mo><mi>a</mi>"
            "<mi>x</mi><mo>+</mo><mi>b</mi></mrow>"
            '<annotation encoding="application/x-tex">y = a x + b</annotation>'
            "</semantics></math>"
        )
        formula = {"label": "Line", "mathml": mathml,
                   "gloss": ["<em>a</em> is the slope", "b is the offset"]}
        text = render([{"id": "f", "title": "F", "formula": formula}])
        self.assertIn(
            "```formula\nlabel: Line\nlinear: y = ax + b\ntex: y = a x + b\n```", text
        )
        self.assertIn(f"```mathml\n{mathml}\n```", text)
        self.assertIn("- Gloss: a is the slope\n- Gloss: b is the offset", text)

    def test_formula_object_without_tex_has_no_tex_line(self):
        mathml = "<math><msup><mi>x</mi><mn>2</mn></msup></math>"
        text = render([{"id": "f", "title": "F", "formula": {"mathml": mathml}}])
        self.assertIn("```formula\nlinear: x^2\n```", text)
        self.assertNotIn("tex:", text)

    def test_multi_row_formula_lists_each_row(self):
        mathml = (
            '<math><mtable columnalign="right left">'
            "<mtr><mtd><mi>y</mi></mtd><mtd><mo>=</mo><mi>a</mi><mo>+</mo><mi>b</mi></mtd></mtr>"
            "<mtr><mtd></mtd><mtd><mo>=</mo><mi>c</mi></mtd></mtr></mtable></math>"
        )
        text = render([{"id": "f", "title": "F", "formula": {"mathml": mathml}}])
        self.assertIn("```formula\nlinear:\n  y = a + b\n  = c\n```", text)

    def test_body_with_table_lists_scripts_and_inline_math(self):
        body = (
            "<p>Values x<sub>1</sub>y<sup>10</sup> and n<sub>e</sub>T.</p>"
            '<table><tr><th>Name</th><th>Value</th></tr>'
            '<tr><td>a|b</td><td colspan="2">wide</td></tr></table>'
            "<ul><li>One<ul><li>Inner</li></ul></li><li>Two</li></ul>"
            "<ol><li>First</li><li>Second</li></ol>"
            "<p>Inline <math><mi>x</mi><mo>=</mo><mn>2</mn></math>, drawn "
            '<svg aria-label="\\alpha+1" viewBox="0 0 9 9"><title>t</title>'
            '<path d="M0 0L10 10Z"/></svg>, pictured '
            '<img class="math-inline" alt="$\\beta$" src="assets/b.svg"> and '
            '<svg><path d="M1 1L2 2"/></svg>bare. <code>a_b</code> <b>bold</b></p>'
            '<img src="assets/sketch.png" alt="A sketch">'
        )
        text = render([{"id": "b", "title": "B", "body": body,
                        "quote": "<p>Said once.</p><p>Said twice.</p>"}])
        self.assertIn("Values x_1 y^(10) and n_e T.", text)
        self.assertIn("| Name | Value |  |\n| --- | --- | --- |\n| a\\|b | wide |  |", text)
        self.assertIn("- One\n  - Inner\n- Two", text)
        self.assertIn("1. First\n2. Second", text)
        self.assertIn(
            "Inline [math: x = 2], drawn [math: \\alpha+1], pictured [math: \\beta] "
            "and bare. `a_b` **bold**",
            text,
        )
        self.assertIn("[figure] webdeck/assets/sketch.png Alt: A sketch", text)
        self.assertIn("> Said once.\n>\n> Said twice.", text)
        self.assertNotIn("M0 0", text)
        self.assertNotIn("path", text)

    def test_entities_spaces_and_invisible_characters(self):
        markdown = html_to_markdown(
            "<p>A&nbsp;B&shy;C&#x200B;D &amp; E&#8212;F &lt;!-- slide: x --&gt;</p>"
        )
        self.assertEqual("A BCD & E—F &lt;!-- slide: x -->", markdown)
        self.assertEqual("# not a heading", plain_text("# not a heading"))
        self.assertEqual("\\# not a heading", html_to_markdown("<p># not a heading</p>"))

    def test_escaped_tags_stay_text_in_markdown_and_plain_in_the_outline(self):
        self.assertEqual(
            "&lt;div class=x>hello&lt;/div> and a < b, &lt;!-- c",
            html_to_markdown("&lt;div class=x&gt;hello&lt;/div&gt; and a &lt; b, &lt;!-- c"),
        )
        self.assertEqual(  # a code span is literal: nothing to escape, no emphasis
            "`<div>` and `a b`",
            html_to_markdown("<p><code>&lt;div&gt;</code> and <code>a <b>b</b></code></p>"),
        )
        slides = [
            {"id": "part", "type": "section", "title": "&lt;b&gt;"},
            {"id": "drift", "title": "The &lt;v&gt; drift", "eyebrow": "&lt;i&gt; eyebrow",
             "figure": {"src": "assets/f.png", "alt": "<f> plot"}},
            {"id": "cards", "title": "C", "cards": [{"label": "&lt;n&gt;", "value": "1"}]},
            {"id": "math", "title": "M",
             "body": '<img class="math" alt="$&lt;x&gt;$"> <svg aria-label="&lt;y&gt;"></svg> '
                     "<math><mtext>&lt;z&gt;</mtext></math>"},
        ]
        text = render(slides)
        self.assertIn("## &lt;b>\n", text)
        self.assertIn("**The &lt;v> drift**", text)
        self.assertIn("Eyebrow: &lt;i> eyebrow", text)
        self.assertIn("Alt: &lt;f> plot", text)
        self.assertIn("- **&lt;n>**: 1", text)
        self.assertIn("[math: &lt;x>] [math: &lt;y>] [math: &lt;z>]", text)
        for tag in ("<b>", "<v>", "<i>", "<n>", "<f>", "<x>", "<y>", "<z>"):
            self.assertNotIn(tag, text)
        document = outline(base_deck(slides), unit="u", deck="d", digest=DIGEST)
        self.assertEqual("<b>", document["chapters"][0]["title"])
        self.assertEqual("The <v> drift", document["chapters"][0]["slides"][1]["title"])

    def test_nav_notes_cannot_close_their_comment(self):
        text = html_to_markdown('<a href="#/x--->y">a ---> b --!> c</a>')
        note = text[text.index("<!--"):]
        self.assertEqual(1, note.count("-->"), note)
        self.assertNotIn("--!>", note)
        self.assertTrue(note.endswith(" -->"), note)

    def test_nested_table_becomes_one_line_in_its_cell(self):
        markdown = html_to_markdown(
            "<table><tr><td>A<table><tr><td>x</td><td>y|z</td></tr><tr><td>w</td></tr>"
            "</table></td><td>B</td></tr></table>"
        )
        self.assertEqual("| A x · y\\|z; w | B |\n| --- | --- |", markdown)

    def test_content_outside_cells_is_kept_before_the_table(self):
        self.assertEqual(
            "stray text in row\n\n| a | b |\n| --- | --- |\n| c |  |",
            html_to_markdown(
                "<table> stray text <tr><td>a</td><td>b</td>in row</tr><tr></tr>"
                "<td>c</td> </table>"
            ),
        )

    def test_empty_math_image_leaves_no_marker(self):
        self.assertEqual(
            "Before after", html_to_markdown('<p>Before <img class="math" alt=""> after</p>')
        )

    def test_legacy_formula_html_is_fenced_as_html(self):
        text = render([{"id": "f", "title": "F", "formula": {"html": "<span>E = mc²</span>"}}])
        self.assertIn("```formula\nlinear: E = mc²\n```", text)
        self.assertIn("```html\n<span>E = mc²</span>\n```", text)
        self.assertNotIn("```mathml", text)

    def test_figures_fold_theme_pairs_and_flag_missing_alt(self):
        slide = {
            "id": "figs",
            "title": "Figures",
            "figures": [
                {"id": "chart-dark", "src": "assets/chart-dark.svg", "alt": "A chart",
                 "caption": "Cap"},
                {"id": "chart-light", "src": "assets/chart-light.svg", "alt": "A chart",
                 "caption": "Cap"},
                {"src": "assets/photo.png", "caption": "<em>Photo</em> caption",
                 "source": 'By <a href="https://example.com/o">owner</a>',
                 "shift": [4, 2], "scale": 1.1},
            ],
        }
        text = render([slide])
        self.assertIn(
            "[figure chart-dark] webdeck/assets/chart-dark.svg (dark/light pair)\n"
            "Alt: A chart\nCaption: Cap",
            text,
        )
        self.assertNotIn("chart-light", text)
        self.assertIn(
            "[figure 3] webdeck/assets/photo.png\nAlt: (missing)\nCaption: Photo caption\n"
            "Credit: By [owner](https://example.com/o)",
            text,
        )
        self.assertNotIn("1.1", text)

    def test_cards_interactive_and_video(self):
        slides = [
            {"id": "cards", "title": "Cards", "cards": [
                {"label": "Speed", "value": "fast", "detail": "per second"},
                {"value": "plain."},
            ]},
            {"id": "demo", "chrome": False,
             "interactive": {"src": "assets/demo/index.html", "title": "Try it"}},
            {"id": "clip", "title": "Clip slide", "video": {
                "src": "assets/clip.mp4", "title": "Clip", "caption": "A <em>short</em> clip",
                "source": "Maker", "originalUrl": "https://example.com/v"}},
        ]
        text = render(slides)
        self.assertIn("- **Speed**: fast — per second\n- plain.", text)
        self.assertIn(
            "<!-- slide: demo -->\n[interactive: Try it] webdeck/assets/demo/index.html", text
        )
        self.assertIn(
            "[video: Clip] A short clip / Maker / original: https://example.com/v", text
        )
        document = outline(base_deck(slides), unit="u", deck="d", digest=DIGEST)
        self.assertEqual("Try it", document["chapters"][0]["slides"][1]["title"])

    def test_chrome_false_marks_hidden_title_and_source(self):
        text = render([{"id": "bare", "chrome": False, "title": "Hidden head",
                        "eyebrow": "Hidden eyebrow", "source": "Hidden source"}])
        self.assertIn("**Hidden head** (title not shown)", text)
        self.assertIn("Source (not shown): Hidden source", text)
        self.assertNotIn("Eyebrow", text)

    def test_layout_hides_blocks_the_viewer_does_not_draw(self):
        figure = {"src": "assets/x.png", "alt": "X"}
        slides = [
            {"id": "eq", "title": "Eq", "layout": "equation", "figure": figure},
            {"id": "st", "title": "St", "layout": "statement", "cards": [{"value": "v"}]},
            {"id": "tt", "type": "title", "title": "Tt", "cards": [{"value": "w"}]},
            {"id": "shown", "title": "Shown", "figure": figure},
        ]
        text = render(slides)
        self.assertEqual(1, text.count("[figure "))
        self.assertIn("<!-- slide: shown -->", text.split("[figure ")[0])
        self.assertNotIn("- v", text)
        self.assertNotIn("- w", text)

    def test_eyebrow_override_shown_and_metadata_excluded(self):
        slides = [
            {"id": "part", "type": "section", "title": "Part A", "eyebrow": "Unit 1",
             "accent": "gold", "className": "style-gradient"},
            {"id": "same", "title": "Same", "eyebrow": "Unit 1", "beat": "internal-beat-7"},
            {"id": "override", "title": "Override", "eyebrow": "Practice"},
            {"id": "plain", "title": "Plain", "source": "A source"},
        ]
        text = render(slides)
        self.assertIn("<!-- slide: part -->\nEyebrow: Unit 1\n\n**Part A**", text)
        self.assertIn("<!-- slide: same -->\n**Same**", text)
        self.assertIn("<!-- slide: override -->\nEyebrow: Practice\n\n**Override**", text)
        self.assertIn("**Plain**\n\nSource: A source", text)
        for hidden in ("internal-beat-7", "gold", "style-gradient"):
            self.assertNotIn(hidden, text)


class MathTest(unittest.TestCase):
    def test_linearizer(self):
        cases = [
            ("<mfrac><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow><mi>c</mi></mfrac>",
             "(a + b)/c"),
            ("<mfrac><mi>a</mi><mn>2</mn></mfrac>", "a/2"),
            ("<mfrac><mi>a</mi><mrow><mn>2</mn><mi>b</mi></mrow></mfrac><mi>c</mi>",
             "a/(2b) c"),
            ("<msubsup><mi>x</mi><mi>i</mi><mn>2</mn></msubsup>", "x_i^2"),
            ("<msup><mi>e</mi><mrow><mo>&#x2212;</mo><mi>t</mi></mrow></msup>", "e^(−t)"),
            ("<msup><mi>f</mi><mo>&#x2032;</mo></msup>", "f′"),
            ("<msqrt><mi>x</mi><mo>+</mo><mn>1</mn></msqrt>", "sqrt(x + 1)"),
            ("<mroot><mi>x</mi><mn>3</mn></mroot>", "root(3)(x)"),
            ("<mover accent='true'><mi>x</mi><mo>^</mo></mover>", "hat(x)"),
            ("<mover><mi>v</mi><mo>&#x2192;</mo></mover>", "vec(v)"),
            ("<mover><mi>z</mi><mo>&#xAF;</mo></mover>", "bar(z)"),
            ("<mover><mi>q</mi><mo>&#x2D9;</mo></mover>", "dot(q)"),
            ("<munderover><mo>&sum;</mo><mrow><mi>k</mi><mo>=</mo><mn>1</mn></mrow>"
             "<mi>n</mi></munderover><msub><mi>a</mi><mi>k</mi></msub>",
             "∑_(k = 1)^n a_k"),
            ("<munder><mo>lim</mo><mrow><mi>t</mi><mo>&#x2192;</mo><mn>0</mn></mrow>"
             "</munder><mi>g</mi>", "lim_(t → 0) g"),
            ("<mi>a</mi><mphantom><mi>q</mi></mphantom><mo>+</mo><mi>b</mi>", "a + b"),
            ("<mi>&alpha;</mi><mo>&InvisibleTimes;</mo><mi>&#x3B2;</mi><mo>&le;</mo>"
             "<mn>&#49;</mn>", "αβ ≤ 1"),
            ("<mi>sin</mi><mo>&ApplyFunction;</mo><mi>&theta;</mi>", "sin θ"),
            ("<mrow><mo>&#x2212;</mo><mi>x</mi></mrow><mo>=</mo><mi>y</mi>"
             "<mo>&#x2212;</mo><mn>1</mn>", "−x = y − 1"),
            ("<mfenced><mi>a</mi><mi>b</mi></mfenced>", "(a, b)"),
            ('<mfenced open="[" close="]" separators=";"><mi>a</mi><mi>b</mi></mfenced>',
             "[a; b]"),
            ("<mn>3</mn><mtext>&#xA0;</mtext><mi>k</mi><mtext>m</mtext>", "3 km"),
            ("<mi>x</mi><mtext>for all</mtext><mi>y</mi>", "x for all y"),
            ("<mi>x</mi><mspace width='negativethinmathspace'/><mi>y</mi>", "xy"),
            ("<mtable><mlabeledtr><mtd><mtext>(1)</mtext></mtd><mtd><mi>a</mi></mtd>"
             "<mtd><mo>=</mo><mi>b</mi></mtd></mlabeledtr></mtable>", "a = b"),
        ]
        for mathml, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, mathml_linear(f"<math>{mathml}</math>"))

    def test_derivation_table_gives_one_line_per_row(self):
        mathml = (
            '<math><mtable columnalign="right left">'
            "<mtr><mtd><mi>s</mi></mtd><mtd><mo form='infix'>=</mo>"
            "<mfrac><mi>p</mi><mi>q</mi></mfrac></mtd></mtr>"
            "<mtr><mtd/><mtd><mo>&#x2264;</mo><mn>1</mn></mtd></mtr>"
            "</mtable></math>"
        )
        self.assertEqual("s = p/q\n≤ 1", mathml_linear(mathml))

    def test_tex_annotation_is_captured_separately(self):
        mathml = (
            "<math><semantics><mi>x</mi>"
            "<annotation encoding='application/x-tex'>\\hat{x}</annotation>"
            "<annotation encoding='text/plain'>ignored</annotation>"
            "</semantics></math>"
        )
        self.assertEqual("x", mathml_linear(mathml))
        self.assertEqual(["\\hat{x}"], mathml_tex(mathml))


class DeepMarkupTest(unittest.TestCase):
    DEEP = {
        "unclosed i": "<p>" + "a <i>" * 1000 + "x",
        "nested i": "<i>" * 1000 + "x" + "</i>" * 1000,
        "span": "<span>" * 1000 + "x",
        "div": "<div>" * 1000 + "x",
        "list": "<ul><li>" * 1000 + "x",
        "table": "<table><tr><td>" * 400 + "x",
        "link": '<i><a href="#/0">' * 500 + "x",
        "mrow": "<math>" + "<mrow>" * 1000 + "<mi>x</mi>",
        "msub": "<math>" + "<msub><mi>a</mi>" * 1000 + "<mi>x</mi>",
    }
    # Past the cap an msub holds every later sibling; MathML reads only its first two.
    LOSSY = frozenset({"msub"})

    def test_nesting_past_the_cap_renders_flat(self):
        for name, html in self.DEEP.items():
            with self.subTest(name):
                slide = {"id": "deep", "title": html, "eyebrow": html, "body": html,
                         "formula": {"mathml": html}, "source": html}
                deck = base_deck([slide])
                text = skeleton(deck, unit="unit", digest=DIGEST)
                outline(deck, unit="unit", deck="d", digest=DIGEST)
                plain = plain_text(html)
                self.assertTrue(plain)
                if name not in self.LOSSY:
                    self.assertIn("x", text.split("<!-- slide: deep -->")[1])
                    self.assertIn("x", plain)


class CommandTest(unittest.TestCase):
    SLIDES = [
        {"id": "opening", "type": "title", "title": "Opening ħω → ∞",
         "claim": "Greek αβγ and “quotes”."},
        {"id": "next", "title": "Next", "body": '<a href="#/2">detail</a>'},
        {"id": "detail", "title": "Detail", "appendix": True},
    ]

    def make_unit(self, root, name="unit"):
        return make_json_unit(root, base_deck(self.SLIDES), name)

    def test_unicode_survives_a_cp1252_console(self):
        with tempfile.TemporaryDirectory() as root:
            unit = self.make_unit(root)
            code, out, err = run_cli("narration", "--deck", unit, encoding="cp1252")
            self.assertEqual(0, code, err)
            text = out.decode("utf-8")
            self.assertIn("**Opening ħω → ∞**", text)
            self.assertIn("Greek αβγ and “quotes”.", text)
            self.assertNotIn(b"\r\n", out)
            self.assertTrue(text.endswith("<!-- slide: detail -->\n**Detail**\n"), text)

    def test_digest_ignores_bom_and_crlf(self):
        lf = b'{"deck": 1}\n{"x": 2}\n'
        expected = hashlib.sha256(lf).hexdigest()
        self.assertEqual(expected, deck_digest(lf))
        self.assertEqual(expected, deck_digest(b"\xef\xbb\xbf" + lf.replace(b"\n", b"\r\n")))
        self.assertRegex(expected, r"^[0-9a-f]{64}$")
        with tempfile.TemporaryDirectory() as root:
            unit = self.make_unit(root)
            deck = unit / "webdeck" / "deck.json"
            plain = deck.read_bytes().replace(b"\r\n", b"\n")
            deck.write_bytes(plain.replace(b"\n", b"\r\n"))
            code, out, err = run_cli("narration", "--deck", deck)
            self.assertEqual(0, code, err)
            digest = hashlib.sha256(plain).hexdigest()
            self.assertTrue(out.startswith(f"<!-- deck: unit sha256 {digest} -->\n".encode()))

    def test_legacy_json_literal_is_accepted_and_code_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            webdeck = Path(root) / "legacy" / "webdeck"
            webdeck.mkdir(parents=True)
            literal = json.dumps(base_deck(self.SLIDES), ensure_ascii=False)
            slides_js = webdeck / "slides.js"
            slides_js.write_bytes(
                f"﻿  window.LECTUREDECK = {literal};\r\n".encode("utf-8")
            )
            code, out, err = run_cli("narration", "--deck", Path(root) / "legacy")
            self.assertEqual(0, code, err)
            self.assertIn(b"<!-- deck: legacy sha256 ", out)
            self.assertIn(b"<!-- slide: detail -->", out)
            refusal = "ERROR: narration needs deck.json; this slides.js is not a plain JSON literal"
            for source in (
                'window.LECTUREDECK = { meta: { title: "x" }, slides: [] };\n',
                f"window.LECTUREDECK = {literal};\nconsole.log(1);\n",
                f"var deck = {literal};\n",
            ):
                with self.subTest(source=source[:24]):
                    slides_js.write_text(source, encoding="utf-8")
                    code, out, err = run_cli("narration", "--deck", slides_js)
                    self.assertEqual(2, code)
                    self.assertEqual(b"", out)
                    self.assertIn(refusal, err)

    def test_legacy_ids_must_be_kebab_case(self):
        with tempfile.TemporaryDirectory() as root:
            webdeck = Path(root) / "legacy" / "webdeck"
            webdeck.mkdir(parents=True)
            slides_js = webdeck / "slides.js"
            for bad in ("a -->\n## Injected heading\n<!--", "Upper", "", 7):
                with self.subTest(bad=bad):
                    deck = base_deck([{"id": bad, "title": "T"}, {"id": "ok", "title": "U"}])
                    slides_js.write_text(
                        f"window.LECTUREDECK = {json.dumps(deck)};", encoding="utf-8"
                    )
                    code, out, err = run_cli("narration", "--deck", slides_js)
                    self.assertEqual(2, code)
                    self.assertEqual(b"", out)
                    self.assertIn(
                        "ERROR: slides.js: slides[0].id must be a lowercase kebab-case "
                        "identifier",
                        err,
                    )

    def test_unit_names_that_break_the_header_are_refused(self):
        with tempfile.TemporaryDirectory() as root:
            for unit in ("a-->b", "a--!>b", "a\nb", "a\rb"):
                with self.subTest(unit=unit):
                    code, out, err = run_cli("narration", unit, "--repo", root)
                    self.assertEqual(2, code)
                    self.assertEqual(b"", out)
                    self.assertIn("cannot appear in a narration header", err)
            unit = self.make_unit(root)
            folder = Path(root) / "x-->y"  # not creatable on every filesystem
            with patch(
                "lecturedeck.cli.narration_deck",
                return_value=folder / "webdeck" / "deck.json",
            ):
                code, out, err = run_cli("narration", "--deck", unit)
            self.assertEqual(2, code)
            self.assertIn("ERROR: unit name 'x-->y' cannot appear", err)

    def test_deeply_nested_markup_is_flattened_not_a_traceback(self):
        body = "<p>" + "a <i>" * 1000 + "x"
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck([{"id": "deep", "title": "D", "body": body}]))
            code, out, err = run_cli("narration", "--deck", unit)
            self.assertEqual(0, code, err)
            paragraph = out.decode("utf-8").split("**D**\n\n")[1]
            self.assertEqual(1000, paragraph.count("a"))
            self.assertTrue(paragraph.rstrip().endswith("x"), paragraph[-40:])
            with patch("lecturedeck.cli.skeleton", side_effect=RecursionError):
                code, out, err = run_cli("narration", "--deck", unit)
            self.assertEqual(2, code)
            self.assertEqual(b"", out)
            self.assertIn("ERROR: deck.json: markup nested too deeply", err)
            self.assertNotIn("Traceback", err)

    def test_closed_stdout_ends_quietly(self):
        class ClosedPipe:
            def __init__(self, error):
                self.error = error

            def write(self, data):
                raise self.error

            def flush(self):
                pass

        class Stdout:
            def __init__(self, error):
                self.buffer = ClosedPipe(error)

            def flush(self):
                pass

            def fileno(self):
                raise io.UnsupportedOperation("fileno")

        with patch("lecturedeck.cli.sys.stdout", Stdout(BrokenPipeError(errno.EPIPE, "pipe"))):
            write_stdout("text")
        full = OSError(errno.ENOSPC, "No space left on device")
        with patch("lecturedeck.cli.sys.stdout", Stdout(full)):
            with self.assertRaises(OSError):
                write_stdout("text")

    def test_a_reader_that_stops_early_gets_no_traceback(self):
        slides = [
            {"id": f"slide-{n}", "title": f"Slide {n}", "body": "<p>" + "word " * 60 + "</p>"}
            for n in range(1500)
        ]
        package = str(Path(lecturedeck.__file__).resolve().parents[1])
        paths = [package, *filter(None, os.environ.get("PYTHONPATH", "").split(os.pathsep))]
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(paths)}
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(slides))
            with subprocess.Popen(
                [sys.executable, "-m", "lecturedeck", "narration", "--deck", str(unit)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            ) as child:
                head = child.stdout.read(300)
                child.stdout.close()  # the reader stops while the child is still writing
                err = child.stderr.read().decode("utf-8", "replace")
                code = child.wait(timeout=120)
        self.assertTrue(head.startswith(b"<!-- deck: unit sha256 "), head)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("BrokenPipeError", err)
        self.assertEqual(0, code, err)

    def test_invalid_deck_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck([{"id": "a", "titel": "typo"}]))
            code, out, err = run_cli("narration", "--deck", unit)
            self.assertEqual(2, code)
            self.assertEqual(b"", out)
            self.assertIn("ERROR: deck.json: slides[0] has unknown field 'titel'", err)

    def test_output_writes_a_new_file_outside_webdeck(self):
        with tempfile.TemporaryDirectory() as root:
            unit = self.make_unit(root)
            _, expected, _ = run_cli("narration", "--deck", unit)
            target = Path(root) / "narration.md"
            code, out, err = run_cli("narration", "--deck", unit, "--output", target)
            self.assertEqual(0, code, err)
            self.assertIn(b"Wrote unit narration skeleton to", out)
            self.assertEqual(expected, target.read_bytes())
            code, _, err = run_cli("narration", "--deck", unit, "--output", target)
            self.assertEqual(2, code)
            self.assertIn("ERROR: output already exists", err)
            self.assertEqual(expected, target.read_bytes())
            inside = unit / "webdeck" / "narration.md"
            code, _, err = run_cli("narration", "--deck", unit, "--output", inside)
            self.assertEqual(2, code)
            self.assertIn("ERROR: refusing to write inside the deck folder", err)
            self.assertFalse(inside.exists())

    def test_outline_json_shape_and_labels(self):
        with tempfile.TemporaryDirectory() as root:
            unit = self.make_unit(root)
            code, out, err = run_cli("narration", "--deck", unit, "--outline")
            self.assertEqual(0, code, err)
            document = json.loads(out.decode("utf-8"))
            digest = deck_digest((unit / "webdeck" / "deck.json").read_bytes())
            self.assertEqual(
                {
                    "schema": 1,
                    "lecturedeck": __version__,
                    "unit": "unit",
                    "deck": "webdeck/deck.json",
                    "sha256": digest,
                    "main_total": 2,
                    "backup_total": 1,
                    "chapters": [
                        {"title": "Opening", "backup": False, "slides": [
                            {"id": "opening", "label": "1", "index": 0,
                             "title": "Opening ħω → ∞"},
                            {"id": "next", "label": "2", "index": 1, "title": "Next"},
                        ]},
                        {"title": "Backup", "backup": True, "slides": [
                            {"id": "detail", "label": "B1", "index": 2, "title": "Detail"},
                        ]},
                    ],
                },
                document,
            )

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as root:
            unit = self.make_unit(root)
            for extra in ([], ["--outline"]):
                with self.subTest(extra=extra):
                    first = run_cli("narration", "--deck", unit, *extra)
                    second = run_cli("narration", "--deck", unit, *extra)
                    self.assertEqual(first, second)

    def test_deck_accepts_file_webdeck_and_unit_folders(self):
        with tempfile.TemporaryDirectory() as root:
            unit = self.make_unit(root, "sample-unit")
            outputs = {
                run_cli("narration", "--deck", path)[1]
                for path in (unit, unit / "webdeck", unit / "webdeck" / "deck.json")
            }
            self.assertEqual(1, len(outputs))
            self.assertIn(b"<!-- deck: sample-unit sha256 ", outputs.pop())
            loose = Path(root) / "loose"
            loose.mkdir()
            deck = loose / "deck.json"
            deck.write_text(json.dumps(base_deck(self.SLIDES[:2])), encoding="utf-8")
            code, out, err = run_cli("narration", "--deck", deck, "--outline")
            self.assertEqual(0, code, err)
            document = json.loads(out)
            self.assertEqual(("loose", "deck.json"), (document["unit"], document["deck"]))
            code, _, err = run_cli("narration", "--deck", Path(root) / "missing")
            self.assertEqual(2, code)
            self.assertIn("ERROR: no deck at", err)

    def test_unit_resolves_like_check(self):
        with tempfile.TemporaryDirectory() as root:
            presentations = Path(root) / "Studio" / "work" / "presentations"
            presentations.mkdir(parents=True)
            make_json_unit(presentations, base_deck(self.SLIDES), "sample")
            code, out, err = run_cli("narration", "sample", "--repo", root, "--outline")
            self.assertEqual(0, code, err)
            self.assertEqual("sample", json.loads(out)["unit"])
            code, _, err = run_cli("narration", "absent", "--repo", root)
            self.assertEqual(2, code)
            self.assertIn("ERROR: web deck not found", err)
            failure = RuntimeError("Could not find a lecture repository.")
            with patch("lecturedeck.cli.find_repo_root", side_effect=failure):
                code, _, err = run_cli("narration", "sample")
            self.assertEqual(2, code)
            self.assertIn("ERROR: Could not find a lecture repository.", err)
            self.assertNotIn("Traceback", err)

    def test_deck_is_exclusive_with_unit_and_repo(self):
        for argv in (
            ["narration", "unit", "--deck", "deck.json"],
            ["narration", "--deck", "deck.json", "--repo", "."],
            ["narration"],
        ):
            stderr = StringIO()
            with self.subTest(argv=argv), redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    main(argv)
                self.assertEqual(2, raised.exception.code)
                self.assertIn("usage: lecturedeck narration", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
