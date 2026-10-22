import http.client
import json
import re
import sys
import tempfile
import threading
import types
import unittest
from contextlib import redirect_stderr
from importlib.resources import files
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from unittest.mock import Mock, patch

from lecturedeck import __version__, pacing, scaffold
from lecturedeck.cli import (
    DEFAULT_PORT,
    build_parser,
    main,
    make_available_server,
    selector_folder,
    serve,
)
from lecturedeck.deckdata import deck_warnings, html_step_values
from lecturedeck.pdf import export_pdf
from lecturedeck.scaffold import refresh_unit, runtime_hash, scaffold_unit
from lecturedeck.server import discover_decks, make_selector_server, make_server, selector_page
from lecturedeck.validation import (
    VIEWER_FILES,
    deck_entry,
    release_unit,
    unit_warnings,
    validate_unit,
)

LEGACY_SLIDES = """window.LECTUREDECK = {
  meta: { title: "Legacy deck", section: "COURSE TITLE", opening: "OPENING" },
  slides: [
    { type: "title", title: "Legacy deck", claim: "Legacy scaffold slide.", accent: "red" }
  ]
};
"""


def packaged_text(name: str) -> str:
    return files("lecturedeck").joinpath("assets", name).read_text(encoding="utf-8")


def make_json_unit(root, deck: dict | None = None) -> Path:
    unit = Path(root) / "unit"
    unit.mkdir()
    scaffold_unit(unit, "JSON deck")
    if deck is not None:
        write_deck(unit, deck)
    return unit


def make_legacy_unit(root) -> Path:
    unit = Path(root) / "unit"
    unit.mkdir()
    webdeck = unit / "webdeck"
    (webdeck / "assets").mkdir(parents=True)
    (webdeck / "slides.js").write_text(LEGACY_SLIDES, encoding="utf-8")
    (webdeck / "deck.css").write_text("/* unit styles */\n", encoding="utf-8")
    return unit


def write_deck(unit: Path, deck: dict) -> None:
    (unit / "webdeck" / "deck.json").write_text(json.dumps(deck, indent=2), encoding="utf-8")


def base_deck(**overrides) -> dict:
    deck = {
        "deck": 1,
        "meta": {"title": "JSON deck", "section": "COURSE TITLE"},
        "slides": [
            {
                "id": "opening",
                "type": "title",
                "title": "JSON deck",
                "claim": "A declarative deck.",
                "accent": "red",
            }
        ],
    }
    deck.update(overrides)
    return deck


