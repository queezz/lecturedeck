import http.client
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from importlib.resources import files
from io import StringIO
from pathlib import Path

from lecturedeck import scaffold
from lecturedeck.cli import DEFAULT_PORT, build_parser, make_available_server
from lecturedeck.scaffold import refresh_unit, runtime_hash, scaffold_unit
from lecturedeck.server import make_server
from lecturedeck.validation import release_unit, validate_unit


def packaged_text(name: str) -> str:
    return files("lecturedeck").joinpath("assets", name).read_text(encoding="utf-8")


class LecturedeckTest(unittest.TestCase):
    def test_scaffold_is_content_only(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            created = scaffold_unit(unit, "Test deck")
            webdeck = unit / "webdeck"
            self.assertEqual({"deck.css", "slides.js"}, {path.name for path in created})
            self.assertTrue((webdeck / "assets").is_dir())
            self.assertFalse((webdeck / "index.html").exists())
            self.assertFalse((webdeck / "lecturedeck.js").exists())
            self.assertIn('title: "Test deck"', (webdeck / "slides.js").read_text())
            self.assertEqual([], validate_unit(unit))

    def test_release_materializes_viewer_and_preserves_unit_css(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Release deck")
            custom_css = ".claim { letter-spacing: .01em; }\n"
            (unit / "webdeck" / "deck.css").write_text(custom_css, encoding="utf-8")
            output = Path(root) / "release"
            release_unit(unit, output)
            for name in ("index.html", "lecturedeck.css", "lecturedeck.js", "slides.js"):
                self.assertTrue((output / name).is_file(), name)
            self.assertFalse((output / "adjust.js").exists())
            self.assertEqual(custom_css, (output / "deck.css").read_text(encoding="utf-8"))
            self.assertIn('href="deck.css"', (output / "index.html").read_text())

    def test_release_preserves_legacy_viewer_overrides(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Legacy deck")
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

    def test_external_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Test deck")
            index = unit / "webdeck" / "index.html"
            index.write_text(
                packaged_text("index.html") + '<script src="https://example.com/x.js"></script>',
                encoding="utf-8",
            )
            self.assertTrue(any("external dependency" in error for error in validate_unit(unit)))

    def test_external_source_link_is_not_a_runtime_dependency(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Test deck")
            slides = unit / "webdeck" / "slides.js"
            slides.write_text(
                slides.read_text(encoding="utf-8")
                + '\nconst source = \'<a href="https://example.com/source">Source</a>\';',
                encoding="utf-8",
            )
            self.assertEqual([], validate_unit(unit))

    def test_validation_accepts_unit_local_runtime_names(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Retained deck")
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
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Port test")
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
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Strict port test")
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
        self.assertIn("data-figure-index", script)
        self.assertIn("figure.shift", script)
        self.assertIn("controls playsinline", script)
        self.assertIn('event.target.closest("video, audio', script)
        self.assertIn("body.immersive-slide .touch-nav", styles)
        self.assertIn("body.light-theme", styles)
        self.assertIn(".slide-frame.style-gradient", styles)
        self.assertIn(".style-title-rule .slide-title::after", styles)
        self.assertIn(".deck-chrome.has-safe-space", styles)
        self.assertIn(":fullscreen .deck-chrome", styles)
        self.assertIn(".layout-video", styles)
        self.assertIn(".body-copy table", styles)

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
            self.assertIn("window.LECTUREDECK", combined)
            self.assertIn("COURSE TITLE", combined)

    def test_local_video_assets_are_validated(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Video deck")
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
            self.assertTrue(any("captions.vtt" in error for error in validate_unit(unit)))

    def test_published_hashes_include_current_runtime(self):
        for name in scaffold.RUNTIME_FILES:
            self.assertIn(
                runtime_hash(packaged_text(name)), scaffold.PUBLISHED_RUNTIME_HASHES, name
            )

    def test_refresh_updates_legacy_snapshots_and_ignores_content_only_units(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Refresh deck")
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

    def test_refresh_treats_crlf_snapshot_as_clean(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "CRLF deck")
            target = unit / "webdeck" / "lecturedeck.css"
            target.write_text(
                packaged_text("lecturedeck.css").replace("\n", "\r\n"),
                encoding="utf-8",
                newline="",
            )
            self.assertIn(("lecturedeck.css", "current"), refresh_unit(unit))

    def test_server_serves_packaged_viewer_content_and_unit_override(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Scope deck")
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
                        return response.status, response.read(), response.getheader("Content-Type")
                    finally:
                        connection.close()

                status, body, _ = request("/webdeck/")
                self.assertEqual(200, status)
                self.assertIn(b"lecturedeck.js", body)
                self.assertIn(b"/__lecturedeck/adjust.js", body)
                self.assertEqual(200, request("/webdeck/lecturedeck.js", "HEAD")[0])
                status, body, content_type = request("/__lecturedeck/adjust.js")
                self.assertEqual(200, status)
                self.assertIn(b"Geometry adjust", body)
                self.assertEqual("text/javascript", content_type)
                self.assertEqual(custom_css.encode(), request("/webdeck/deck.css")[1])
                status, body, _ = request("/__lecturedeck/version")
                self.assertEqual(200, status)
                self.assertFalse(json.loads(body)["livereload"])
                self.assertEqual(302, request("/")[0])
                self.assertEqual(404, request("/script.md")[0])
                self.assertEqual(404, request("/webdeck/../script.md")[0])
                self.assertEqual(404, request("/webdeck/%2e%2e/script.md")[0])
                self.assertEqual(404, request("/webdeck/assets/")[0])
            finally:
                server.shutdown()
                server.server_close()

    def test_server_prefers_legacy_local_viewer(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Legacy serve")
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
