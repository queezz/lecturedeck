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
FAVICON_ROUTE = "/favicon.svg"


@dataclass(frozen=True)
class DeckSummary:
    """Public selector metadata for one immediate child unit."""

    name: str
    root: Path
    title: str
    section: str | None = None
    group: str = "Lectures"
    hero: str | None = None
    selector_title: str | None = None
    selector_favicon: str | None = None


def _selector_group(name: str, title: str, explicit: object) -> str:
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    identity = f"{name} {title}".casefold()
    if "solution" in identity or title.casefold().startswith("homework"):
        return "Homeworks"
    if name.casefold().startswith("extra-") or title.casefold().startswith("extra"):
        return "Extras"
    return "Lectures"


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
        group = "Lectures"
        hero = None
        selector_title = None
        selector_favicon = None
        if deck_json.is_file():
            try:
                data = json.loads(deck_json.read_text(encoding="utf-8"))
                meta = data.get("meta") if isinstance(data, dict) else None
                if isinstance(meta, dict):
                    if isinstance(meta.get("title"), str) and meta["title"].strip():
                        title = meta["title"].strip()
                    if isinstance(meta.get("section"), str) and meta["section"].strip():
                        section = meta["section"].strip()
                    group = _selector_group(candidate.name, title, meta.get("selectorGroup"))
                    if isinstance(meta.get("selectorTitle"), str) and meta["selectorTitle"].strip():
                        selector_title = meta["selectorTitle"].strip()
                    candidate_icon = meta.get("selectorFavicon")
                    if (
                        isinstance(candidate_icon, str)
                        and candidate_icon.startswith("assets/")
                        and "\\" not in candidate_icon
                        and ".." not in candidate_icon.split("/")
                        and (webdeck / candidate_icon).is_file()
                        and webdeck.resolve() in (webdeck / candidate_icon).resolve().parents
                    ):
                        selector_favicon = candidate_icon
                    candidate_hero = meta.get("selectorHero")
                    if (
                        isinstance(candidate_hero, str)
                        and candidate_hero.startswith("assets/")
                        and "\\" not in candidate_hero
                        and ".." not in candidate_hero.split("/")
                        and (webdeck / candidate_hero).is_file()
                    ):
                        hero = candidate_hero
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        decks.append(DeckSummary(
            candidate.name, root, title, section, group, hero,
            selector_title, selector_favicon,
        ))
    return sorted(decks, key=lambda deck: (deck.title.casefold(), deck.name.casefold()))


