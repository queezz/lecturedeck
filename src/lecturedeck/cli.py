"""Command-line interface for reusable web lecture decks."""

from __future__ import annotations

import argparse
import socket
import sys
import webbrowser
from pathlib import Path

from .scaffold import refresh_unit, scaffold_unit
from .server import make_server
from .validation import release_unit, validate_unit


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lecturedeck")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="serve a live presentation unit")
    serve.add_argument("unit", type=clean_unit)
    network = serve.add_mutually_exclusive_group()
    network.add_argument("--host", default="127.0.0.1", help="interface to bind")
    network.add_argument(
        "--lan",
        action="store_true",
        help="listen on all IPv4 interfaces for access from the local network",
    )
    serve.add_argument("--port", type=int, default=4173, help="port to listen on")
    serve.add_argument("--livereload", action="store_true", help="reload when deck files change")
    serve.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="open the deck in the default browser",
    )
    serve.add_argument("--repo", type=Path, help="repository root; normally auto-detected")

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
    return parser


def serve(args: argparse.Namespace) -> int:
    repo = args.repo.resolve() if args.repo else find_repo_root(Path.cwd())
    unit_root = repo / "Studio" / "work" / "presentations" / args.unit
    index = unit_root / "webdeck" / "index.html"
    if not index.is_file():
        print(f"ERROR: web deck not found: {index}", file=sys.stderr)
        return 2

    bind_host = "0.0.0.0" if args.lan else args.host
    try:
        server = make_server(unit_root, bind_host, args.port, args.livereload)
    except OSError as exc:
        print(f"ERROR: cannot listen on {bind_host}:{args.port} ({exc})", file=sys.stderr)
        print("Another server may be running; pick a different --port.", file=sys.stderr)
        return 2
    local_url = f"http://127.0.0.1:{args.port}/webdeck/"
    display_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    url = f"http://{display_host}:{args.port}/webdeck/"
    access = (
        "localhost only"
        if bind_host in {"127.0.0.1", "localhost", "::1"}
        else "LAN-visible, read-only files"
    )
    print(f"Serving {args.unit}  (Ctrl+C to stop)")
    print(f"  Local: {local_url if args.lan else url}")
    if args.lan:
        addresses = lan_ipv4_addresses()
        if addresses:
            for address in addresses:
                print(f"  LAN:   http://{address}:{args.port}/webdeck/")
        else:
            print(f"  LAN:   http://<this-computer-ip>:{args.port}/webdeck/")
    print(f"  Access: {access}")
    print(f"  Source: {unit_root}")
    if args.livereload:
        print("  Live reload: on")
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
            "missing": "not present; unit retains its own runtime files",
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
        print(f"OK: {args.unit} webdeck is self-contained")
        return 0
    if args.command == "release":
        try:
            output = release_unit(unit_root, args.output)
        except (FileExistsError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"Released {args.unit} to {output}")
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
