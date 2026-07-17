import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

from lecturedeck.cli import build_parser
from lecturedeck.scaffold import scaffold_unit
from lecturedeck.validation import release_unit, validate_unit


class LecturedeckTest(unittest.TestCase):
    def test_scaffold_check_and_release(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            created = scaffold_unit(unit, "Test deck")
            self.assertEqual(4, len(created))
            self.assertEqual([], validate_unit(unit))
            output = Path(root) / "release"
            release_unit(unit, output)
            self.assertTrue((output / "index.html").is_file())

    def test_external_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Test deck")
            index = unit / "webdeck" / "index.html"
            index.write_text(index.read_text() + '<script src="https://example.com/x.js"></script>')
            self.assertTrue(any("external dependency" in error for error in validate_unit(unit)))

    def test_external_source_link_is_not_a_runtime_dependency(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Test deck")
            index = unit / "webdeck" / "index.html"
            index.write_text(
                index.read_text()
                + '<a href="https://example.com/source">Source</a>',
                encoding="utf-8",
            )
            self.assertEqual([], validate_unit(unit))

    def test_serve_lan_shortcut(self):
        args = build_parser().parse_args(["serve", "sample-unit", "--lan"])
        self.assertTrue(args.lan)
        self.assertEqual("127.0.0.1", args.host)

    def test_serve_lan_and_host_are_mutually_exclusive(self):
        parser = build_parser()
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    ["serve", "sample-unit", "--lan", "--host", "192.0.2.10"]
                )

    def test_touch_navigation_is_packaged(self):
        with tempfile.TemporaryDirectory() as root:
            unit = Path(root) / "unit"
            unit.mkdir()
            scaffold_unit(unit, "Touch deck")
            webdeck = unit / "webdeck"
            index = (webdeck / "index.html").read_text(encoding="utf-8")
            script = (webdeck / "lecturedeck.js").read_text(encoding="utf-8")
            styles = (webdeck / "lecturedeck.css").read_text(encoding="utf-8")
            self.assertIn('id="previous-button"', index)
            self.assertIn('id="touch-fullscreen-button"', index)
            self.assertIn('id="next-button"', index)
            self.assertIn("webkitRequestFullscreen", script)
            self.assertIn("pseudo-fullscreen", script)
            self.assertIn("/__lecturedeck/version", script)
            self.assertIn("body.immersive-slide .touch-nav", styles)

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


if __name__ == "__main__":
    unittest.main()