class LecturedeckTest(unittest.TestCase):
    def assertHasError(self, errors, fragment):  # noqa: N802 - unittest style
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_stable_tab_and_selector_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            deck = base_deck(meta={"title": "One", "tabTitle": "Subject · 1",
                                  "selectorTitle": "Subject & lectures",
                                  "selectorFavicon": "assets/identity.svg"})
            unit = make_json_unit(root, deck)
            self.assertHasError(validate_unit(unit), "meta.selectorFavicon is missing")
            icon = unit / "webdeck/assets/identity.svg"
            icon.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
            self.assertEqual([], validate_unit(unit))
            output = Path(root) / "release"
            release_unit(unit, output)
            self.assertTrue((output / "assets/identity.svg").is_file())
            page = selector_page(discover_decks(Path(root)))
            self.assertIn(b"<title>Subject &amp; lectures</title>", page)
            self.assertIn(b"/decks/unit/webdeck/assets/identity.svg", page)
            deck["meta"]["selectorFavicon"] = "assets/../private.svg"
            write_deck(unit, deck)
            self.assertHasError(validate_unit(unit), "path under assets/")
            self.assertIsNone(discover_decks(Path(root))[0].selector_favicon)

    def test_conflicting_selector_identity_is_generic(self):
        from lecturedeck.server import DeckSummary

        decks = [DeckSummary("one", Path("one"), "One", selector_title="First"),
                 DeckSummary("two", Path("two"), "Two", selector_title="Second")]
        page = selector_page(decks)
        self.assertIn(b"<title>Lecture decks</title>", page)
        self.assertIn(b'<link rel="icon" href="/favicon.svg"', page)

    def test_scaffold_is_content_only(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            created = scaffold_unit(unit, 'Test "quoted" deck')
            webdeck = unit / "webdeck"
            self.assertEqual({"deck.css", "deck.json"}, {path.name for path in created})
            self.assertTrue((webdeck / "assets").is_dir())
            self.assertFalse((webdeck / "index.html").exists())
            self.assertFalse((webdeck / "slides.js").exists())
            self.assertFalse((webdeck / "lecturedeck.js").exists())
            deck = json.loads((webdeck / "deck.json").read_text(encoding="utf-8"))
            self.assertEqual(1, deck["deck"])
            self.assertEqual('Test "quoted" deck', deck["meta"]["title"])
            self.assertEqual([], validate_unit(unit))

    def test_release_materializes_viewer_and_preserves_unit_css(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            custom_css = ".claim { letter-spacing: .01em; }\n"
            (unit / "webdeck" / "deck.css").write_text(custom_css, encoding="utf-8")
            output = Path(root) / "release"
            release_unit(unit, output)
            for name in ("index.html", "lecturedeck.css", "lecturedeck.js", "deck.json"):
                self.assertTrue((output / name).is_file(), name)
            self.assertFalse((output / "adjust.js").exists())
            self.assertFalse((output / "slides.js").exists())
            self.assertEqual(custom_css, (output / "deck.css").read_text(encoding="utf-8"))
            self.assertIn('href="deck.css"', (output / "index.html").read_text())

    def test_release_and_check_ignore_pacing_records(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            records = unit / "pacing-records"
            records.mkdir()
            (records / "x.json").write_text("{not a record", encoding="utf-8")
            (records / "stray.html").write_text(
                '<script src="https://example.com/x.js"></script><img src="../../x.png">',
                encoding="utf-8",
            )
            self.assertEqual([], validate_unit(unit))
            output = Path(root) / "release"
            release_unit(unit, output)
            released = [path.relative_to(output).as_posix() for path in output.rglob("*")]
            self.assertNotIn("pacing-sink.js", [Path(name).name for name in released])
            self.assertFalse([name for name in released if "pacing-records" in name], released)
            for path in output.rglob("*"):
                if path.is_file() and path.suffix in {".html", ".js", ".css", ".json"}:
                    with self.subTest(path=path.name):
                        self.assertNotIn(
                            "__lecturedeck/pacing", path.read_text(encoding="utf-8")
                        )

    def test_release_preserves_legacy_viewer_overrides(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_legacy_unit(root)
            webdeck = unit / "webdeck"
            for name in ("index.html", "lecturedeck.css", "lecturedeck.js"):
                marker = (
                    f"<!-- local {name} -->"
                    if name == "index.html"
                    else f"/* local {name} */"
                    if name.endswith(".css")
                    else f"// local {name}"
                )
                content = packaged_text(name) + f"\n{marker}\n"
                (webdeck / name).write_text(content, encoding="utf-8")
            output = Path(root) / "release"
            release_unit(unit, output)
            self.assertIn("local lecturedeck.js", (output / "lecturedeck.js").read_text())
            self.assertTrue((output / "slides.js").is_file())

    def test_missing_deck_data_is_reported(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            (unit / "webdeck").mkdir(parents=True)
            self.assertEqual(
                ["missing webdeck/deck.json (or legacy webdeck/slides.js)"],
                validate_unit(unit),
            )

    def test_legacy_slides_only_unit_validates(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_legacy_unit(root)
            self.assertEqual([], validate_unit(unit))
            self.assertEqual("slides.js", deck_entry(unit).name)

    def test_deck_entry_prefers_deck_json(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_legacy_unit(root)
            write_deck(unit, base_deck())
            self.assertEqual("deck.json", deck_entry(unit).name)
            self.assertEqual([], validate_unit(unit))

    def test_external_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            index = unit / "webdeck" / "index.html"
            index.write_text(
                packaged_text("index.html") + '<script src="https://example.com/x.js"></script>',
                encoding="utf-8",
            )
            self.assertHasError(validate_unit(unit), "external dependency")

    def test_external_source_link_is_not_a_runtime_dependency(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_legacy_unit(root)
            slides = unit / "webdeck" / "slides.js"
            slides.write_text(
                slides.read_text(encoding="utf-8")
                + '\nconst source = \'<a href="https://example.com/source">Source</a>\';',
                encoding="utf-8",
            )
            self.assertEqual([], validate_unit(unit))

    def test_validation_accepts_unit_local_runtime_names(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            webdeck = unit / "webdeck"
            (webdeck / "retained-runtime.css").write_text(
                packaged_text("lecturedeck.css"), encoding="utf-8"
            )
            (webdeck / "retained-runtime.js").write_text(
                packaged_text("lecturedeck.js"), encoding="utf-8"
            )
            index = packaged_text("index.html").replace("lecturedeck.css", "retained-runtime.css")
            index = index.replace("lecturedeck.js", "retained-runtime.js")
            (webdeck / "index.html").write_text(index, encoding="utf-8")
            self.assertEqual([], validate_unit(unit))

    def test_deck_json_schema_rejections(self):
        cases = [
            ({"deck": 2, "meta": {"title": "x"}, "slides": [{"id": "a"}]}, "schema version"),
            (base_deck(requires="1.0"), 'requires must look like ">=MAJOR.MINOR"'),
            (base_deck(meta={"title": ""}), "meta.title must be a non-empty string"),
            (base_deck(meta={"title": "x", "banner": "y"}), "unknown field 'banner'"),
            (base_deck(meta={"title": "x", "openingAccent": "pink"}), "meta.openingAccent"),
            (base_deck(meta={"title": "x", "favicon": ""}), "meta.favicon"),
            (
                base_deck(meta={"title": "x", "favicon": "geometry"}),
                "must be a preset",
            ),
            (
                base_deck(meta={"title": "x", "favicon": "images/favicon.svg"}),
                "path under assets/",
            ),
            (base_deck(meta={"title": "x", "selectorGroup": ""}), "meta.selectorGroup"),
            (base_deck(meta={"title": "x", "selectorHero": "hero.png"}), "meta.selectorHero"),
            (base_deck(slides=[]), "slides must be a non-empty list"),
            (base_deck(slides=[{"title": "no id"}]), "slides[0].id"),
            (base_deck(slides=[{"id": "Bad_ID"}]), "kebab-case"),
            (
                base_deck(slides=[{"id": "twin"}, {"id": "twin"}]),
                "duplicate slide id 'twin'",
            ),
            (base_deck(slides=[{"id": "a", "titel": "typo"}]), "unknown field 'titel'"),
            (base_deck(slides=[{"id": "a", "accent": "magenta"}]), "slides[0].accent"),
            (base_deck(slides=[{"id": "a", "layout": "poster"}]), "slides[0].layout"),
            (base_deck(slides=[{"id": "a", "className": "bad<class"}]), "className"),
            (base_deck(slides=[{"id": "a", "chrome": "no"}]), "chrome must be true or false"),
            (base_deck(slides=[{"id": "a", "formula": {"label": "L"}}]), "formula.mathml"),
            (base_deck(slides=[{"id": "a", "cards": []}]), "cards must be a non-empty list"),
            (
                base_deck(
                    slides=[
                        {
                            "id": "a",
                            "figure": {"src": "assets/x.png"},
                            "video": {"src": "assets/x.mp4"},
                        }
                    ]
                ),
                "only one of",
            ),
            (
                base_deck(slides=[{"id": "a", "figure": {"src": "assets/x.png", "crop": 1}}]),
                "unknown field 'crop'",
            ),
            (
                base_deck(slides=[{"id": "a", "figure": {"src": "assets/x.png", "shift": [1]}}]),
                "shift must be [x, y]",
            ),
            (
                base_deck(slides=[{"id": "a", "figure": {"src": "assets/x.png", "scale": 0}}]),
                "scale must be a number",
            ),
            (
                base_deck(
                    slides=[
                        {
                            "id": "a",
                            "figures": [
                                {"id": "fig", "src": "assets/x.png"},
                                {"id": "fig", "src": "assets/y.png"},
                            ],
                        }
                    ]
                ),
                "duplicate figure id 'fig'",
            ),
            (base_deck(slides=[{"id": "a", "video": {"poster": "p.jpg"}}]), "video.src"),
            (
                base_deck(
                    slides=[
                        {
                            "id": "a",
                            "video": {
                                "sources": [{"src": "assets/x.mp4"}],
                                "src": "assets/x.mp4",
                            },
                        }
                    ]
                ),
                "must not mix sources with src/type",
            ),
            (
                base_deck(
                    slides=[
                        {
                            "id": "a",
                            "video": {"src": "assets/x.mp4", "tracks": [{"kind": "captions"}]},
                        }
                    ]
                ),
                "tracks[0].src",
            ),
            (
                base_deck(slides=[{"id": "a", "interactive": {"src": "demo/index.html"}}]),
                "must lie under assets/",
            ),
        ]
        for deck, fragment in cases:
            with self.subTest(fragment=fragment):
                with tempfile.TemporaryDirectory() as root:
                    unit = make_json_unit(root, deck)
                    self.assertHasError(validate_unit(unit), fragment)

    def test_deck_json_appendix_marks_one_boundary(self):
        slides = [
            {"id": "opening", "type": "title", "title": "Main"},
            {"id": "main-two", "title": "Main two", "appendix": False},
            {"id": "backup", "type": "section", "title": "Backup", "appendix": True},
            {"id": "backup-two", "title": "Backup two"},
        ]
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(slides=slides))
            self.assertEqual([], validate_unit(unit))
        cases = [
            (
                [{"id": "a", "appendix": "yes"}],
                "slides[0].appendix must be true or false",
            ),
            ([{"id": "a", "appendix": 1}], "slides[0].appendix must be true or false"),
            (
                [
                    {"id": "a"},
                    {"id": "b", "appendix": True},
                    {"id": "c", "appendix": False},
                    {"id": "d", "appendix": True},
                ],
                "only one slide may set appendix to true; it marks where the appendix "
                "starts (found slides[1], slides[3])",
            ),
        ]
        for deck_slides, fragment in cases:
            with self.subTest(fragment=fragment):
                with tempfile.TemporaryDirectory() as root:
                    unit = make_json_unit(root, base_deck(slides=deck_slides))
                    self.assertHasError(validate_unit(unit), fragment)

    def test_deck_json_review_slides_come_before_the_appendix(self):
        slides = [
            {"id": "opening", "type": "title", "title": "Main"},
            {"id": "review", "type": "section", "title": "Homework review", "review": True},
            {"id": "review-two", "title": "Solution", "review": True},
            {"id": "main-two", "title": "Main two", "review": False},
            {"id": "backup", "type": "section", "title": "Backup", "appendix": True},
        ]
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(slides=slides))
            self.assertEqual([], validate_unit(unit))
        cases = [
            ([{"id": "a", "review": "yes"}], "slides[0].review must be true or false"),
            (
                [
                    {"id": "a"},
                    {"id": "b", "appendix": True},
                    {"id": "c", "review": True},
                ],
                "slides[2].review cannot be true in the appendix; review slides come "
                "before the slide that sets appendix",
            ),
            (
                [{"id": "a"}, {"id": "b", "appendix": True, "review": True}],
                "slides[1].review cannot be true in the appendix",
            ),
        ]
        for deck_slides, fragment in cases:
            with self.subTest(fragment=fragment):
                with tempfile.TemporaryDirectory() as root:
                    unit = make_json_unit(root, base_deck(slides=deck_slides))
                    self.assertHasError(validate_unit(unit), fragment)

    def test_deck_json_figure_hotspots_are_validated(self):
        def figure(hotspots, src="assets/a.png") -> dict:
            return {"src": src, "alt": "Group photo", "hotspots": hotspots}

        planck = {
            "x": 0.123, "y": 0.456, "r": 0.025, "label": "Max Planck",
            "html": "<strong>Max Planck</strong> (1858–1947)<br>Energy quanta, 1900; "
                    "<math><mi>E</mi><mo>=</mo><mi>h</mi><mi>ν</mi></math>, "
                    '<a href="https://www.nobelprize.org/">Nobel</a> 1918.',
        }
        edges = [{"x": 0, "y": 1, "r": 0.5, "label": "Edge"}, {"x": 1, "y": 0, "r": 1e-4,
                                                               "label": "Other edge"}]
        good = [
            {"id": "one", "figure": figure([planck])},
            {"id": "grid", "layout": "figures",
             "figures": [figure(edges), {"src": "assets/a.png", "alt": "Plain"}]},
        ]
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(slides=good))
            (unit / "webdeck" / "assets" / "a.png").write_bytes(b"x")
            self.assertEqual([], validate_unit(unit))
        where = "slides[0].figure.hotspots"
        cases = [
            ([], f"{where} must be a non-empty list"),
            ({"x": 0.5}, f"{where} must be a non-empty list"),
            (["Planck"], f"{where}[0] must be an object"),
            ([{**planck, "name": "x"}], f"{where}[0] has unknown field 'name'"),
            ([{**planck, "x": 1.2}], f"{where}[0].x must be a number in [0, 1], a fraction of "
                                     "the picture's natural width"),
            ([{**planck, "y": -0.1}], f"{where}[0].y must be a number in [0, 1], a fraction of "
                                      "the picture's natural height"),
            ([{**planck, "y": "0.4"}], f"{where}[0].y must be a number in [0, 1]"),
            ([{**planck, "x": True}], f"{where}[0].x must be a number in [0, 1]"),
            ([{k: v for k, v in planck.items() if k != "x"}], f"{where}[0].x must be a number"),
            ([{**planck, "r": 0}], f"{where}[0].r must be a number in (0, 0.5], a fraction of "
                                   "the picture's natural width"),
            ([{**planck, "r": 0.6}], f"{where}[0].r must be a number in (0, 0.5]"),
            ([{**planck, "r": float("nan")}], f"{where}[0].r must be a number in (0, 0.5]"),
            ([{**planck, "label": ""}], f"{where}[0].label must be a non-empty string"),
            ([{**planck, "label": "  "}], f"{where}[0].label must be a non-empty string"),
            ([{k: v for k, v in planck.items() if k != "label"}],
             f"{where}[0].label must be a non-empty string"),
            ([planck, {**planck, "html": 3}], f"{where}[1].html must be a string"),
            ([{**planck, "html": '<span data-step="1">later</span>'}],
             f"{where}[0].html cannot hold a data-step; a popup is never stepped"),
        ]
        for hotspots, fragment in cases:
            with self.subTest(fragment=fragment, hotspots=hotspots):
                with tempfile.TemporaryDirectory() as root:
                    unit = make_json_unit(root, base_deck(
                        slides=[{"id": "one", "figure": figure(hotspots)}]))
                    (unit / "webdeck" / "assets" / "a.png").write_bytes(b"x")
                    self.assertHasError(validate_unit(unit), fragment)
        # Every item of a figure grid is checked on its own.
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(slides=[{"id": "grid", "figures": [
                figure([planck]), figure([{**planck, "x": 2}])]}]))
            (unit / "webdeck" / "assets" / "a.png").write_bytes(b"x")
            self.assertHasError(validate_unit(unit), "slides[0].figures[1].hotspots[0].x")

    def stepped_unit(self, root, slides: list) -> Path:
        unit = make_json_unit(root, base_deck(slides=slides))
        assets = unit / "webdeck" / "assets"
        for name in ("a.png", "b.png", "clip.mp4"):
            (assets / name).write_bytes(b"x")
        (assets / "demo").mkdir()
        (assets / "demo" / "index.html").write_text("<!doctype html><title>d</title>")
        return unit

    def test_step_reveals_validate_everywhere_a_slide_shows_them(self):
        slides = [
            {
                "id": "copy-steps",
                "title": 'Title <span data-step="4">later</span>',
                "eyebrow": "Part",
                "claim": 'One <span data-step="1">two</span>',
                "body": '<p data-step="2">three</p><p data-step="2">together</p>',
                "quote": '<em data-step="4">quoted</em>',
                "source": '<span data-step="4">credit</span>',
                "formula": {
                    "mathml": "<math><mi data-step='3'>x</mi></math>",
                    "step": 3,
                    "gloss": ['<span data-step="3">gloss</span>'],
                },
            },
            {
                "id": "figure-steps",
                "layout": "figures",
                "figures": [
                    {"src": "assets/a.png", "step": 1},
                    {"src": "assets/b.png", "step": 2, "caption": '<b data-step="3">c</b>'},
                ],
            },
            {
                "id": "card-steps",
                "cards": [
                    {"value": "always"},
                    {"value": "first", "step": 1},
                    {"label": '<span data-step="2">L</span>', "value": "second", "step": 2},
                ],
            },
            {"id": "video-step", "video": {"src": "assets/clip.mp4", "step": 1}},
            {
                "id": "demo-step",
                "claim": '<b data-step="2">after the demo</b>',
                "interactive": {"src": "assets/demo/index.html", "step": 1},
            },
            {
                "id": "full-canvas",
                "chrome": False,
                "interactive": {"src": "assets/demo/index.html", "step": 1},
            },
            {"id": "bare-demo", "chrome": False, "claim": '<b data-step="1">shown</b>'},
        ]
        with tempfile.TemporaryDirectory() as root:
            unit = self.stepped_unit(root, slides)
            self.assertEqual([], validate_unit(unit))
            self.assertEqual([], unit_warnings(unit))

    def test_step_reveal_rejections(self):
        cases = [
            ({"id": "a", "figure": {"src": "assets/a.png", "step": 0}},
             "slides[0].figure.step must be a positive integer"),
            ({"id": "a", "figure": {"src": "assets/a.png", "step": -1}}, "figure.step must"),
            ({"id": "a", "figure": {"src": "assets/a.png", "step": "2"}}, "figure.step must"),
            ({"id": "a", "figure": {"src": "assets/a.png", "step": True}}, "figure.step must"),
            ({"id": "a", "figure": {"src": "assets/a.png", "step": 1.0}}, "figure.step must"),
            ({"id": "a", "cards": [{"value": "v", "step": 1.5}]},
             "slides[0].cards[0].step must be a positive integer"),
            ({"id": "a", "video": {"src": "assets/clip.mp4", "step": None}}, "video.step must"),
            ({"id": "a", "interactive": {"src": "assets/demo/index.html", "step": [1]}},
             "interactive.step must"),
            ({"id": "a", "formula": {"mathml": "<math/>", "step": 0}}, "formula.step must"),
            ({"id": "a", "claim": '<span data-step="0">x</span>'},
             "slides[0].claim has data-step='0'; data-step must be a positive integer"),
            ({"id": "a", "body": '<p data-step="two">x</p>'}, "body has data-step='two'"),
            ({"id": "a", "body": "<p data-step>x</p>"}, "body has an empty data-step"),
            ({"id": "a", "body": '<p data-step="01">x</p>'}, "data-step='01'"),
            ({"id": "a", "body": '<p data-step=" 2">x</p>'}, "data-step=' 2'"),
            ({"id": "a", "claim": '<p DATA-STEP="-1">x</p>'}, "data-step='-1'"),
            ({"id": "a", "figure": {"src": "assets/a.png", "caption": "<i data-step=1.5>c</i>"}},
             "figure.caption has data-step='1.5'"),
            ({"id": "a", "figure": {"src": "assets/a.png", "steps": 1}}, "unknown field 'steps'"),
            (
                {"id": "a", "chrome": False, "claim": '<b data-step="1">x</b>',
                 "interactive": {"src": "assets/demo/index.html"}},
                "slides[0].claim has a step this slide never shows: a full-canvas interactive "
                "slide (chrome: false) hides its claim, formula, body and quote",
            ),
            (
                {"id": "a", "chrome": False, "formula": {"mathml": "<math/>", "step": 1},
                 "interactive": {"src": "assets/demo/index.html"}},
                "slides[0].formula.step has a step this slide never shows",
            ),
            (
                {"id": "a", "chrome": False, "title": '<b data-step="1">x</b>'},
                "slides[0].title has a step this slide never shows: chrome: false drops",
            ),
            (
                {"id": "a", "chrome": False, "source": '<b data-step="1">x</b>'},
                "slides[0].source has a step this slide never shows",
            ),
            (
                {"id": "a", "layout": "statement", "figure": {"src": "assets/a.png", "step": 1}},
                "slides[0].figure.step has a step this slide never shows: layout 'statement' "
                "does not show the figure",
            ),
            (
                {"id": "a", "layout": "equation", "cards": [{"value": "v", "step": 1}]},
                "does not show the cards",
            ),
            (
                {"id": "a", "layout": "figure", "video": {"src": "assets/clip.mp4", "step": 1}},
                "does not show the video",
            ),
        ]
        for slide, fragment in cases:
            with self.subTest(fragment=fragment):
                with tempfile.TemporaryDirectory() as root:
                    unit = self.stepped_unit(root, [slide])
                    self.assertHasError(validate_unit(unit), fragment)
        # One error per field, however many hidden steps it holds.
        with tempfile.TemporaryDirectory() as root:
            unit = self.stepped_unit(root, [{
                "id": "a", "chrome": False, "interactive": {"src": "assets/demo/index.html"},
                "body": '<p data-step="1">x</p><p data-step="2">y</p>',
            }])
            self.assertEqual(1, sum("never shows" in error for error in validate_unit(unit)))

    def test_step_gaps_warn_without_failing_check(self):
        slides = [
            {"id": "plain", "title": "No steps"},
            {"id": "gappy", "claim": '<b data-step="1">a</b>', "body": '<p data-step="3">c</p>'},
            {"id": "stray", "body": '<p data-step="900">late</p>'},
            {"id": "runs", "cards": [{"value": "a", "step": 2}, {"value": "b", "step": 5}]},
            {"id": "contiguous", "claim": '<b data-step="2">b</b><b data-step="1">a</b>'},
        ]
        self.assertEqual(
            [
                "deck.json: slides[1] (gappy) skips step 2 (uses 1, 3); "
                "each press still reveals the next number used",
                "deck.json: slides[2] (stray) skips step 1-899 (uses 900); "
                "each press still reveals the next number used",
                "deck.json: slides[3] (runs) skips step 1, 3-4 (uses 2, 5); "
                "each press still reveals the next number used",
            ],
            deck_warnings(base_deck(slides=slides)),
        )
        self.assertEqual([], deck_warnings({"slides": "not a list"}))
        self.assertEqual(["1", "x", None], html_step_values(
            '<p data-step="1">a</p><img DATA-STEP="x"/><b data-step>c</b><i>none</i>'
        ))
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "Studio" / "work" / "presentations" / "steps"
            unit.parent.mkdir(parents=True)
            unit.mkdir()
            scaffold_unit(unit, "Steps")
            write_deck(unit, base_deck(slides=slides))
            stderr, stdout = StringIO(), StringIO()
            with redirect_stderr(stderr), patch("sys.stdout", stdout):
                code = main(["check", "steps", "--repo", root])
            self.assertEqual(0, code)
            self.assertIn("OK: steps", stdout.getvalue())
            self.assertEqual(3, stderr.getvalue().count("WARNING: deck.json: slides["))
            self.assertNotIn("ERROR", stderr.getvalue())
            # Errors and warnings print together; errors still fail check.
            write_deck(unit, base_deck(slides=[*slides, {"id": "bad", "body": "<p data-step=0>"}]))
            stderr = StringIO()
            with redirect_stderr(stderr), patch("sys.stdout", StringIO()):
                code = main(["check", "steps", "--repo", root])
            self.assertEqual(2, code)
            self.assertIn("ERROR: deck.json: slides[5].body has data-step='0'", stderr.getvalue())
            self.assertIn("WARNING: deck.json: slides[1] (gappy)", stderr.getvalue())

    def test_a_step_nested_in_a_later_one_warns(self):
        slides = [
            {"id": "html", "body": '<div data-step="2"><img src="assets/a.png" data-step="3">'
                                   '<span data-step="1">early</span></div><p data-step="1">a</p>'},
            {"id": "caption", "figure": {"src": "assets/a.png", "step": 2,
                                         "caption": '<b data-step="1">read first</b>'}},
            {"id": "card", "cards": [{"value": '<i data-step="1">v</i>', "step": 3}]},
            {"id": "formula", "formula": {
                "mathml": "<math><mi data-step='1'>x</mi></math>", "step": 2,
                "gloss": ['<span data-step="2">same</span>',
                          '<div data-step="3"><b data-step="1">z</b></div>']}},
            {"id": "video", "video": {"src": "assets/clip.mp4", "step": 1,
                                      "caption": '<span data-step="2">after</span>'}},
            # Equal or later numbers inside a step are fine; void elements
            # and closed elements enclose nothing.
            {"id": "fine", "body": '<p data-step="1"><b data-step="1">a</b>'
                                   '<i data-step="2">b</i></p><br data-step="3"><p>c</p>'},
        ]
        nested = [w for w in deck_warnings(base_deck(slides=slides)) if " inside " in w]
        self.assertEqual(
            [
                'deck.json: slides[0].body has data-step="1" inside a data-step="2" element; '
                "it appears with step 2, not before it",
                'deck.json: slides[1].figure.caption has data-step="1" inside '
                "slides[1].figure (step 2); it appears with step 2, not before it",
                'deck.json: slides[2].cards[0].value has data-step="1" inside '
                "slides[2].cards[0] (step 3); it appears with step 3, not before it",
                'deck.json: slides[3].formula.mathml has data-step="1" inside '
                "slides[3].formula (step 2); it appears with step 2, not before it",
                'deck.json: slides[3].formula.gloss[1] has data-step="1" inside a '
                'data-step="3" element; it appears with step 3, not before it',
            ],
            nested,
        )
        # The gap check counts the steps a press reveals: the nested step
        # is no level of its own.
        self.assertIn(
            "deck.json: slides[1] (caption) skips step 1 (uses 2); "
            "each press still reveals the next number used",
            deck_warnings(base_deck(slides=slides)),
        )
        with tempfile.TemporaryDirectory() as root:
            unit = self.stepped_unit(root, slides)
            self.assertEqual([], validate_unit(unit))

    def test_course_and_opening_labels_cannot_hold_steps(self):
        for key, shown in (("section", "every slide's footer"), ("opening", "the eyebrow")):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as root:
                deck = base_deck()
                deck["meta"][key] = '<span data-step="1">LABEL</span>'
                unit = make_json_unit(root, deck)
                self.assertHasError(
                    validate_unit(unit),
                    f"deck.json: meta.{key} cannot hold a data-step; it is shown in {shown}",
                )
        # A section slide's stepped title is fine: only that slide steps it.
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(slides=[
                {"id": "part", "type": "section", "title": '<span data-step="1">Part</span>'},
                {"id": "after", "title": "After"},
            ]))
            self.assertEqual([], validate_unit(unit))

    def test_deck_json_requires_viewer_version(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(requires=">=99.0"))
            self.assertHasError(validate_unit(unit), "requires viewer >=99.0")
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(requires=">=0.1"))
            self.assertEqual([], validate_unit(unit))

    def test_deck_json_asset_references_are_validated(self):
        figure_slide = {
            "id": "figure-slide",
            "title": "Figure",
            "figure": {"src": "assets/figure.png", "alt": "A figure"},
        }
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(slides=[figure_slide]))
            self.assertHasError(validate_unit(unit), "figure.src is missing: assets/figure.png")
            (unit / "webdeck" / "assets" / "figure.png").write_bytes(b"fixture")
            self.assertEqual([], validate_unit(unit))
        cases = [
            ({"src": "https://example.com/x.png"}, "must be a local path"),
            ({"src": "/assets/x.png"}, "must be a relative forward-slash path"),
            ({"src": "assets\\x.png"}, "must be a relative forward-slash path"),
            ({"src": "../private.png"}, "escapes webdeck"),
        ]
        for figure, fragment in cases:
            with self.subTest(fragment=fragment):
                with tempfile.TemporaryDirectory() as root:
                    unit = make_json_unit(
                        root, base_deck(slides=[{"id": "a", "figure": figure}])
                    )
                    self.assertHasError(validate_unit(unit), fragment)

    def test_deck_json_favicon_presets_and_custom_asset_are_validated(self):
        for preset in ("complex", "calculus", "plasma"):
            with self.subTest(preset=preset), tempfile.TemporaryDirectory() as root:
                deck = base_deck(meta={"title": "x", "favicon": preset})
                self.assertEqual([], validate_unit(make_json_unit(root, deck)))

        with tempfile.TemporaryDirectory() as root:
            deck = base_deck(meta={"title": "x", "favicon": "assets/favicon.svg"})
            unit = make_json_unit(root, deck)
            self.assertHasError(validate_unit(unit), "meta.favicon is missing")
            favicon = unit / "webdeck" / "assets" / "favicon.svg"
            favicon.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
            self.assertEqual([], validate_unit(unit))
            output = Path(root) / "release"
            release_unit(unit, output)
            self.assertTrue((output / "assets" / "favicon.svg").is_file())

    def test_deck_json_video_assets_are_validated(self):
        video_slide = {
            "id": "video-slide",
            "title": "Video",
            "video": {
                "src": "assets/clip.mp4",
                "type": "video/mp4",
                "poster": "assets/poster.jpg",
                "originalUrl": "https://example.com/original",
                "tracks": [{"src": "assets/captions.vtt", "kind": "captions", "srclang": "en"}],
            },
        }
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(slides=[video_slide]))
            assets = unit / "webdeck" / "assets"
            for name in ("clip.mp4", "poster.jpg", "captions.vtt"):
                (assets / name).write_bytes(b"fixture")
            self.assertEqual([], validate_unit(unit))
            (assets / "captions.vtt").unlink()
            self.assertHasError(validate_unit(unit), "captions.vtt")

    def test_deck_json_interactive_entry_is_validated(self):
        slide = {
            "id": "demo",
            "chrome": False,
            "interactive": {"src": "assets/demo/index.html", "title": "Demo"},
        }
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root, base_deck(slides=[slide]))
            self.assertHasError(validate_unit(unit), "interactive.src is missing")
            demo = unit / "webdeck" / "assets" / "demo"
            demo.mkdir(parents=True)
            (demo / "index.html").write_text("<canvas></canvas>", encoding="utf-8")
            self.assertEqual([], validate_unit(unit))

    def test_legacy_local_video_assets_are_validated(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_legacy_unit(root)
            webdeck = unit / "webdeck"
            assets = webdeck / "assets"
            for name in ("clip.mp4", "poster.jpg", "captions.vtt"):
                (assets / name).write_bytes(b"fixture")
            slides = webdeck / "slides.js"
            slides.write_text(
                slides.read_text(encoding="utf-8")
                + '\nconst videoFixture = {video: {src: "assets/clip.mp4", '
                'poster: "assets/poster.jpg", tracks: [{src: "assets/captions.vtt"}], '
                'originalUrl: "https://example.com/original"}};\n',
                encoding="utf-8",
            )
            self.assertEqual([], validate_unit(unit))
            (assets / "captions.vtt").unlink()
            self.assertHasError(validate_unit(unit), "captions.vtt")

    def test_nested_interactive_references_resolve_locally(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            demo = unit / "webdeck" / "assets" / "demo"
            demo.mkdir(parents=True)
            (demo / "index.html").write_text(
                '<link rel="stylesheet" href="style.css"><script src="./sketch.js"></script>',
                encoding="utf-8",
            )
            (demo / "style.css").write_text("canvas { display: block; }", encoding="utf-8")
            (demo / "sketch.js").write_text("console.log('demo');", encoding="utf-8")
            self.assertEqual([], validate_unit(unit))
            (demo / "sketch.js").unlink()
            self.assertHasError(
                validate_unit(unit), "missing reference in assets/demo/index.html: ./sketch.js"
            )

    def test_nested_css_references_are_checked(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            demo = unit / "webdeck" / "assets" / "demo"
            demo.mkdir(parents=True)
            (demo / "style.css").write_text(
                '@import "palette.css";\n'
                ".bg { background: url(bg.png); }\n"
                ".inline { background: url(\"data:image/png;base64,AAA\"); }\n"
                ".frag { fill: url(#gradient); }\n",
                encoding="utf-8",
            )
            errors = validate_unit(unit)
            self.assertHasError(errors, "missing reference in assets/demo/style.css: palette.css")
            self.assertHasError(errors, "missing reference in assets/demo/style.css: bg.png")
            self.assertFalse(any("data:" in error for error in errors), errors)
            self.assertFalse(any("#gradient" in error for error in errors), errors)
            (demo / "palette.css").write_text(":root { --x: 1; }", encoding="utf-8")
            (demo / "bg.png").write_bytes(b"fixture")
            self.assertEqual([], validate_unit(unit))

    def test_module_imports_are_checked(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            demo = unit / "webdeck" / "assets" / "demo"
            demo.mkdir(parents=True)
            (demo / "app.js").write_text(
                'import { helper } from "./lib.js";\n'
                'export * from "./util.js";\n'
                'import "./side-effect.js";\n'
                'const lazy = () => import("./lazy.js");\n',
                encoding="utf-8",
            )
            errors = validate_unit(unit)
            for name in ("./lib.js", "./util.js", "./side-effect.js", "./lazy.js"):
                self.assertHasError(errors, f"missing reference in assets/demo/app.js: {name}")
            for name in ("lib.js", "util.js", "side-effect.js", "lazy.js"):
                (demo / name).write_text("export const helper = 1;", encoding="utf-8")
            self.assertEqual([], validate_unit(unit))
            (demo / "app.js").write_text(
                'import "https://cdn.example.com/x.js";\nimport lodash from "lodash";\n',
                encoding="utf-8",
            )
            errors = validate_unit(unit)
            self.assertHasError(
                errors, "external dependency in assets/demo/app.js: https://cdn.example.com/x.js"
            )
            self.assertHasError(errors, "unresolvable module import in assets/demo/app.js: lodash")

    def test_root_index_relative_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            (unit / "script.md").write_text("private notes", encoding="utf-8")
            index = packaged_text("index.html").replace(
                "</body>", '<img src="../script.md"></body>'
            )
            (unit / "webdeck" / "index.html").write_text(index, encoding="utf-8")
            self.assertHasError(validate_unit(unit), "reference escapes webdeck")

    def test_packaged_fallback_is_limited_to_viewer_files(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            index = packaged_text("index.html").replace(
                "</body>", '<script src="adjust.js"></script></body>'
            )
            (unit / "webdeck" / "index.html").write_text(index, encoding="utf-8")
            self.assertHasError(validate_unit(unit), "missing reference in index.html: adjust.js")

    def test_serve_lan_shortcut(self):
        args = build_parser().parse_args(["serve", "sample-unit", "--lan"])
        self.assertTrue(args.lan)
        self.assertEqual("127.0.0.1", args.host)

    def test_serve_flushes_banner_before_entering_loop(self):
        for reload_args in ([], ["--livereload"]):
            with self.subTest(reload=bool(reload_args)), tempfile.TemporaryDirectory() as root:
                make_json_unit(root)
                args = build_parser().parse_args(["serve", "--folder", root, *reload_args])
                raw = BytesIO()
                output = TextIOWrapper(raw, encoding="utf-8")
                server = Mock(server_address=("127.0.0.1", 48943))

                def check_banner():
                    self.assertIn(b"http://127.0.0.1:48943/", raw.getvalue())
                    if reload_args:
                        self.assertIn(b"Live reload: on", raw.getvalue())
                    raise KeyboardInterrupt

                server.serve_forever.side_effect = check_banner
                with (
                    patch("lecturedeck.cli.make_available_server", return_value=(server, 48943)),
                    patch("lecturedeck.cli.sys.stdout", output),
                ):
                    self.assertEqual(0, serve(args))
                server.server_close.assert_called_once()
                output.close()

    def test_serve_pacing_records_flag_reaches_server_and_banner(self):
        self.assertTrue(build_parser().parse_args(["serve", "sample-unit"]).pacing_records)
        cases = (
            ([], "  Pacing records: <unit>/pacing-records/ on scheduled dates "
                 "(browser on this computer only)\n"),
            (["--no-pacing-records"], "  Pacing records: off\n"),
        )
        for flags, line in cases:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as root:
                make_json_unit(root)
                args = build_parser().parse_args(["serve", "--folder", root, *flags])
                self.assertEqual(not flags, args.pacing_records)
                output = StringIO()
                server = Mock(server_address=("127.0.0.1", 48943))
                server.serve_forever.side_effect = KeyboardInterrupt
                with (
                    patch(
                        "lecturedeck.cli.make_available_server", return_value=(server, 48943)
                    ) as factory,
                    patch("lecturedeck.cli.sys.stdout", output),
                ):
                    self.assertEqual(0, serve(args))
                self.assertIs(not flags, factory.call_args.kwargs["pacing_records"])
                banner = output.getvalue()
                self.assertIn(line, banner)
                self.assertLess(banner.index("Access:"), banner.index("Pacing records:"))

    def test_make_available_server_passes_pacing_records(self):
        for selector, factory_name in ((False, "make_server"), (True, "make_selector_server")):
            for enabled in (True, False):
                with (
                    self.subTest(selector=selector, enabled=enabled),
                    patch(f"lecturedeck.cli.{factory_name}") as factory,
                ):
                    make_available_server(
                        Path("root"), "127.0.0.1", 48943, False,
                        auto_advance=False, selector=selector, pacing_records=enabled,
                    )
                    factory.assert_called_once_with(
                        Path("root"), "127.0.0.1", 48943, False, pacing_records=enabled
                    )
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            server, _ = make_available_server(
                unit, "127.0.0.1", 0, False, auto_advance=False, pacing_records=False
            )
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("GET", "/__lecturedeck/version")
                self.assertEqual("off", json.loads(connection.getresponse().read())["pacing"])
                connection.close()
            finally:
                server.shutdown()
                server.server_close()

    def test_repository_selector_folder_is_persistent_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.assertEqual(repo / "Studio/work/presentations", selector_folder(repo))
            config = repo / "lecturedeck.toml"
            config.write_text('[selector]\nfolder = "release/teaching"\n')
            self.assertEqual((repo / "release/teaching").resolve(), selector_folder(repo))
            config.write_text('[selector]\nfolder = "../outside"\n')
            with self.assertRaises(RuntimeError):
                selector_folder(repo)
            config.write_text('[selector]\nfolder = 42\n')
            with self.assertRaises(RuntimeError):
                selector_folder(repo)

    def test_serve_without_unit_selects_a_folder(self):
        args = build_parser().parse_args(["serve", "--folder", "presentations"])
        self.assertIsNone(args.unit)
        self.assertEqual(Path("presentations"), args.folder)

    def test_serve_repo_and_folder_are_mutually_exclusive(self):
        parser = build_parser()
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["serve", "--repo", "course", "--folder", "decks"])

    def test_pdf_cli_defaults_to_light_theme(self):
        args = build_parser().parse_args(
            ["pdf", "sample-unit", "--output", "sample.pdf"]
        )
        self.assertEqual("pdf", args.command)
        self.assertEqual("light", args.theme)
        self.assertEqual(Path("sample.pdf"), args.output)

    def test_pdf_export_requires_new_pdf_path(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            with self.assertRaisesRegex(ValueError, r"must end in \.pdf"):
                export_pdf(unit, Path(root) / "slides.out")
            existing = Path(root) / "slides.pdf"
            existing.write_bytes(b"keep")
            with self.assertRaisesRegex(FileExistsError, "already exists"):
                export_pdf(unit, existing)
            self.assertEqual(b"keep", existing.read_bytes())

    def test_pdf_export_server_never_offers_pacing_records(self):
        playwright = types.ModuleType("playwright")
        sync_api = types.ModuleType("playwright.sync_api")
        sync_api.sync_playwright = Mock()
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            with (
                patch.dict(sys.modules, {"playwright": playwright,
                                         "playwright.sync_api": sync_api}),
                patch("lecturedeck.pdf.make_server", side_effect=RuntimeError("stop")) as fake,
            ):
                with self.assertRaisesRegex(RuntimeError, "stop"):
                    export_pdf(unit, Path(root) / "slides.pdf")
            fake.assert_called_once_with(
                unit, "127.0.0.1", 0, livereload=False, quiet=True, pacing_records=False
            )
            self.assertFalse((Path(root) / "slides.pdf").exists())

    def test_serve_default_port_is_automatic(self):
        args = build_parser().parse_args(["serve", "sample-unit"])
        self.assertIsNone(args.port)
        self.assertEqual(4173, DEFAULT_PORT)

    def test_automatic_port_advances_when_first_port_is_busy(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            first = make_server(unit, "127.0.0.1", 0, livereload=False)
            occupied_port = first.server_address[1]
            try:
                second, selected_port = make_available_server(
                    unit,
                    "127.0.0.1",
                    occupied_port,
                    False,
                    auto_advance=True,
                )
                try:
                    self.assertGreater(selected_port, occupied_port)
                    self.assertEqual(selected_port, second.server_address[1])
                finally:
                    second.server_close()
            finally:
                first.server_close()

    def test_explicit_busy_port_remains_strict(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            first = make_server(unit, "127.0.0.1", 0, livereload=False)
            occupied_port = first.server_address[1]
            try:
                with self.assertRaises(OSError):
                    make_available_server(
                        unit,
                        "127.0.0.1",
                        occupied_port,
                        False,
                        auto_advance=False,
                    )
            finally:
                first.server_close()

    def test_serve_lan_and_host_are_mutually_exclusive(self):
        parser = build_parser()
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["serve", "sample-unit", "--lan", "--host", "192.0.2.10"])

    def test_runtime_features_are_packaged(self):
        index = packaged_text("index.html")
        script = packaged_text("lecturedeck.js")
        styles = packaged_text("lecturedeck.css")
        self.assertIn('id="previous-button"', index)
        self.assertIn('href="deck.css"', index)
        self.assertIn('id="appearance-button"', index)
        self.assertIn('id="appearance-dialog"', index)
        self.assertIn('name="color-mode"', index)
        self.assertIn('name="presentation-style"', index)
        self.assertIn('id="controls-toggle"', index)
        self.assertIn('id="controls-tools"', index)
        self.assertIn('aria-label="Show presentation controls"', index)
        self.assertIn("&#9881;&#65039;", index)
        self.assertIn('id="deck-selector-link"', index)
        self.assertIn('aria-label="Back to deck selector"', index)
        self.assertNotIn("slides.js", index)
        self.assertIn('id="viewer-version"', index)
        self.assertIn(f'const VIEWER_VERSION = "{__version__}"', script)
        self.assertIn('fetch("deck.json"', script)
        self.assertIn('fetch("../__lecturedeck/version"', script)
        self.assertIn("loadLegacySpec", script)
        self.assertIn('script.src = "slides.js"', script)
        self.assertIn("window.LECTUREDECK = spec", script)
        self.assertIn("deckLoadError", script)
        self.assertIn("data-slide-id", script)
        self.assertIn("function slideNumbering", script)
        self.assertIn("data-appendix", script)
        self.assertIn('"in-appendix"', script)
        self.assertIn("webkitRequestFullscreen", script)
        self.assertIn("function setTheme", script)
        self.assertIn("function setPresentationStyle", script)
        self.assertIn("function setFavicon", script)
        self.assertIn("complex:", script)
        self.assertIn("calculus:", script)
        self.assertIn("plasma:", script)
        self.assertIn("lecturedeck-presentation-style", script)
        self.assertIn("function positionControls", script)
        self.assertIn("controlsTools.inert", script)
        self.assertIn("escapedNativeFullscreen", script)
        self.assertIn("deliberateNativeFullscreenExit", script)
        self.assertIn('addEventListener("wheel"', script)
        self.assertIn("function partAccent", script)
        self.assertIn("slide.className", script)
        self.assertIn("function videoMarkup", script)
        self.assertIn("function figureGeometry", script)
        self.assertIn("function fitFormulas", script)
        self.assertIn("function renderPrintDeck", script)
        self.assertIn("LECTUREDECK_PRINT_READY", script)
        self.assertIn("data-figure-index", script)
        self.assertIn("figure.shift", script)
        self.assertIn("controls playsinline", script)
        self.assertIn('event.target.closest("video, audio', script)
        self.assertIn("body.immersive-slide .touch-nav", styles)
        self.assertIn("body.light-theme", styles)
        self.assertIn('body[data-presentation-style="gradient"]', styles)
        self.assertIn(".appearance-dialog", styles)
        self.assertIn(".deck-error", styles)
        self.assertIn(".formula-gloss > span", styles)
        self.assertIn(".controls-tools > *", styles)
        self.assertIn(".deck-chrome .controls-toggle", styles)
        self.assertIn(".deck-chrome .control-link[hidden]", styles)
        self.assertIn('mtable[columnalign="right left"]', styles)
        self.assertIn(".slide-frame.style-gradient", styles)
        self.assertIn(".style-title-rule,", styles)
        self.assertIn(".deck-chrome.has-safe-space", styles)
        self.assertIn(":fullscreen body.immersive-slide .deck-chrome", styles)
        self.assertIn("body.print-deck", styles)
        self.assertIn("@page", styles)
        self.assertIn(".layout-video", styles)
        self.assertIn("width: fit-content", styles)
        self.assertIn("justify-self: center", styles)
        self.assertIn(".body-copy table", styles)
        # Step-by-step reveals: the live slide alone hides steps, in place,
        # with a fade that reduced motion and print drop.
        self.assertIn("function parseSlideHash", script)
        self.assertIn("function collectSteps", script)
        self.assertIn('querySelectorAll("[data-step]")', script)
        self.assertIn('"step-hidden"', script)
        self.assertIn('stepIndicator.id = "step-indicator"', script)
        self.assertIn(".step-indicator[hidden]", styles)
        self.assertIn(".slide-frame .step-hidden { opacity: 0; visibility: hidden;", styles)
        self.assertIn("prefers-reduced-motion: reduce", styles)
        self.assertIn(".slide-frame.steps-settling [data-step]", styles)
        self.assertIn("function refreshSteps", script)
        self.assertIn("data-step-src", script)
        self.assertIn('cue.className = "step-cue"', script)
        self.assertIn(".footer-nav .step-cue i.shown", styles)
        # The photo viewer: a dialog built after the print return, its
        # settings per deck in local storage, a correction weak enough for
        # deck.css to override, no pacing pause, nothing in print.
        self.assertIn('viewer.id = "photo-viewer"', script)
        self.assertIn("viewer.showModal()", script)
        self.assertIn("lecturedeck-photo:", script)
        self.assertIn('dialog[open]:not(.photo-viewer)', script)
        self.assertIn('button.className = "photo-expand"', script)
        self.assertIn('[data-photo="off"]', script)
        self.assertIn(".photo-viewer[open] { display: grid;", styles)
        self.assertIn(":where(body.photos-corrected) .photo-content", styles)
        self.assertIn(".photo-viewer, .photo-viewer[open] { display: none; }", styles)
        self.assertLess(script.index("if (printMode) {\n      renderPrintDeck();"),
                        script.index('viewer.id = "photo-viewer"'))
        self.assertNotIn("photo-viewer", index)
        # Photo hotspots: built after the print return like the viewer, a
        # deck-wide H switch kept for the tab, nothing in print.
        self.assertLess(script.index("if (printMode) {\n      renderPrintDeck();"),
                        script.index("function hotspotSurface"))
        self.assertIn("lecturedeck-hotspot-rings:", script)
        self.assertIn('ring.className = "hotspot"', script)
        # The layer is the frame's child: a positioned figure card lays out
        # at another width in WebKit, so the card is never restyled.
        self.assertIn("frame.append(layer)", script)
        self.assertNotIn("has-hotspots {", styles)
        self.assertIn(".slide-frame .hotspot-layer.hotspot-stepped-out {", styles)
        self.assertIn(
            "@media print { .hotspot-layer, .hotspot-popup { display: none !important; } }", styles)
        self.assertNotIn("hotspot", index)
        # The viewer records, journals and reports pacing, and reaches disk only
        # through the sink it looks up; any open dialog owns deck input.
        self.assertIn("lecturedeckPacingSink", script)
        self.assertIn("lecturedeck-pacing2:", script)
        self.assertIn("dialog[open]", script)
        self.assertIn("function summarizePacing", script)
        self.assertIn(".pacing-dialog[open]", styles)
        self.assertIn('[data-saved="failing"]', styles)
        # Releases carry no write code: the endpoint lives only in the serve-only sink.
        self.assertNotIn("__lecturedeck/pacing", script)
        self.assertNotIn("__lecturedeck/pacing", index)
        self.assertNotIn("pacing-sink.js", VIEWER_FILES)
        sink = packaged_text("pacing-sink.js")
        self.assertIn("X-Lecturedeck-Pacing", sink)
        self.assertIn("navigator.webdriver", sink)
        self.assertIn("window.lecturedeckPacingSink = Object.freeze", sink)
        self.assertIn('credentials: "same-origin"', sink)
        self.assertIn('"../__lecturedeck/pacing"', sink)
        # The sink answers the server's own 413 itself: a refused large upload
        # often reaches the browser as a network error, retried forever.
        self.assertIn(f"const MAX_BODY = {pacing.MAX_BODY};", sink)
        adjust = packaged_text("adjust.js")
        self.assertIn("const spec = () => window.LECTUREDECK", adjust)
        self.assertIn("event.stopPropagation()", adjust)
        self.assertIn("overviewVisible", adjust)
        self.assertIn("MutationObserver", adjust)
        self.assertIn('document.querySelector("dialog[open]")', adjust)
        # "#/N.k" step addresses still name slide N for adjustment.
        self.assertIn(r"/^#\/(\d+)/.exec(location.hash)", adjust)

    def test_photo_viewer_keys_are_documented_and_free(self):
        script = packaged_text("lecturedeck.js")
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        section = readme.split("### Photo viewer", 1)[1].split("\n## ", 1)[0]
        # Each key the viewer reads is in the README's table.
        for key, documented in (('"b"', "`B` / `Shift`+`B`"), ('"c"', "`C` / `Shift`+`C`"),
                                ('"+", "="', "`+` / `-` (also `=` / `_`)"), ('"0"', "`0`"),
                                ('"a"', "`A`"), ('"l"', "`L`"), ('"h"', "`H`")):
            self.assertIn(key, script)
            self.assertIn(documented, section)
        # None of them is a deck shortcut: the deck's handler reads only o,
        # f, l, t, h (and the serve-only adjust HUD g); L is the laser and H
        # the hotspot hint rings in both.
        deck_keys = set(re.findall(r'event\.key\.toLowerCase\(\) === "(\w)"', script))
        self.assertEqual({"o", "f", "l", "t", "h"}, deck_keys)
        adjust_keys = set(re.findall(r'event\.key\.toLowerCase\(\) === "(\w)"',
                                     packaged_text("adjust.js")))
        self.assertEqual({"g"}, adjust_keys)
        hotspots = readme.split("### Photo hotspots", 1)[1].split("\n## ", 1)[0]
        self.assertIn("| `H` |", hotspots)
        self.assertIn("Use on all photos", section)
        self.assertIn('data-photo="off"', section)

    def test_scaffold_has_no_course_specific_identity(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Generic deck")
            combined = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (unit / "webdeck").iterdir()
                if path.is_file()
            )
            self.assertNotIn("window.LECTUREDECK", combined)
            self.assertIn('"deck": 1', combined)
            self.assertIn("COURSE TITLE", combined)

    def test_published_hashes_include_current_runtime(self):
        for name in scaffold.RUNTIME_FILES:
            self.assertIn(
                runtime_hash(packaged_text(name)), scaffold.PUBLISHED_RUNTIME_HASHES, name
            )

    def test_refresh_updates_legacy_snapshots_and_ignores_content_only_units(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            self.assertEqual(
                [("lecturedeck.css", "missing"), ("lecturedeck.js", "missing")],
                refresh_unit(unit),
            )
            webdeck = unit / "webdeck"
            for name in scaffold.RUNTIME_FILES:
                (webdeck / name).write_text(packaged_text(name), encoding="utf-8", newline="\n")
            self.assertEqual(
                [("lecturedeck.css", "current"), ("lecturedeck.js", "current")],
                refresh_unit(unit),
            )
            stale = "// an older published runtime\n"
            (webdeck / "lecturedeck.js").write_text(stale, encoding="utf-8", newline="\n")
            original_hashes = scaffold.PUBLISHED_RUNTIME_HASHES
            scaffold.PUBLISHED_RUNTIME_HASHES = original_hashes | {runtime_hash(stale)}
            try:
                self.assertIn(("lecturedeck.js", "refreshed"), refresh_unit(unit))
            finally:
                scaffold.PUBLISHED_RUNTIME_HASHES = original_hashes
            fork = packaged_text("lecturedeck.js") + "// local fork\n"
            (webdeck / "lecturedeck.js").write_text(fork, encoding="utf-8", newline="\n")
            self.assertIn(("lecturedeck.js", "kept"), refresh_unit(unit))
            self.assertIn(("lecturedeck.js", "refreshed"), refresh_unit(unit, force=True))

    def test_refresh_requires_deck_content(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            (unit / "webdeck").mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):
                refresh_unit(unit)

    def test_refresh_treats_crlf_snapshot_as_clean(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            target = unit / "webdeck" / "lecturedeck.css"
            target.write_text(
                packaged_text("lecturedeck.css").replace("\n", "\r\n"),
                encoding="utf-8",
                newline="",
            )
            self.assertIn(("lecturedeck.css", "current"), refresh_unit(unit))

    def test_server_serves_packaged_viewer_content_and_unit_override(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_json_unit(root)
            webdeck = unit / "webdeck"
            custom_css = "/* unit deck css */"
            (webdeck / "deck.css").write_text(custom_css, encoding="utf-8")
            (unit / "script.md").write_text("private lecture notes", encoding="utf-8")
            server = make_server(unit, "127.0.0.1", 0, livereload=False)
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                def request(path, method="GET"):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    try:
                        connection.request(method, path)
                        response = connection.getresponse()
                        return (
                            response.status,
                            response.read(),
                            response.getheader("Content-Type"),
                            response.getheader("Location"),
                        )
                    finally:
                        connection.close()

                status, body, _, _ = request("/webdeck/")
                self.assertEqual(200, status)
                self.assertIn(b"lecturedeck.js", body)
                self.assertIn(b"/__lecturedeck/adjust.js", body)
                self.assertIn(b'/__lecturedeck/pacing-sink.js" data-unit="unit"', body)
                self.assertEqual(200, request("/webdeck/lecturedeck.js", "HEAD")[0])
                status, body, content_type, _ = request("/__lecturedeck/adjust.js")
                self.assertEqual(200, status)
                self.assertIn(b"Geometry adjust", body)
                self.assertEqual("text/javascript", content_type)
                status, body, content_type, _ = request("/favicon.svg")
                self.assertEqual(200, status)
                self.assertIn(b"<svg", body)
                self.assertEqual("image/svg+xml", content_type)
                self.assertEqual(200, request("/favicon.svg", "HEAD")[0])
                self.assertEqual(custom_css.encode(), request("/webdeck/deck.css")[1])
                status, body, _, _ = request("/webdeck/deck.json")
                self.assertEqual(200, status)
                self.assertEqual(1, json.loads(body)["deck"])
                status, body, _, _ = request("/__lecturedeck/version")
                self.assertEqual(200, status)
                self.assertFalse(json.loads(body)["livereload"])
                self.assertEqual("on", json.loads(body)["pacing"])
                self.assertEqual(404, request("/pacing-records/")[0])
                self.assertEqual(302, request("/")[0])
                status, _, _, location = request("/webdeck")
                self.assertEqual(302, status)
                self.assertEqual("/webdeck/", location)
                self.assertEqual(302, request("/webdeck", "HEAD")[0])
                self.assertEqual(404, request("/script.md")[0])
                self.assertEqual(404, request("/webdeck/../script.md")[0])
                self.assertEqual(404, request("/webdeck/%2e%2e/script.md")[0])
                self.assertEqual(404, request("/webdeck/assets/")[0])
            finally:
                server.shutdown()
                server.server_close()

    def test_server_prefers_legacy_local_viewer(self):
        with tempfile.TemporaryDirectory() as root:
            unit = make_legacy_unit(root)
            local = b"/* local viewer */"
            (unit / "webdeck" / "lecturedeck.js").write_bytes(local)
            server = make_server(unit, "127.0.0.1", 0, livereload=False)
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("GET", "/webdeck/lecturedeck.js")
                response = connection.getresponse()
                self.assertEqual(local, response.read())
                connection.close()
            finally:
                server.shutdown()
                server.server_close()

    def test_selector_discovers_only_immediate_child_webdecks(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "presentations"
            folder.mkdir()
            alpha = folder / "alpha"
            alpha.mkdir()
            scaffold_unit(alpha, "Alpha deck")
            deck = base_deck()
            deck["meta"]["title"] = "Zeta title"
            deck["meta"]["section"] = "Example section"
            deck["meta"]["selectorGroup"] = "Seminars"
            deck["meta"]["selectorHero"] = "assets/hero.png"
            (alpha / "webdeck" / "assets" / "hero.png").write_bytes(b"hero")
            write_deck(alpha, deck)

            legacy = folder / "legacy"
            legacy.mkdir()
            webdeck = legacy / "webdeck"
            webdeck.mkdir()
            (webdeck / "slides.js").write_text(LEGACY_SLIDES, encoding="utf-8")

            nested = folder / "group" / "nested"
            nested.mkdir(parents=True)
            scaffold_unit(nested, "Nested deck")
            (folder / "notes.txt").write_text("not a deck", encoding="utf-8")

            decks = discover_decks(folder)
            self.assertEqual(["legacy", "alpha"], [deck.name for deck in decks])
            self.assertEqual("legacy", decks[0].title)
            self.assertEqual("Zeta title", decks[1].title)
            self.assertEqual("Example section", decks[1].section)
            self.assertEqual("Seminars", decks[1].group)
            self.assertEqual("assets/hero.png", decks[1].hero)

    def test_selector_serves_chosen_webdeck_and_nothing_adjacent(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "presentations"
            folder.mkdir()
            unit = folder / "unit one"
            unit.mkdir()
            scaffold_unit(unit, "Unsafe <title>")
            (unit / "private.md").write_text("private notes", encoding="utf-8")
            server = make_selector_server(folder, "127.0.0.1", 0, livereload=True)
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                def request(path, method="GET"):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    try:
                        connection.request(method, path)
                        response = connection.getresponse()
                        return (
                            response.status,
                            response.read(),
                            response.getheader("Location"),
                        )
                    finally:
                        connection.close()

                status, body, _ = request("/")
                self.assertEqual(200, status)
                self.assertIn(b"Unsafe &lt;title&gt;", body)
                self.assertIn(b'/decks/unit%20one/webdeck/', body)
                self.assertIn(b'data-group-filter="Lectures"', body)
                self.assertNotIn(b"Select a deck to present", body)
                self.assertIn(b'<link rel="icon" href="/favicon.svg"', body)
                self.assertIn(b"<svg", request("/favicon.svg")[1])
                self.assertEqual(200, request("/decks/unit%20one/webdeck/")[0])
                self.assertEqual(200, request("/decks/unit%20one/webdeck/deck.json")[0])
                status, body, _ = request("/decks/unit%20one/__lecturedeck/version")
                self.assertEqual(200, status)
                self.assertTrue(json.loads(body)["livereload"])
                status, _, location = request("/decks/unit%20one/webdeck")
                self.assertEqual(302, status)
                self.assertEqual("/decks/unit%20one/webdeck/", location)
                self.assertEqual(404, request("/decks/unit%20one/private.md")[0])
                self.assertEqual(404, request("/decks/unit%20one/webdeck/../private.md")[0])
                self.assertEqual(404, request("/decks/missing/webdeck/")[0])
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
