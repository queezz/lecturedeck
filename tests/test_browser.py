"""Chromium smoke suite for the presenter contract.

Runs only when the optional Playwright dev dependency and its Chromium
browser are installed; otherwise every test is skipped. The suite asserts
the mechanical contract — loading paths, navigation, wheel input, overview,
fullscreen, theme, media attributes, iframe interaction, and the serve-only
geometry-adjust guards. Visual density and pedagogical quality remain human
judgment and are deliberately out of scope.
"""

from __future__ import annotations

import json
import struct
import tempfile
import threading
import unittest
import zlib
from pathlib import Path

from lecturedeck import __version__
from lecturedeck.server import make_server

try:
    from playwright.sync_api import sync_playwright

    HAVE_PLAYWRIGHT = True
except ImportError:
    HAVE_PLAYWRIGHT = False


def png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        data = kind + payload
        return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    body = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", body) + chunk(b"IEND", b"")
    )


def build_json_unit(unit: Path) -> None:
    webdeck = unit / "webdeck"
    assets = webdeck / "assets"
    assets.mkdir(parents=True)
    (assets / "figure.png").write_bytes(png(320, 180, (131, 165, 152)))
    (assets / "poster.png").write_bytes(png(320, 180, (250, 189, 47)))
    (assets / "clip.mp4").write_bytes(b"not a real encoding; attributes only")
    demo = assets / "demo"
    demo.mkdir()
    (demo / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Demo</title>"
        "<body><button id='next'>Next slide</button>"
        "<script type='module' src='./app.js'></script></body>",
        encoding="utf-8",
    )
    (demo / "app.js").write_text(
        'import { advance } from "./lib.js";\n'
        "document.querySelector('#next').addEventListener('click', advance);\n",
        encoding="utf-8",
    )
    (demo / "lib.js").write_text(
        "export const advance = () =>"
        ' parent.postMessage({type: "lecturedeck:navigate", direction: 1}, "*");\n',
        encoding="utf-8",
    )
    deck = {
        "deck": 1,
        "meta": {"title": "Smoke deck", "section": "SMOKE", "opening": "OPENING"},
        "slides": [
            {"id": "s-title", "type": "title", "title": "Smoke deck", "claim": "Slide one."},
            {"id": "s-a", "title": "Statement A", "claim": "Second slide."},
            {
                "id": "s-figure",
                "title": "Figure",
                "figure": {
                    "id": "fig-1",
                    "src": "assets/figure.png",
                    "alt": "Figure",
                    "shift": [10, -6],
                    "scale": 1.1,
                },
            },
            {
                "id": "s-video",
                "title": "Video",
                "video": {
                    "src": "assets/clip.mp4",
                    "type": "video/mp4",
                    "poster": "assets/poster.png",
                    "title": "Smoke video",
                },
            },
            {
                "id": "s-interactive",
                "chrome": False,
                "interactive": {"src": "assets/demo/index.html", "title": "Demo"},
            },
            {"id": "s-b", "title": "Statement B", "claim": "Sixth slide."},
            {"id": "s-c", "title": "Statement C", "claim": "Seventh slide."},
            {"id": "s-d", "title": "Statement D", "claim": "Eighth slide."},
            {
                "id": "s-formula",
                "title": "Modest formula",
                "layout": "equation",
                "formula": {
                    "mathml": "<math xmlns='http://www.w3.org/1998/Math/MathML' "
                    "display='block'><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow></math>"
                },
            },
            {
                "id": "s-huge-formula",
                "title": "Oversized formula",
                "layout": "equation",
                "formula": {
                    "mathml": "<math xmlns='http://www.w3.org/1998/Math/MathML' "
                    "display='block'><mrow>"
                    + "<msup><mi>x</mi><mn>2</mn></msup><mo>+</mo>" * 12
                    + "<mn>1</mn></mrow></math>"
                },
            },
        ],
    }
    (webdeck / "deck.json").write_text(json.dumps(deck), encoding="utf-8")


def build_legacy_unit(unit: Path) -> None:
    webdeck = unit / "webdeck"
    (webdeck / "assets").mkdir(parents=True)
    (webdeck / "slides.js").write_text(
        "window.LECTUREDECK = {\n"
        '  meta: { title: "Legacy smoke", section: "SMOKE", opening: "OPENING" },\n'
        '  slides: [\n'
        '    { type: "title", title: "Legacy smoke", claim: "Fallback slide." },\n'
        '    { title: "Legacy two", claim: "Second legacy slide." }\n'
        "  ]\n"
        "};\n",
        encoding="utf-8",
    )


