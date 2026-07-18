import http.client
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from importlib.resources import files
from io import StringIO
from pathlib import Path

from lecturedeck import __version__, scaffold
from lecturedeck.cli import DEFAULT_PORT, build_parser, make_available_server
from lecturedeck.scaffold import refresh_unit, runtime_hash, scaffold_unit
from lecturedeck.server import make_server
from lecturedeck.validation import deck_entry, release_unit, validate_unit

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
        self.assertIn('id="theme-button"', index)
        self.assertIn('id="controls-toggle"', index)
        self.assertIn('id="controls-tools"', index)
        self.assertNotIn("slides.js", index)
        self.assertIn('id="viewer-version"', index)
        self.assertIn(f'const VIEWER_VERSION = "{__version__}"', script)
        self.assertIn('fetch("deck.json"', script)
        self.assertIn("loadLegacySpec", script)
        self.assertIn('script.src = "slides.js"', script)
        self.assertIn("window.LECTUREDECK = spec", script)
        self.assertIn("deckLoadError", script)
        self.assertIn("data-slide-id", script)
        self.assertIn("webkitRequestFullscreen", script)
        self.assertIn("function setTheme", script)
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
        self.assertIn("data-figure-index", script)
        self.assertIn("figure.shift", script)
        self.assertIn("controls playsinline", script)
        self.assertIn('event.target.closest("video, audio', script)
        self.assertIn("body.immersive-slide .touch-nav", styles)
        self.assertIn("body.light-theme", styles)
        self.assertIn(".deck-error", styles)
        self.assertIn(".slide-frame.style-gradient", styles)
        self.assertIn(".style-title-rule .slide-title::after", styles)
        self.assertIn(".deck-chrome.has-safe-space", styles)
        self.assertIn(":fullscreen .deck-chrome", styles)
        self.assertIn(".layout-video", styles)
        self.assertIn(".body-copy table", styles)
        adjust = packaged_text("adjust.js")
        self.assertIn("const spec = () => window.LECTUREDECK", adjust)
        self.assertIn("event.stopPropagation()", adjust)
        self.assertIn("overviewVisible", adjust)
        self.assertIn("MutationObserver", adjust)

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
                self.assertEqual(200, request("/webdeck/lecturedeck.js", "HEAD")[0])
                status, body, content_type, _ = request("/__lecturedeck/adjust.js")
                self.assertEqual(200, status)
                self.assertIn(b"Geometry adjust", body)
                self.assertEqual("text/javascript", content_type)
                self.assertEqual(custom_css.encode(), request("/webdeck/deck.css")[1])
                status, body, _, _ = request("/webdeck/deck.json")
                self.assertEqual(200, status)
                self.assertEqual(1, json.loads(body)["deck"])
                status, body, _, _ = request("/__lecturedeck/version")
                self.assertEqual(200, status)
                self.assertFalse(json.loads(body)["livereload"])
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


if __name__ == "__main__":
    unittest.main()
