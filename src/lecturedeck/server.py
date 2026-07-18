"""Strict, cache-free static server with a tiny live-reload endpoint."""

from __future__ import annotations

import json
import mimetypes
import posixpath
import socket
from functools import partial
from hashlib import sha1
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import __version__

VIEWER_ROUTES = {
    "/webdeck/lecturedeck.css": "lecturedeck.css",
    "/webdeck/lecturedeck.js": "lecturedeck.js",
    "/webdeck/deck.css": "deck.css",
}
INDEX_ROUTES = {"/webdeck", "/webdeck/index.html"}
ADJUST_ROUTE = "/__lecturedeck/adjust.js"


class DeckHTTPServer(ThreadingHTTPServer):
    """Threaded server with exclusive Windows port ownership."""

    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def content_version(root: Path) -> str:
    digest = sha1()
    digest.update(__version__.encode("ascii"))
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

    def needs_slash_redirect(self) -> bool:
        """The slashless deck root would break every relative deck URL."""
        return self.normalized_route() == "/webdeck" and not unquote(
            urlsplit(self.path).path
        ).endswith("/")

    def send_slash_redirect(self) -> None:
        self.send_response(302)
        self.send_header("Location", "/webdeck/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def packaged_asset(self, route: str):
        """Return a packaged viewer asset when the unit has no local override."""
        name = VIEWER_ROUTES.get(route)
        if name is None or (self.deck_root / "webdeck" / name).is_file():
            return None
        return files("lecturedeck").joinpath("assets", name)

    def send_packaged(self, asset, include_body: bool) -> None:
        payload = asset.read_bytes()
        content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def send_served_index(self, include_body: bool) -> None:
        local = self.deck_root / "webdeck" / "index.html"
        index = local if local.is_file() else files("lecturedeck").joinpath("assets", "index.html")
        text = index.read_text(encoding="utf-8")
        script = '<script src="/__lecturedeck/adjust.js"></script>'
        payload = text.replace("</body>", f"{script}</body>").encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    @staticmethod
    def serves(route: str) -> bool:
        """Only the unit's webdeck bundle is public; scripts and briefs are not."""
        return route == "/webdeck" or route.startswith("/webdeck/")

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        route = self.normalized_route()
        if route == ADJUST_ROUTE:
            asset = files("lecturedeck").joinpath("assets", "adjust.js")
            self.send_packaged(asset, include_body=True)
            return
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
        if route == "/" or self.needs_slash_redirect():
            self.send_slash_redirect()
            return
        if not self.serves(route):
            self.send_error(HTTPStatus.NOT_FOUND, "Only webdeck/ is served")
            return
        if route in INDEX_ROUTES:
            self.send_served_index(include_body=True)
            return
        packaged = self.packaged_asset(route)
        if packaged is not None:
            self.send_packaged(packaged, include_body=True)
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        route = self.normalized_route()
        if route == ADJUST_ROUTE:
            asset = files("lecturedeck").joinpath("assets", "adjust.js")
            self.send_packaged(asset, include_body=False)
            return
        if self.needs_slash_redirect():
            self.send_slash_redirect()
            return
        if not self.serves(route):
            self.send_error(HTTPStatus.NOT_FOUND, "Only webdeck/ is served")
            return
        if route in INDEX_ROUTES:
            self.send_served_index(include_body=False)
            return
        packaged = self.packaged_asset(route)
        if packaged is not None:
            self.send_packaged(packaged, include_body=False)
            return
        super().do_HEAD()

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND, "Directory listings are disabled")
        return None

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def make_server(root: Path, host: str, port: int, livereload: bool) -> DeckHTTPServer:
    handler = partial(DeckRequestHandler, directory=str(root), livereload=livereload)
    server = DeckHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
