"""Command-line interface for reusable web lecture decks."""

from __future__ import annotations

import argparse
import errno
import json
import os
import socket
import sys
import tomllib
import webbrowser
from pathlib import Path

from .narration import NarrationError, outline, read_deck, skeleton
from .pdf import PDFExportError, export_pdf
from .scaffold import refresh_unit, scaffold_unit
from .server import make_selector_server, make_server
from .validation import deck_entry, release_unit, validate_unit

DEFAULT_PORT = 4173
PORT_SEARCH_ATTEMPTS = 100


def find_repo_root(start: Path) -> Path:
    seen: set[Path] = set()
    for origin in (start.resolve(), Path(__file__).resolve()):
        for candidate in (origin, *origin.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            if (candidate / "Studio" / "work" / "presentations").is_dir():
                return candidate
    raise RuntimeError(
        "Could not find a lecture repository. Run the command inside "
        "the repository or pass --repo PATH."
    )


def selector_folder(repo: Path) -> Path:
    """Resolve an optional repository selector setting without escaping it."""
    config = repo / "lecturedeck.toml"
    if not config.is_file():
        return repo / "Studio" / "work" / "presentations"
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
        section = data.get("selector", {})
        value = section.get("folder") if isinstance(section, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("[selector].folder must be a nonempty relative path")
        relative = Path(value)
        folder = (repo / relative).resolve()
        if relative.is_absolute() or not folder.is_relative_to(repo.resolve()):
            raise ValueError("[selector].folder must stay inside the repository")
        return folder
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Invalid lecturedeck.toml: {error}") from error


def clean_unit(value: str) -> str:
    if not value or value in {".", ".."} or Path(value).name != value:
        raise argparse.ArgumentTypeError("unit must be one presentation-unit name")
    return value


def lan_ipv4_addresses() -> list[str]:
    """Return useful non-loopback IPv4 addresses for startup hints."""
    addresses: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 80))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(
        address
        for address in addresses
        if address != "0.0.0.0" and not address.startswith("127.")
    )


def port_unavailable(exc: OSError) -> bool:
    """Return whether automatic selection should try the next port."""
    return exc.errno in {errno.EACCES, errno.EADDRINUSE, 10013, 10048} or getattr(
        exc, "winerror", None
    ) in {10013, 10048}


def make_available_server(
    root: Path,
    host: str,
    port: int,
    livereload: bool,
    *,
    auto_advance: bool,
    selector: bool = False,
    pacing_records: bool = True,
):
    """Bind the requested port, optionally advancing past occupied ports."""
    attempts = PORT_SEARCH_ATTEMPTS if auto_advance else 1
    last_error: OSError | None = None
    server_factory = make_selector_server if selector else make_server
    for candidate in range(port, min(port + attempts, 65536)):
        try:
            server = server_factory(
                root, host, candidate, livereload, pacing_records=pacing_records
            )
            return server, candidate
        except OSError as exc:
            if not auto_advance or not port_unavailable(exc):
                raise
            last_error = exc
    if last_error is not None:
        raise last_error
    raise OSError(f"no valid port at or above {port}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lecturedeck")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="serve a deck or a deck selector")
    serve.add_argument(
        "unit",
        nargs="?",
        type=clean_unit,
        help="unit to serve; omit to show a deck selector",
    )
    network = serve.add_mutually_exclusive_group()
    network.add_argument("--host", default="127.0.0.1", help="interface to bind")
    network.add_argument(
        "--lan",
        action="store_true",
        help="listen on all IPv4 interfaces for access from the local network",
    )
    serve.add_argument(
        "--port",
        type=int,
        help=(
            f"port to listen on; without this option, start at {DEFAULT_PORT} "
            "and advance past ports already in use"
        ),
    )
    serve.add_argument("--livereload", action="store_true", help="reload when deck files change")
    serve.add_argument(
        "--no-pacing-records",
        action="store_false",
        dest="pacing_records",
        help="do not save scheduled pacing records to <unit>/pacing-records/",
    )
    serve.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="open the deck in the default browser",
    )
    location = serve.add_mutually_exclusive_group()
    location.add_argument("--repo", type=Path, help="repository root; normally auto-detected")
    location.add_argument(
        "--folder",
        type=Path,
        help="folder whose immediate children are presentation units",
    )

    init = subparsers.add_parser("init", help="create a reusable webdeck scaffold")
    init.add_argument("unit", type=clean_unit)
    init.add_argument("--title", required=True, help="presentation title")
    init.add_argument("--repo", type=Path, help="repository root; normally auto-detected")

    refresh = subparsers.add_parser(
        "refresh", help="update scaffold-owned runtime files in a unit's webdeck"
    )
    refresh.add_argument("unit", type=clean_unit)
    refresh.add_argument(
        "--force",
        action="store_true",
        help="overwrite runtime files that carry local modifications",
    )
    refresh.add_argument("--repo", type=Path, help="repository root; normally auto-detected")

    check = subparsers.add_parser("check", help="validate a unit's static webdeck")
    check.add_argument("unit", type=clean_unit)
    check.add_argument("--repo", type=Path, help="repository root; normally auto-detected")

    release = subparsers.add_parser("release", help="copy a checked static bundle")
    release.add_argument("unit", type=clean_unit)
    release.add_argument("--output", required=True, type=Path, help="new output directory")
    release.add_argument("--repo", type=Path, help="repository root; normally auto-detected")

    pdf = subparsers.add_parser("pdf", help="export every slide to a 16:9 PDF page")
    pdf.add_argument("unit", type=clean_unit)
    pdf.add_argument("--output", required=True, type=Path, help="new .pdf output file")
    pdf.add_argument(
        "--theme",
        choices=("light", "dark"),
        default="light",
        help="PDF color theme (default: light)",
    )
    pdf.add_argument("--repo", type=Path, help="repository root; normally auto-detected")

    narration = subparsers.add_parser(
        "narration",
        help="print a Markdown narration skeleton (or JSON outline) of a deck",
    )
    narration.add_argument(
        "unit", nargs="?", type=clean_unit, help="unit to read; or pass --deck PATH"
    )
    deck_source = narration.add_mutually_exclusive_group()
    deck_source.add_argument(
        "--repo", type=Path, help="repository root; normally auto-detected"
    )
    deck_source.add_argument(
        "--deck",
        type=Path,
        help="a deck.json file, a webdeck/ folder, or a unit folder (instead of UNIT)",
    )
    narration.add_argument(
        "--outline", action="store_true", help="print the JSON outline instead"
    )
    narration.add_argument(
        "--output", type=Path, help="new file to write instead of standard output"
    )
    narration.set_defaults(subparser=narration)
    return parser