def selector_page(decks: list[DeckSummary]) -> bytes:
    """Render the self-contained deck selector."""
    identities = {deck.selector_title for deck in decks if deck.selector_title}
    selector_title = next(iter(identities)) if len(identities) == 1 else "Lecture decks"
    selector_icon = FAVICON_ROUTE
    # Course identity is declarative and opt-in. Unbranded decks may share
    # the selector; conflicting named courses retain the generic identity.
    branded = [deck for deck in decks if deck.selector_title == selector_title
               and deck.selector_favicon]
    if len(identities) == 1 and branded:
        icon_deck = sorted(branded, key=lambda deck: deck.name)[0]
        selector_icon = f"/decks/{quote(icon_deck.name, safe='')}/webdeck/" + "/".join(
            quote(part, safe="") for part in icon_deck.selector_favicon.split("/")
        )
    grouped: dict[str, list[str]] = {}
    for deck in decks:
        base = f"/decks/{quote(deck.name, safe='')}/webdeck/"
        search = escape(f"{deck.title} {deck.section or ''} {deck.name}", quote=True)
        hero = ""
        if deck.hero:
            hero_url = base + "/".join(quote(part, safe="") for part in deck.hero.split("/"))
            hero = f'<img class="hero" src="{hero_url}" alt="" loading="lazy">'
        card = (
            f'<li data-search="{search}" data-group="{escape(deck.group, quote=True)}">'
            f'<a href="{base}">{hero}<span class="card-copy">'
            f'<strong>{escape(deck.title)}</strong>'
            f'<span class="unit">{escape(deck.name)}</span></span></a></li>'
        )
        grouped.setdefault(deck.group, []).append(card)
    preferred = {"Lectures": 0, "Homeworks": 1, "Extras": 2}
    group_names = sorted(grouped, key=lambda name: (preferred.get(name, 3), name.casefold()))
    groups = "".join(
        f'<section class="deck-group" data-deck-group="{escape(name, quote=True)}">'
        f'<div class="group-heading"><h2>{escape(name)}</h2>'
        f'<span>{len(grouped[name])}</span></div><ul>{"".join(grouped[name])}</ul></section>'
        for name in group_names
    )
    rail_buttons = "".join(
        f'<button type="button" data-group-filter="{escape(name, quote=True)}">'
        f'<span>{escape(name)}</span><small>{len(grouped[name])}</small></button>'
        for name in group_names
    )
    empty = '<p class="empty">No decks found in this folder.</p>' if not decks else ""
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="{escape(selector_icon, quote=True)}">
  <title>{escape(selector_title)}</title>
  <style>
    :root {{ color-scheme: dark; font-family: Aptos, Calibri, system-ui, sans-serif;
      --bar: 58px; --page-pad: 28px; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; background: #101827; color: #e7edf6; }}
    .topbar {{ position: sticky; z-index: 10; top: 0; height: var(--bar); display: flex;
      align-items: center; gap: 24px; padding: 0 max(24px, calc((100vw - 1180px) / 2));
      border-bottom: 1px solid #26354a; background: rgb(16 24 39 / .96);
      backdrop-filter: blur(14px); }}
    h1 {{ flex: none; margin: 0; font-size: 1rem; font-weight: 650; letter-spacing: .01em; }}
    #filter {{ width: min(460px, 46vw); margin-left: auto; padding: 9px 12px;
      border: 1px solid #34445b; border-radius: 8px; background: #162236; color: inherit;
      font: inherit; outline: none; }}
    #filter:focus {{ border-color: #669fe0; box-shadow: 0 0 0 3px rgb(102 159 224 / .14); }}
    main {{ width: min(1180px, calc(100% - 48px)); margin: 0 auto;
      padding: var(--page-pad) 0 72px; }}
    .layout {{ display: grid; grid-template-columns: 180px minmax(0, 1fr); gap: 28px;
      align-items: stretch; }}
    .rail {{ position: sticky; top: calc(var(--bar) + var(--page-pad)); align-self: start;
      display: grid; gap: 6px; }}
    .rail-label {{ margin: 0 0 6px 10px; color: #8391a6; font-size: .68rem;
      font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
    .rail button {{ display: flex; justify-content: space-between; gap: 12px; width: 100%;
      padding: 10px 11px; border: 1px solid transparent; border-radius: 8px;
      background: transparent; color: #aebbd0; font: inherit; text-align: left; cursor: pointer; }}
    .rail button:hover {{ background: #152135; color: #e7edf6; }}
    .rail button[aria-pressed="true"] {{ border-color: #334760; background: #1a2940;
      color: #f3f7fc; }}
    .rail small {{ color: #718198; font-size: .75rem; }}
    .deck-list {{ min-width: 0; }}
    .deck-group {{ margin: 0 0 36px; }}
    .group-heading {{ display: flex; align-items: baseline; gap: 10px; margin-bottom: 12px;
      padding-bottom: 8px; border-bottom: 1px solid #26354a; }}
    h2 {{ margin: 0; font-size: 1rem; font-weight: 650; }}
    .group-heading span {{ color: #718198; font-size: .78rem; }}
    ul {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px; margin: 0; padding: 0; list-style: none; }}
    li a {{ display: grid; min-height: 108px; overflow: hidden; border: 1px solid #2f4058;
      border-radius: 10px; background: #162236; color: inherit; text-decoration: none;
      transition: border-color 120ms ease, background 120ms ease; }}
    li a:hover, li a:focus-visible {{ border-color: #649bd9; background: #192941; outline: none; }}
    .hero {{ width: 100%; aspect-ratio: 16 / 7; display: block; object-fit: cover;
      border-bottom: 1px solid #2f4058; background: #0d1522; }}
    .card-copy {{ display: grid; gap: 8px; padding: 16px 17px; }}
    strong {{ font-size: 1.03rem; line-height: 1.3; font-weight: 650; }}
    .unit {{ color: #8391a6; font: .73rem ui-monospace, monospace; }}
    .empty {{ padding: 24px; border: 1px dashed #40506b; border-radius: 12px; }}
    [hidden] {{ display: none; }}
    @media (max-width: 760px) {{
      :root {{ --bar: 106px; --page-pad: 18px; }}
      .topbar {{ align-content: center; flex-wrap: wrap; gap: 10px; padding: 12px 20px; }}
      #filter {{ order: 2; width: 100%; }}
      main {{ width: min(100% - 32px, 620px); }}
      .layout {{ grid-template-columns: 1fr; gap: 18px; }}
      .rail {{ z-index: 5; display: flex; overflow-x: auto;
        padding: 8px 0; background: #101827; }}
      .rail-label {{ display: none; }}
      .rail button {{ width: auto; flex: none; }}
      ul {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header class="topbar"><h1>{escape(selector_title)}</h1>
    <input id="filter" type="search" placeholder="Filter decks" aria-label="Filter decks">
  </header>
  <main><div class="layout">
    <nav class="rail" aria-label="Deck groups"><p class="rail-label">Show</p>
      <button type="button" data-group-filter="all" aria-pressed="true">
        <span>All decks</span><small>{len(decks)}</small>
      </button>
      {rail_buttons}
    </nav>
    <div class="deck-list">{empty}{groups}
      <p class="empty no-match" hidden>No matching decks.</p>
    </div>
  </div></main>
  <script>
    const filter = document.querySelector("#filter");
    const groupButtons = [...document.querySelectorAll("[data-group-filter]")];
    let activeGroup = "all";
    function updateDecks() {{
      const query = filter.value.trim().toLocaleLowerCase();
      document.querySelectorAll("li[data-search]").forEach((card) => {{
        const inGroup = activeGroup === "all" || card.dataset.group === activeGroup;
        card.hidden = !inGroup || !card.dataset.search.toLocaleLowerCase().includes(query);
      }});
      document.querySelectorAll("[data-deck-group]").forEach((group) => {{
        group.hidden = !group.querySelector("li[data-search]:not([hidden])");
      }});
      const anyVisible = document.querySelector("li[data-search]:not([hidden])");
      document.querySelector(".no-match").hidden = Boolean(anyVisible)
        || !document.querySelector("li[data-search]");
    }}
    filter.addEventListener("input", updateDecks);
    groupButtons.forEach((button) => button.addEventListener("click", () => {{
      activeGroup = button.dataset.groupFilter;
      groupButtons.forEach((candidate) =>
        candidate.setAttribute("aria-pressed", candidate === button));
      updateDecks();
    }}));
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
        if route == FAVICON_ROUTE:
            asset = files("lecturedeck").joinpath("assets", "favicon.svg")
            self.send_packaged(asset, include_body=True)
            return
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
        if route == FAVICON_ROUTE:
            asset = files("lecturedeck").joinpath("assets", "favicon.svg")
            self.send_packaged(asset, include_body=False)
            return
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
        if self.normalized_route() == FAVICON_ROUTE:
            super().do_GET()
            return
        if not self.select_deck():
            self.send_error(HTTPStatus.NOT_FOUND, "Deck not found")
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        if self.normalized_route() == "/":
            self.send_selector(include_body=False)
            return
        if self.normalized_route() == FAVICON_ROUTE:
            super().do_HEAD()
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
