"""Strict, cache-free static server with a tiny live-reload endpoint."""

from __future__ import annotations

import json
import mimetypes
import posixpath
import socket
from dataclasses import dataclass
from functools import partial
from hashlib import sha1
from html import escape
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from . import __version__

VIEWER_ROUTES = {
    "/webdeck/lecturedeck.css": "lecturedeck.css",
    "/webdeck/lecturedeck.js": "lecturedeck.js",
    "/webdeck/deck.css": "deck.css",
}
INDEX_ROUTES = {"/webdeck", "/webdeck/index.html"}
ADJUST_ROUTE = "/__lecturedeck/adjust.js"


@dataclass(frozen=True)
class DeckSummary:
    """Public selector metadata for one immediate child unit."""

    name: str
    root: Path
    title: str
    section: str | None = None


def discover_decks(folder: Path) -> list[DeckSummary]:
    """Find immediate child units without reading outside their webdeck trees."""
    folder = folder.resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"deck folder does not exist: {folder}")
    decks: list[DeckSummary] = []
    for candidate in folder.iterdir():
        if not candidate.is_dir():
            continue
        root = candidate.resolve()
        if folder not in root.parents:
            continue
        webdeck = root / "webdeck"
        deck_json = webdeck / "deck.json"
        legacy = webdeck / "slides.js"
        if not deck_json.is_file() and not legacy.is_file():
            continue
        title = candidate.name
        section = None
        if deck_json.is_file():
            try:
                data = json.loads(deck_json.read_text(encoding="utf-8"))
                meta = data.get("meta") if isinstance(data, dict) else None
                if isinstance(meta, dict):
                    if isinstance(meta.get("title"), str) and meta["title"].strip():
                        title = meta["title"].strip()
                    if isinstance(meta.get("section"), str) and meta["section"].strip():
                        section = meta["section"].strip()
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        decks.append(DeckSummary(candidate.name, root, title, section))
    return sorted(decks, key=lambda deck: (deck.title.casefold(), deck.name.casefold()))