def write_stdout(text: str) -> None:
    """Write UTF-8 bytes to stdout whatever the console encoding.

    A reader that stops early (``| head``) ends the output quietly: the rest
    goes to the null device, so neither this write nor the flush at
    interpreter exit prints a BrokenPipeError traceback.
    """
    try:
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is None:
            sys.stdout.write(text)
            sys.stdout.flush()
            return
        sys.stdout.flush()
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    except OSError as error:
        if not _reader_gone(error):
            raise
        _silence_stdout()


def _reader_gone(error: OSError) -> bool:
    # Windows reports a pipe closed mid-write as EINVAL as often as EPIPE.
    return isinstance(error, BrokenPipeError) or (
        sys.platform == "win32" and error.errno == errno.EINVAL
    )


def _silence_stdout() -> None:
    try:
        target = sys.stdout.fileno()
    except (OSError, ValueError):
        return  # no real descriptor behind stdout (an in-memory stream)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, target)
    except OSError:
        pass  # at worst Python reports the pipe once more at exit
    finally:
        os.close(devnull)


def narration_label(label: str) -> str:
    """A unit label that cannot end or split its ``<!-- deck: ... -->`` line."""
    if any(part in label for part in ("-->", "--!>", "\n", "\r")):
        raise NarrationError(
            [
                f"unit name {label!r} cannot appear in a narration header "
                "(it contains '-->', '--!>' or a line break)"
            ]
        )
    return label


def narration_deck(path: Path) -> Path:
    """Resolve --deck: a deck file, a webdeck/ folder, or a unit folder."""
    path = path.resolve()
    if path.is_file():
        return path
    if path.is_dir():
        entry = deck_entry(path)
        if entry is not None:
            return entry
        for name in ("deck.json", "slides.js"):
            if (path / name).is_file():
                return path / name
    raise FileNotFoundError(
        f"no deck at {path}: expected deck.json, a webdeck/ folder, or a unit folder"
    )


