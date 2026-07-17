"""Strict, cache-free static server with a tiny live-reload endpoint."""

from __future__ import annotations

import json
import posixpath
from functools import partial
from hashlib import sha1
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import __version__


def content_version(root: Path) -> str:
    digest = sha1()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        stat = path.stat()
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()[:16]


class DeckRequestHandler(SimpleHTTPRequestHandler):
    server_version = f"lecturedeck/{__version__}"

    def __init__(self, *args, directory: str, livereload: bool, **kwargs):
        self.deck_root = Path(directory).resolve()
        self.livereload = livereload
        super().__init__(*args, directory=directory, **kwargs)

    def normalized_route(self) -> str:
        """Decoded, dot-segment-free request path, mirroring translate_path."""
        return posixpath.normpath(unquote(urlsplit(self.path).path))

    @staticmethod
    def serves(route: str) -> bool:
        """Only the unit's webdeck bundle is public; scripts and briefs are not."""
        return route == "/webdeck" or route.startswith("/webdeck/")

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        route = self.normalized_route()
        if route == "/__lecturedeck/version":
            payload = json.dumps(
                {
                    "version": content_version(self.deck_root / "webdeck"),
                    "livereload": self.livereload,
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        if route == "/":
            self.send_response(302)
            self.send_header("Location", "/webdeck/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not self.serves(route):
            self.send_error(HTTPStatus.NOT_FOUND, "Only webdeck/ is served")
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        if not self.serves(self.normalized_route()):
            self.send_error(HTTPStatus.NOT_FOUND, "Only webdeck/ is served")
            return
        super().do_HEAD()

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND, "Directory listings are disabled")
        return None

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def make_server(root: Path, host: str, port: int, livereload: bool) -> ThreadingHTTPServer:
    handler = partial(DeckRequestHandler, directory=str(root), livereload=livereload)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