def build_broken_unit(unit: Path) -> None:
    webdeck = unit / "webdeck"
    (webdeck / "assets").mkdir(parents=True)
    (webdeck / "deck.json").write_text('{"deck": 1, broken', encoding="utf-8")


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright is not installed")
class BrowserSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._root = tempfile.TemporaryDirectory()
        root = Path(cls._root.name)
        cls.servers = []
        cls.urls = {}
        for name, builder in (
            ("json", build_json_unit),
            ("legacy", build_legacy_unit),
            ("broken", build_broken_unit),
        ):
            unit = root / name
            unit.mkdir()
            builder(unit)
            server = make_server(unit, "127.0.0.1", 0, livereload=False)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cls.servers.append(server)
            cls.urls[name] = f"http://127.0.0.1:{server.server_address[1]}/webdeck/"
        cls._playwright = sync_playwright().start()
        try:
            cls.browser = cls._playwright.chromium.launch()
        except Exception as exc:  # browser binaries absent
            cls._playwright.stop()
            for server in cls.servers:
                server.shutdown()
                server.server_close()
            cls._root.cleanup()
            raise unittest.SkipTest(f"chromium is not installed ({exc})")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
            cls._playwright.stop()
            for server in cls.servers:
                server.shutdown()
                server.server_close()
            cls._root.cleanup()

    def open_deck(self, name: str, fragment: str = ""):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.goto(self.urls[name] + fragment)
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        return page

    def current_index(self, page) -> int:
        return page.evaluate(
            "Number(document.querySelector('.slide-frame')?.dataset.index)"
        )

    def test_json_deck_loads_and_navigates(self):
        page = self.open_deck("json")
        self.assertIn("Smoke deck", page.title())
        self.assertEqual(10, page.evaluate("window.LECTUREDECK.slides.length"))
        self.assertEqual("s-title", page.evaluate(
            "document.querySelector('.slide-frame').dataset.slideId"
        ))
        page.keyboard.press("ArrowRight")
        self.assertEqual(1, self.current_index(page))
        page.keyboard.press("ArrowLeft")
        self.assertEqual(0, self.current_index(page))
        page.keyboard.press("End")
        self.assertEqual(9, self.current_index(page))
        page.keyboard.press("Home")
        self.assertEqual(0, self.current_index(page))
        self.assertEqual("1 / 10", page.text_content("#counter"))
        self.assertEqual(f"v{__version__}", page.text_content("#viewer-version"))

    def test_declarative_figure_geometry_renders(self):
        page = self.open_deck("json", "#/2")
        transform = page.evaluate(
            "document.querySelector('.figure-card').style.transform"
        )
        self.assertEqual("translate(10px, -6px) scale(1.1)", transform)
        self.assertEqual("fig-1", page.evaluate(
            "document.querySelector('.figure-card').dataset.figureId"
        ))

    def test_legacy_deck_loads_via_fallback(self):
        page = self.open_deck("legacy")
        self.assertIn("Legacy smoke", page.title())
        self.assertTrue(page.evaluate(
            "Boolean(document.querySelector('script[src=\"slides.js\"]'))"
        ))
        page.keyboard.press("ArrowRight")
        self.assertEqual(1, self.current_index(page))

    def test_broken_deck_json_reports_error(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.goto(self.urls["broken"])
        page.wait_for_selector(".deck-error")
        self.assertIn("not valid JSON", page.text_content(".deck-error"))

    def test_slashless_webdeck_redirects(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.goto(self.urls["json"].rstrip("/"))
        self.assertTrue(page.url.endswith("/webdeck/"))

    def test_rapid_wheel_notches_page_one_slide_each(self):
        page = self.open_deck("json")
        page.mouse.move(400, 300)
        for _ in range(3):
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(90)
        self.assertEqual(3, self.current_index(page))

    def test_trackpad_glide_pages_once(self):
        page = self.open_deck("json")
        page.mouse.move(400, 300)
        for _ in range(10):
            page.mouse.wheel(0, 15)
        page.wait_for_timeout(120)
        self.assertEqual(1, self.current_index(page))

    def test_overview_open_click_close(self):
        page = self.open_deck("json")
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        self.assertEqual(10, page.locator(".overview-card").count())
        page.locator(".overview-card[data-index='5']").click()
        page.wait_for_function("document.querySelector('#overview').hidden")
        self.assertEqual(5, self.current_index(page))
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")

    def test_fullscreen_toggles_and_exits(self):
        page = self.open_deck("json")
        page.keyboard.press("f")
        page.wait_for_function(
            "document.querySelector('#fullscreen-button').textContent === 'Exit full screen'"
        )
        native = page.evaluate("Boolean(document.fullscreenElement)")
        page.keyboard.press("f")
        page.wait_for_function(
            "document.querySelector('#fullscreen-button').textContent === 'Full screen'"
        )
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        if native:
            # Browser-reserved Escape exits native fullscreen and opens the overview.
            page.keyboard.press("f")
            page.wait_for_function("Boolean(document.fullscreenElement)")
            page.keyboard.press("Escape")
            page.wait_for_function("!document.querySelector('#overview').hidden")

    def test_theme_selection_persists(self):
        page = self.open_deck("json")
        page.keyboard.press("t")
        self.assertTrue(page.evaluate("document.body.classList.contains('light-theme')"))
        page.reload()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.assertTrue(page.evaluate("document.body.classList.contains('light-theme')"))
        page.keyboard.press("t")
        self.assertFalse(page.evaluate("document.body.classList.contains('light-theme')"))

    def test_video_slide_attributes_and_key_guard(self):
        page = self.open_deck("json", "#/3")
        video = page.locator("video")
        self.assertEqual("metadata", video.get_attribute("preload"))
        self.assertIsNotNone(video.get_attribute("controls"))
        self.assertIn("poster.png", video.get_attribute("poster"))
        page.evaluate("document.querySelector('video').focus()")
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(80)
        self.assertEqual(3, self.current_index(page))

    def test_interactive_iframe_pointer_navigates(self):
        page = self.open_deck("json", "#/4")
        page.wait_for_selector(".interactive-frame iframe")
        self.assertTrue(page.evaluate(
            "document.body.classList.contains('immersive-slide')"
        ))
        page.frame_locator(".interactive-frame iframe").locator("#next").click()
        page.wait_for_function(
            "Number(document.querySelector('.slide-frame')?.dataset.index) === 5"
        )

    def test_touch_swipe_navigates(self):
        page = self.open_deck("json")
        page.evaluate(
            """() => {
              const touch = x => new Touch({identifier: 1, target: document.body,
                clientX: x, clientY: 300});
              dispatchEvent(new TouchEvent("touchstart",
                {changedTouches: [touch(500)], bubbles: true}));
              dispatchEvent(new TouchEvent("touchend",
                {changedTouches: [touch(380)], bubbles: true}));
            }"""
        )
        self.assertEqual(1, self.current_index(page))

    def test_oversized_formula_shrinks_to_fit(self):
        page = self.open_deck("json", "#/9")
        page.wait_for_selector(".formula-math math")
        fitted = page.evaluate(
            """() => {
              const formula = document.querySelector('.formula');
              const math = formula.querySelector('.formula-math math');
              return {
                fontSize: parseFloat(getComputedStyle(formula).fontSize),
                inkWidth: math.scrollWidth,
                boxWidth: math.clientWidth,
              };
            }"""
        )
        self.assertLessEqual(fitted["inkWidth"], fitted["boxWidth"] + 2, fitted)
        self.assertLess(fitted["fontSize"], 72)

    def test_fitting_formula_keeps_stylesheet_size(self):
        page = self.open_deck("json", "#/8")
        page.wait_for_selector(".formula-math math")
        self.assertEqual(72, page.evaluate(
            "parseFloat(getComputedStyle(document.querySelector('.formula')).fontSize)"
        ))

    def test_controls_strip_is_single_row_and_stable(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 760})
        self.addCleanup(page.close)
        page.goto(self.urls["json"])
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        page.wait_for_selector(".slide-frame")

        def strip():
            return page.evaluate(
                "() => { const r = document.querySelector('#presentation-controls')"
                ".getBoundingClientRect();"
                " return {top: Math.round(r.top), height: Math.round(r.height)}; }"
            )

        first = strip()
        self.assertLessEqual(first["height"], 40, first)
        page.click("#controls-toggle")
        page.wait_for_timeout(250)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(100)
        page.click("#controls-toggle")
        page.wait_for_timeout(250)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(100)
        last = strip()
        self.assertEqual(first["top"], last["top"])
        self.assertLessEqual(last["height"], 40, last)
        self.assertLessEqual(last["top"] + last["height"], 760)

    def test_adjust_hud_nudges_without_paging(self):
        page = self.open_deck("json", "#/2")
        page.keyboard.press("g")
        page.wait_for_selector(".lecturedeck-adjust-hud:not([hidden])")
        page.keyboard.press("ArrowRight")
        self.assertEqual(2, self.current_index(page))
        self.assertIn("shift: [12, -6]", page.text_content(".lecturedeck-adjust-hud code"))
        page.keyboard.press("Escape")
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        page.wait_for_selector(".lecturedeck-adjust-hud", state="hidden")

    def test_adjust_hud_stays_off_the_overview(self):
        page = self.open_deck("json", "#/2")
        page.keyboard.press("g")
        page.wait_for_selector(".lecturedeck-adjust-hud:not([hidden])")
        page.keyboard.press("o")
        page.wait_for_selector(".lecturedeck-adjust-hud", state="hidden")
        page.keyboard.press("g")
        self.assertTrue(page.evaluate(
            "document.querySelector('.lecturedeck-adjust-hud').hidden"
        ))
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")


if __name__ == "__main__":
    unittest.main()