def narrate(args: argparse.Namespace) -> int:
    if args.deck is not None and args.unit is not None:
        args.subparser.error("narration takes UNIT or --deck PATH, not both")
    if args.deck is None and args.unit is None:
        args.subparser.error("narration needs UNIT or --deck PATH")
    try:
        if args.deck is not None:
            deck = narration_deck(args.deck)
            unit_folder = deck.parent.parent if deck.parent.name == "webdeck" else deck.parent
            label = narration_label(unit_folder.name)
        else:
            label = narration_label(args.unit)
            repo = args.repo.resolve() if args.repo else find_repo_root(Path.cwd())
            unit_folder = repo / "Studio" / "work" / "presentations" / args.unit
            deck = deck_entry(unit_folder)
            if deck is None:
                raise FileNotFoundError(
                    f"web deck not found: {unit_folder / 'webdeck'} has no deck.json "
                    "or slides.js"
                )
        data, digest = read_deck(deck)
    except (RuntimeError, FileNotFoundError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except NarrationError as error:
        for problem in error.errors:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 2
    relative = deck.relative_to(unit_folder).as_posix()
    try:
        if args.outline:
            document = outline(data, unit=label, deck=relative, digest=digest)
            text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        else:
            text = skeleton(data, unit=label, digest=digest)
    except RecursionError:
        print(f"ERROR: {deck.name}: markup nested too deeply", file=sys.stderr)
        return 2
    if args.output is None:
        write_stdout(text)
        return 0
    output = args.output.resolve()
    webdeck = deck.parent.resolve()
    if output == webdeck or webdeck in output.parents:
        print(f"ERROR: refusing to write inside the deck folder: {output}", file=sys.stderr)
        return 2
    if output.exists():
        print(f"ERROR: output already exists: {output}", file=sys.stderr)
        return 2
    try:
        with output.open("xb") as handle:
            handle.write(text.encode("utf-8"))
    except OSError as error:
        print(f"ERROR: cannot write {output} ({error})", file=sys.stderr)
        return 2
    kind = "outline" if args.outline else "skeleton"
    write_stdout(f"Wrote {label} narration {kind} to {output}\n")
    return 0


def serve(args: argparse.Namespace) -> int:
    if args.folder:
        folder = args.folder.resolve()
    else:
        repo = args.repo.resolve() if args.repo else find_repo_root(Path.cwd())
        try:
            folder = (
                selector_folder(repo) if args.unit is None
                else repo / "Studio" / "work" / "presentations"
            )
        except RuntimeError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
    selector = args.unit is None
    root = folder if selector else folder / args.unit
    if selector:
        if not folder.is_dir():
            print(f"ERROR: deck folder does not exist: {folder}", file=sys.stderr)
            return 2
    elif deck_entry(root) is None:
        webdeck = root / "webdeck"
        print(
            f"ERROR: web deck not found: {webdeck} has no deck.json or slides.js",
            file=sys.stderr,
        )
        return 2

    bind_host = "0.0.0.0" if args.lan else args.host
    requested_port = args.port if args.port is not None else DEFAULT_PORT
    try:
        server, selected_port = make_available_server(
            root,
            bind_host,
            requested_port,
            args.livereload,
            auto_advance=args.port is None,
            selector=selector,
            pacing_records=args.pacing_records,
        )
    except OSError as exc:
        print(f"ERROR: cannot listen on {bind_host}:{requested_port} ({exc})", file=sys.stderr)
        if args.port is None:
            last_port = requested_port + PORT_SEARCH_ATTEMPTS - 1
            print(
                f"No free port found in {requested_port}-{last_port}.",
                file=sys.stderr,
            )
        else:
            print(
                "Another server may be running; omit --port to choose automatically.",
                file=sys.stderr,
            )
        return 2
    selected_port = server.server_address[1]
    start_path = "/" if selector else "/webdeck/"
    local_url = f"http://127.0.0.1:{selected_port}{start_path}"
    display_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    url = f"http://{display_host}:{selected_port}{start_path}"
    access = (
        "localhost only"
        if bind_host in {"127.0.0.1", "localhost", "::1"}
        else "LAN-visible, read-only files"
    )
    label = f"deck selector for {folder}" if selector else args.unit
    print(f"Serving {label}  (Ctrl+C to stop)")
    if args.port is None and selected_port != requested_port:
        print(f"  Port {requested_port} is busy; using {selected_port}.")
    print(f"  Local: {local_url if args.lan else url}")
    if args.lan:
        addresses = lan_ipv4_addresses()
        if addresses:
            for address in addresses:
                print(f"  LAN:   http://{address}:{selected_port}{start_path}")
        else:
            print(f"  LAN:   http://<this-computer-ip>:{selected_port}{start_path}")
    print(f"  Access: {access}")
    if args.pacing_records:
        print(
            "  Pacing records: <unit>/pacing-records/ on scheduled dates "
            "(browser on this computer only)"
        )
    else:
        print("  Pacing records: off")
    print(f"  Source: {root}")
    if args.livereload:
        print("  Live reload: on")
    # Redirected stdout is buffered; publish the address before serving forever.
    sys.stdout.flush()
    if args.open_browser:
        webbrowser.open(local_url if args.lan else url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(args)
    if args.command == "narration":
        return narrate(args)
    repo = args.repo.resolve() if args.repo else find_repo_root(Path.cwd())
    unit_root = repo / "Studio" / "work" / "presentations" / args.unit
    if args.command == "init":
        created = scaffold_unit(unit_root, args.title)
        for path in created:
            print(path.relative_to(repo))
        return 0
    if args.command == "refresh":
        try:
            results = refresh_unit(unit_root, force=args.force)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        notes = {
            "current": "already matches this runtime",
            "refreshed": "updated to this runtime",
            "kept": "locally modified; kept (use --force to overwrite)",
            "missing": "not present; installed viewer is used",
        }
        for name, state in results:
            print(f"{name}: {notes[state]}")
        return 0
    if args.command == "check":
        errors = validate_unit(unit_root)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 2
        print(f"OK: {args.unit} webdeck content and installed viewer are valid")
        return 0
    if args.command == "release":
        try:
            output = release_unit(unit_root, args.output)
        except (FileExistsError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"Released {args.unit} to {output}")
        return 0
    if args.command == "pdf":
        try:
            output = export_pdf(unit_root, args.output, theme=args.theme)
        except (FileExistsError, FileNotFoundError, PDFExportError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"Exported {args.unit} to {output}")
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