def selector_page(decks: list[DeckSummary]) -> bytes:
    """Render the self-contained deck selector."""
    cards = []
    for deck in decks:
        href = f"/decks/{quote(deck.name, safe='')}/webdeck/"
        search = escape(f"{deck.title} {deck.section or ''} {deck.name}", quote=True)
        section = (
            f'<span class="section">{escape(deck.section)}</span>' if deck.section else ""
        )
        cards.append(
            f'<li data-search="{search}">'
            f'<a href="{href}">{section}<strong>{escape(deck.title)}</strong>'
            f'<span class="unit">{escape(deck.name)}</span></a></li>'
        )
    empty = '<p class="empty">No decks found in this folder.</p>' if not cards else ""
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lecture decks</title>
  <style>
    :root {{ color-scheme: light dark; font-family: Aptos, Calibri, system-ui, sans-serif; }}
    body {{ margin: 0; min-height: 100vh; background: #101827; color: #eef3fb; }}
    main {{ width: min(980px, calc(100% - 40px)); margin: 0 auto; padding: 64px 0 80px; }}
    header {{ display: grid; gap: 12px; margin-bottom: 32px; }}
    h1 {{ margin: 0; font-size: clamp(2.2rem, 7vw, 4.5rem); letter-spacing: -.045em; }}
    p {{ margin: 0; color: #aebbd0; font-size: 1.05rem; }}
    input {{ box-sizing: border-box; width: 100%; margin-top: 12px; padding: 14px 16px;
      border: 1px solid #40506b; border-radius: 10px; background: #172338; color: inherit;
      font: inherit; }}
    ul {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px; margin: 0; padding: 0; list-style: none; }}
    a {{ display: grid; gap: 8px; min-height: 120px; padding: 22px; border: 1px solid #33445f;
      border-radius: 14px; background: #172338; color: inherit; text-decoration: none;
      box-shadow: 0 12px 30px rgb(0 0 0 / .16); }}
    a:hover, a:focus-visible {{ border-color: #74b6ff; outline: none;
      transform: translateY(-2px); }}
    strong {{ font-size: 1.35rem; line-height: 1.15; }}
    .section {{ color: #74b6ff; font-size: .78rem; font-weight: 700; letter-spacing: .08em;
      text-transform: uppercase; }}
    .unit {{ align-self: end; color: #8f9eb6; font: .82rem ui-monospace, monospace; }}
    .empty {{ padding: 24px; border: 1px dashed #40506b; border-radius: 12px; }}
    [hidden] {{ display: none; }}
  </style>
</head>
<body>
  <main>
    <header><h1>Lecture decks</h1><p>Select a deck to present.</p>
      <input id="filter" type="search" placeholder="Filter decks" aria-label="Filter decks">
    </header>
    {empty}<ul>{''.join(cards)}</ul>
  </main>
  <script>
    const filter = document.querySelector("#filter");
    filter.addEventListener("input", () => {{
      const query = filter.value.trim().toLocaleLowerCase();
      document.querySelectorAll("li[data-search]").forEach((card) => {{
        card.hidden = !card.dataset.search.toLocaleLowerCase().includes(query);
      }});
    }});
  </script>
</body>
</html>
"""
    return html.encode("utf-8")


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

    def __init__(self, *args, directory: str, livereload: bool, quiet: bool = False, **kwargs):
        self.deck_root = Path(directory).resolve()
        self.livereload = livereload
        self.quiet = quiet
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:
        if not self.quiet:
            super().log_message(format, *args)

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
        self.send_header("Location", f"{getattr(self, 'route_prefix', '')}/webdeck/")
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
        script = '<script src="../__lecturedeck/adjust.js"></script>'
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


class SelectorRequestHandler(DeckRequestHandler):
    """Select and serve immediate child decks from one presentations folder."""

    def __init__(self, *args, decks: list[DeckSummary], **kwargs):
        self.decks = {deck.name: deck for deck in decks}
        super().__init__(*args, **kwargs)

    def select_deck(self) -> bool:
        """Rewrite a selector URL to the chosen unit's existing server route."""
        parsed = urlsplit(self.path)
        route = posixpath.normpath(unquote(parsed.path))
        parts = route.split("/")
        if len(parts) < 3 or parts[1] != "decks" or parts[2] not in self.decks:
            return False
        deck = self.decks[parts[2]]
        self.deck_root = deck.root
        self.directory = str(deck.root)
        self.route_prefix = f"/decks/{quote(deck.name, safe='')}"
        inner = "/" + "/".join(parts[3:])
        if unquote(parsed.path).endswith("/") and not inner.endswith("/"):
            inner += "/"
        self.path = inner + (f"?{parsed.query}" if parsed.query else "")
        return True

    def send_selector(self, include_body: bool) -> None:
        payload = selector_page(list(self.decks.values()))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.normalized_route() == "/":
            self.send_selector(include_body=True)
            return
        if not self.select_deck():
            self.send_error(HTTPStatus.NOT_FOUND, "Deck not found")
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        if self.normalized_route() == "/":
            self.send_selector(include_body=False)
            return
        if not self.select_deck():
            self.send_error(HTTPStatus.NOT_FOUND, "Deck not found")
            return
        super().do_HEAD()


def make_server(
    root: Path, host: str, port: int, livereload: bool, *, quiet: bool = False
) -> DeckHTTPServer:
    handler = partial(
        DeckRequestHandler, directory=str(root), livereload=livereload, quiet=quiet
    )
    server = DeckHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def make_selector_server(
    folder: Path, host: str, port: int, livereload: bool, *, quiet: bool = False
) -> DeckHTTPServer:
    decks = discover_decks(folder)
    handler = partial(
        SelectorRequestHandler,
        directory=str(folder.resolve()),
        livereload=livereload,
        quiet=quiet,
        decks=decks,
    )
    server = DeckHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
