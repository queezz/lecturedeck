"""Render a checked lecture deck to a deterministic slide-sized PDF."""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from .server import make_server
from .validation import validate_unit


class PDFExportError(RuntimeError):
    """A PDF could not be rendered with the optional browser toolchain."""


def export_pdf(unit_root: Path, output: Path, *, theme: str = "light") -> Path:
    """Export every slide to one 16:9 PDF page through headless Chromium."""
    errors = validate_unit(unit_root)
    if errors:
        raise ValueError("; ".join(errors))

    output = output.resolve()
    if output.suffix.lower() != ".pdf":
        raise ValueError("PDF output must end in .pdf")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"output directory does not exist: {output.parent}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PDFExportError(
            'PDF export requires the optional toolchain. Install -e ".[pdf]", '
            "then run: python -m playwright install chromium"
        ) from exc

    server = make_server(unit_root, "127.0.0.1", 0, livereload=False, quiet=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = (
        f"http://127.0.0.1:{server.server_address[1]}/webdeck/"
        f"?print=1&theme={theme}"
    )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.stem}-", suffix=".pdf", dir=output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except Exception as exc:
                raise PDFExportError(
                    "Chromium is unavailable. Run: python -m playwright install chromium"
                ) from exc
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("window.LECTUREDECK_PRINT_READY === true")
                page.emulate_media(media="print")
                page.pdf(
                    path=str(temporary),
                    print_background=True,
                    prefer_css_page_size=True,
                    display_header_footer=False,
                )
            except Exception as exc:
                raise PDFExportError(f"Chromium could not render the deck ({exc})") from exc
            finally:
                browser.close()
        os.replace(temporary, output)
        temporary = None
        return output
    finally:
        server.shutdown()
        server.server_close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
