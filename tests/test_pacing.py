"""Server side of pacing records: gates, schema, writer, and HTTP routes."""

import http.client
import json
import os
import socket
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from lecturedeck import __version__, pacing
from lecturedeck.pacing import PacingRefusal, StaleRecord
from lecturedeck.scaffold import scaffold_unit
from lecturedeck.server import content_version, make_selector_server, make_server

DAY = "2026-01-01"
SCHEDULE = {"start": "09:00", "end": "09:02", "timeZone": "UTC", "dates": [DAY]}
NOW = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
SEGMENT = "3fa9c1d27b0e"
FILE_NAME = f"{DAY}_0859_unit_{SEGMENT}.json"
TOP_ORDER = [
    "schema", "kind", "segment", "rev", "unit", "path", "deck", "viewer", "date", "opened",
    "timeZone", "slot", "window", "slides", "visits", "pauses", "fullscreenMs",
]


def segment_record(**overrides) -> dict:
    """A consistent live segment: 10 s before 09:00, the 2-min slot, 20 s after."""
    record = {
        "schema": 2,
        "kind": "lecturedeck-pacing-segment",
        "segment": SEGMENT,
        "rev": 5,
        "unit": "unit",
        "path": "/webdeck/",
        "deck": "Pacing deck",
        "viewer": "0.24.0",
        "date": DAY,
        "opened": "0859",
        "timeZone": "UTC",
        "slot": {
            "start": "09:00",
            "end": "09:02",
            "startAt": "2026-01-01T09:00:00.000Z",
            "endAt": "2026-01-01T09:02:00.000Z",
        },
        "window": {
            "before": 30,
            "after": 60,
            "from": "2026-01-01T08:30:00.000Z",
            "to": "2026-01-01T10:02:00.000Z",
        },
        "slides": {
            "opening": {"number": 1, "label": "1", "title": "Opening", "section": "Opening"},
            "second": {"number": 2, "label": "2", "title": "Second", "section": "Part one"},
            "backup-one": {
                "number": 3, "label": "B1", "title": "Backup", "section": "Backup",
                "backup": True,
            },
        },
        "visits": [
            {"slideId": "opening", "startedAt": "2026-01-01T08:59:50.000Z",
             "durationMs": 10000, "phase": "before"},
            {"slideId": "opening", "startedAt": "2026-01-01T09:00:00.000Z",
             "durationMs": 1000, "phase": "slot"},
            {"slideId": "second", "startedAt": "2026-01-01T09:00:01.000Z",
             "durationMs": 119000, "phase": "slot"},
            {"slideId": "second", "startedAt": "2026-01-01T09:02:00.000Z",
             "durationMs": 20000, "phase": "after"},
        ],
        "pauses": [{"startedAt": "2026-01-01T09:02:20.000Z", "durationMs": 17000,
                    "why": "overview"}],
        "fullscreenMs": 120000,
    }
    record.update(overrides)
    return record


def migrated_record() -> dict:
    """A schema-1 browser record converted by the client (no window margins)."""
    record = segment_record()
    record["window"] = {
        "before": 0, "after": 0,
        "from": record["slot"]["startAt"], "to": record["slot"]["endAt"],
    }
    record["visits"] = [
        {"slideId": "second", "startedAt": "2026-01-01T09:00:30.000Z",
         "durationMs": 60000, "phase": "slot"},
        # Two-tab v1 records may be out of order; migrated visits skip that check.
        {"slideId": "opening", "startedAt": "2026-01-01T09:00:00.000Z",
         "durationMs": 20000, "phase": "slot"},
    ]
    record["pauses"] = []
    record["fullscreenMs"] = None
    record["migratedFrom"] = 1
    return record


def encode(record) -> bytes:
    return json.dumps(record).encode("utf-8")


def parse(record, *, body: bytes | None = None, now: datetime = NOW, **kwargs) -> dict:
    options = {"dates": frozenset({DAY}), "unit": "unit", "route_path": "/webdeck/"}
    options.update(kwargs)
    return pacing.parse_record(encode(record) if body is None else body, now=now, **options)


def make_unit(parent: Path, name: str = "unit", schedule: dict | None = SCHEDULE) -> Path:
    unit = parent / name
    unit.mkdir()
    scaffold_unit(unit, "Pacing deck")
    if schedule is not None:
        (unit / "webdeck" / "presentation-time.json").write_text(
            json.dumps(schedule), encoding="utf-8"
        )
    return unit


def webdeck_listing(unit: Path) -> list[str]:
    webdeck = unit / "webdeck"
    return sorted(path.relative_to(webdeck).as_posix() for path in webdeck.rglob("*"))


@contextmanager
def serving(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def raw_request(port: int, head: str, body: bytes = b"", timeout: float = 5) -> tuple[int, bytes]:
    """Send exactly these bytes; the server must answer without the rest of the body."""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        sock.sendall(head.replace("\n", "\r\n").encode("latin-1") + b"\r\n" + body)
        chunks = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)
    raw = b"".join(chunks)
    status_line, _, rest = raw.partition(b"\r\n")
    _, _, payload = rest.partition(b"\r\n\r\n")
    return int(status_line.split(b" ")[1]), payload


def pacing_head(port: int, *, length: int = 100, path: str = "/__lecturedeck/pacing",
                omit: tuple = (), **extra) -> str:
    headers = {
        "Host": f"127.0.0.1:{port}",
        "Origin": f"http://127.0.0.1:{port}",
        "Content-Type": "application/json",
        "X-Lecturedeck-Pacing": "2",
        "Content-Length": str(length),
    }
    headers.update({key.replace("_", "-"): value for key, value in extra.items()})
    lines = [f"POST {path} HTTP/1.1"]
    lines += [f"{key}: {value}" for key, value in headers.items() if key not in omit]
    return "\n".join(lines) + "\n"


class GateTest(unittest.TestCase):
    def test_same_machine_table(self):
        allowed = [
            ("127.0.0.1", "127.0.0.1"),
            ("::1", "::1"),
            ("::ffff:127.0.0.1", "::ffff:127.0.0.1"),
            ("::ffff:127.0.0.1", "127.0.0.1"),
            ("192.168.1.5", "192.168.1.5"),
            ("::ffff:192.168.1.5", "192.168.1.5"),
        ]
        refused = [
            ("192.168.1.20", "192.168.1.5"),
            ("::ffff:192.168.1.20", "::ffff:192.168.1.5"),
            ("10.0.0.2", "127.0.0.1"),
            ("not-an-address", "127.0.0.1"),
        ]
        for peer, local in allowed:
            with self.subTest(peer=peer, local=local):
                self.assertTrue(pacing.same_machine(peer, local))
        for peer, local in refused:
            with self.subTest(peer=peer, local=local):
                self.assertFalse(pacing.same_machine(peer, local))

    def test_host_allowed_table(self):
        port = 48123
        local = "192.168.1.5"
        for host in (f"localhost:{port}", f"LocalHost:{port}", f"127.0.0.1:{port}",
                     f"[::1]:{port}", f"{local}:{port}"):
            with self.subTest(host=host):
                self.assertTrue(pacing.host_allowed(host, local, port))
        for host in (f"mac.local:{port}", f"evil.example:{port}", f"127.0.0.1:{port + 1}",
                     None, "", f"192.168.1.20:{port}", f"[127.0.0.1]:{port}",
                     f"localhost.:{port}", f"127.0.0.1:{port}/x", "127.0.0.1"):
            with self.subTest(host=host):
                self.assertFalse(pacing.host_allowed(host, local, port))
        self.assertTrue(pacing.host_allowed("localhost", "127.0.0.1", 80))

    def headers(self, port, **changes):
        headers = {
            "Host": f"127.0.0.1:{port}",
            "Origin": f"http://127.0.0.1:{port}",
            "Sec-Fetch-Site": "same-origin",
            pacing.PACING_HEADER: "2",
        }
        for key, value in changes.items():
            key = key.replace("_", "-")
            if value is None:
                headers.pop(key, None)
            else:
                headers[key] = value
        return headers

    def test_page_and_write_problem_table(self):
        port = 48123
        local = "127.0.0.1"
        for name in ("Forwarded", "X-Forwarded-For", "X-Real-IP", "Via"):
            with self.subTest(proxy=name):
                headers = self.headers(port, **{name: "for=192.0.2.1"})
                self.assertEqual("proxied", pacing.page_problem(headers, local, local, port))
        self.assertEqual(
            "not-same-machine",
            pacing.page_problem(self.headers(port), "192.168.1.20", "192.168.1.5", port),
        )
        self.assertEqual(
            "host",
            pacing.page_problem(self.headers(port, Host=f"mac.local:{port}"), local, local, port),
        )
        self.assertIsNone(pacing.page_problem(self.headers(port), local, local, port))

        origin_cases = [
            self.headers(port, Origin=None),
            self.headers(port, Origin="null"),
            self.headers(port, Origin="http://evil.example"),
            self.headers(port, Host=f"localhost:{port}"),
            self.headers(port, Origin=f"https://127.0.0.1:{port}"),
        ]
        for headers in origin_cases:
            with self.subTest(origin=headers.get("Origin"), host=headers["Host"]):
                self.assertEqual("origin", pacing.write_problem(headers))
        for site in ("cross-site", "same-site", "none"):
            with self.subTest(site=site):
                headers = self.headers(port, Sec_Fetch_Site=site)
                self.assertEqual("fetch-site", pacing.write_problem(headers))
        for value in (None, "1", "PROBE", ""):
            with self.subTest(header=value):
                headers = self.headers(port, X_Lecturedeck_Pacing=value)
                self.assertEqual("header", pacing.write_problem(headers))
        self.assertIsNone(pacing.write_problem(self.headers(port)))
        self.assertIsNone(pacing.write_problem(self.headers(port, Sec_Fetch_Site=None)))
        self.assertIsNone(pacing.write_problem(self.headers(port, X_Lecturedeck_Pacing="probe")))
        upper = self.headers(port, Host=f"LOCALHOST:{port}", Origin=f"http://localhost:{port}")
        self.assertIsNone(pacing.write_problem(upper))

    def test_scheduled_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            webdeck = Path(directory)
            target = webdeck / "presentation-time.json"
            self.assertIsNone(pacing.scheduled_dates(webdeck))
            target.write_text("{not json", encoding="utf-8")
            self.assertIsNone(pacing.scheduled_dates(webdeck))
            target.write_text(json.dumps({"start": "09:00", "end": "10:00"}), encoding="utf-8")
            self.assertIsNone(pacing.scheduled_dates(webdeck))
            target.write_text(json.dumps({"dates": "2026-01-01"}), encoding="utf-8")
            self.assertIsNone(pacing.scheduled_dates(webdeck))
            target.write_text(json.dumps({"dates": [
                "2026-01-01", "2026-02-30", "2026-1-2", 20260103, None, "2026-01-04T00:00",
                "２０２６-01-05", "2026-01-06",
            ]}), encoding="utf-8")
            self.assertEqual(
                frozenset({"2026-01-01", "2026-01-06"}), pacing.scheduled_dates(webdeck)
            )

    def test_unit_token(self):
        self.assertEqual("unit-one", pacing.unit_token("unit one"))
        self.assertEqual("unit", pacing.unit_token("é/.."))
        self.assertEqual("lecture-02_intro.v2", pacing.unit_token("lecture-02_intro.v2"))
        self.assertEqual("a-b", pacing.unit_token("..a\\b.."))
        self.assertEqual(60, len(pacing.unit_token("x" * 200)))
        self.assertRegex(pacing.machine_label(), r"^[A-Za-z0-9.-]{1,64}$")


class ParseRecordTest(unittest.TestCase):
    def assertRefused(self, status, detail, record=None, **kwargs):  # noqa: N802
        with self.assertRaises(PacingRefusal) as caught:
            parse(record, **kwargs)
        self.assertEqual(status, caught.exception.status)
        self.assertEqual(detail, caught.exception.detail)
        return caught.exception

    def test_live_segment_is_rebuilt_in_fixed_order(self):
        record = segment_record()
        result = parse(record)
        self.assertEqual(TOP_ORDER, list(result))
        self.assertEqual(record, result)
        self.assertEqual(["start", "end", "startAt", "endAt"], list(result["slot"]))
        self.assertEqual(["before", "after", "from", "to"], list(result["window"]))
        self.assertEqual(
            ["number", "label", "title", "section", "backup"],
            list(result["slides"]["backup-one"]),
        )
        self.assertEqual(
            ["slideId", "startedAt", "durationMs", "phase"], list(result["visits"][0])
        )
        self.assertEqual(["startedAt", "durationMs", "why"], list(result["pauses"][0]))
        # Key order in the request does not matter; the rebuilt order is fixed.
        shuffled = dict(reversed(list(record.items())))
        self.assertEqual(TOP_ORDER, list(parse(shuffled)))
        self.assertEqual("/webdeck/", parse(segment_record(path="/webdeck/index.html"))["path"])

    def test_migrated_segment_is_accepted(self):
        result = parse(migrated_record())
        order = TOP_ORDER[:13] + ["migratedFrom"] + TOP_ORDER[13:]
        self.assertEqual(order, list(result))
        self.assertEqual(1, result["migratedFrom"])
        self.assertIsNone(result["fullscreenMs"])

    def test_selector_path_and_unit(self):
        record = segment_record(unit="unit one", path="/decks/unit%20one/webdeck/")
        result = parse(record, unit="unit one", route_path="/decks/unit%20one/webdeck/")
        self.assertEqual("/decks/unit%20one/webdeck/", result["path"])
        self.assertRefused(422, None, segment_record(unit="unit one", path="/webdeck/"),
                           unit="unit one", route_path="/decks/unit%20one/webdeck/")

    def mutated(self, change):
        record = segment_record()
        change(record)
        return record

    def test_rejections(self):
        def setter(*path, value):
            def change(record):
                target = record
                for part in path[:-1]:
                    target = target[part]
                target[path[-1]] = value
            return change

        long_visits = [
            {"slideId": "opening", "startedAt": "2026-01-01T09:00:00.000Z",
             "durationMs": 0, "phase": "slot"}
        ] * 5001
        cases = [
            ("unknown top key", setter("extra", value=1), 400, "record"),
            ("unknown visit key", setter("visits", 0, "note", value="x"), 400, "visits[0]"),
            ("missing slide key", lambda r: r["slides"]["opening"].pop("section"),
             400, "slides[0]"),
            ("schema 1", setter("schema", value=1), 400, "schema"),
            ("schema true", setter("schema", value=True), 400, "schema"),
            ("kind", setter("kind", value="lecturedeck-pacing-export"), 400, "kind"),
            ("segment dots", setter("segment", value="../x"), 400, "segment"),
            ("segment upper", setter("segment", value="ABCDEF123456"), 400, "segment"),
            ("segment short", setter("segment", value="abcdef12345"), 400, "segment"),
            ("segment newline", setter("segment", value=SEGMENT + "\n"), 400, "segment"),
            ("rev 0", setter("rev", value=0), 400, "rev"),
            ("rev -1", setter("rev", value=-1), 400, "rev"),
            ("rev float", setter("rev", value=1.5), 400, "rev"),
            ("rev bool", setter("rev", value=True), 400, "rev"),
            ("rev huge", setter("rev", value=2**31), 400, "rev"),
            ("date", setter("date", value="2026-02-30"), 400, "date"),
            ("unscheduled", setter("date", value="2026-01-02"), 422, None),
            ("other unit", setter("unit", value="other"), 422, None),
            ("null unit", setter("unit", value=None), 400, "unit"),
            ("other path", setter("path", value="/decks/other/webdeck/"), 422, None),
            ("opened", setter("opened", value="2460"), 400, "opened"),
            ("time zone", setter("timeZone", value="Asia/Tokyo; x"), 400, "timeZone"),
            ("slot clock", setter("slot", "start", value="9:00"), 400, "slot.start"),
            ("window minutes", setter("window", "before", value=241), 400, "window.before"),
            ("label", setter("slides", "opening", "label", value="X4"), 400, "slides[0].label"),
            ("number", setter("slides", "opening", "number", value=0), 400, "slides[0].number"),
            ("backup", setter("slides", "opening", "backup", value="yes"),
             400, "slides[0].backup"),
            ("control title", setter("slides", "opening", "title", value="a\nb"),
             400, "slides[0].title"),
            ("delete title", setter("slides", "opening", "title", value="a\x7fb"),
             400, "slides[0].title"),
            ("surrogate title", setter("slides", "opening", "title", value="\ud800"),
             400, "slides[0].title"),
            ("long title", setter("slides", "opening", "title", value="x" * 501),
             400, "slides[0].title"),
            ("long deck", setter("deck", value="x" * 301), 400, "deck"),
            ("5001 visits", setter("visits", value=long_visits), 400, "visits"),
            ("unknown slide", setter("visits", 0, "slideId", value="missing"),
             400, "visits[0].slideId"),
            ("unhashable phase", setter("visits", 0, "phase", value=[]),
             400, "visits[0].phase"),
            ("overlap", setter("visits", 1, "durationMs", value=2000),
             400, "visits[2].startedAt"),
            ("slot visit before slot", setter("visits", 0, "phase", value="slot"),
             400, "visits[0].phase"),
            ("negative duration", setter("visits", 0, "durationMs", value=-1),
             400, "visits[0].durationMs"),
            ("huge duration", setter("visits", 0, "durationMs", value=10**9),
             400, "visits[0].durationMs"),
            ("15 h before the date", setter("window", "from", value="2025-12-31T09:00:00.000Z"),
             400, "window.from"),
            ("instant format", setter("visits", 0, "startedAt", value="2026-01-01T08:59:50Z"),
             400, "visits[0].startedAt"),
            ("impossible instant",
             setter("visits", 0, "startedAt", value="2026-01-01T25:00:00.000Z"),
             400, "visits[0].startedAt"),
            ("window after slot", setter("window", "from", value="2026-01-01T09:00:01.000Z"),
             400, "window"),
            ("window wider than minutes", setter("window", "before", value=10), 400, "window"),
            ("pause reason", setter("pauses", 0, "why", value="coffee"), 400, "pauses[0].why"),
            ("pause outside window",
             setter("pauses", 0, "startedAt", value="2026-01-01T07:00:00.000Z"),
             400, "pauses[0].startedAt"),
            ("fullscreen null", setter("fullscreenMs", value=None), 400, "fullscreenMs"),
            ("fullscreen too long", setter("fullscreenMs", value=150001), 400, "fullscreenMs"),
            ("migratedFrom 2", setter("migratedFrom", value=2), 400, "migratedFrom"),
        ]
        for name, change, status, detail in cases:
            with self.subTest(name):
                self.assertRefused(status, detail, self.mutated(change))

    def test_422_codes(self):
        for change, code in (
            ({"date": "2026-01-02"}, "not-scheduled"),
            ({"unit": "other"}, "wrong-unit"),
            ({"path": "/decks/other/webdeck/"}, "wrong-path"),
        ):
            with self.subTest(code):
                refusal = self.assertRefused(422, None, segment_record(**change))
                self.assertEqual({"error": code}, refusal.payload())

    def test_instants_may_not_be_in_the_future(self):
        record = segment_record()
        now = datetime(2026, 1, 1, 7, 59, 50, tzinfo=timezone.utc)  # 1 h before visits[0]
        self.assertRefused(400, "visits[0].startedAt", record, now=now)
        # The schedule itself may lie ahead while class is still running.
        live = segment_record(visits=segment_record()["visits"][:1], pauses=[],
                              fullscreenMs=0)
        parse(live, now=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc))

    def test_malformed_bodies(self):
        for name, body in (
            ("nan", b'{"schema": NaN}'),
            ("infinity", b'{"schema": Infinity}'),
            ("minus infinity", b'{"schema": -Infinity}'),
            ("not json", b"{schema"),
            ("latin-1", '{"deck": "\u00e9"}'.encode("latin-1")),
            ("duplicate key", b'{"schema": 2, "schema": 2}'),
            ("deep nesting", b"[" * 100_000 + b"]" * 100_000),
        ):
            with self.subTest(name):
                self.assertRefused(400, "json", body=body)
        for body in (b"[]", b"null", b'"record"', b"2"):
            with self.subTest(body=body):
                self.assertRefused(400, "record", body=body)


class StoreRecordTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.unit = make_unit(Path(self.directory.name))
        self.records = self.unit / "pacing-records"

    def store(self, record=None):
        canonical = parse(record or segment_record())
        return pacing.store_record(
            self.unit, "unit", canonical, host="test-host", version=__version__, now=NOW
        )

    def leftovers(self):
        return sorted(path.name for path in self.records.glob(".~*"))

    def test_writes_named_file_with_saved_fields(self):
        result = self.store()
        self.assertEqual(
            {"ok": True, "rev": 5, "file": f"pacing-records/{FILE_NAME}",
             "savedAt": "2026-01-01T10:30:00.000Z"},
            result,
        )
        written = json.loads((self.records / FILE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(TOP_ORDER + ["savedAt", "savedBy"], list(written))
        self.assertEqual("2026-01-01T10:30:00.000Z", written["savedAt"])
        self.assertEqual({"host": "test-host", "lecturedeck": __version__}, written["savedBy"])
        self.assertEqual(segment_record(), {
            key: value for key, value in written.items() if key not in {"savedAt", "savedBy"}
        })
        self.assertEqual([], self.leftovers())
        self.assertEqual([FILE_NAME], sorted(path.name for path in self.records.iterdir()))

    def test_revisions_only_move_forward(self):
        self.store(segment_record(rev=7))
        target = self.records / FILE_NAME
        before = target.read_bytes()
        for rev in (7, 6):
            with self.subTest(rev=rev), self.assertRaises(StaleRecord) as caught:
                self.store(segment_record(rev=rev))
            self.assertEqual(409, caught.exception.status)
            self.assertEqual({"error": "stale", "rev": 7}, caught.exception.payload())
            self.assertEqual(before, target.read_bytes())
        self.assertEqual(8, self.store(segment_record(rev=8))["rev"])
        self.assertEqual(8, json.loads(target.read_text(encoding="utf-8"))["rev"])
        self.assertEqual([], self.leftovers())

    def test_unreadable_existing_file_is_left_as_evidence(self):
        self.records.mkdir()
        target = self.records / FILE_NAME
        for garbage in (b"\x00garbage", b'{"schema": 1, "rev": 3}', b'{"schema": 2}',
                        b'{"schema": 2, "rev": "9"}', b"[]"):
            with self.subTest(garbage=garbage):
                target.write_bytes(garbage)
                with self.assertRaises(PacingRefusal) as caught:
                    self.store(segment_record(rev=50))
                self.assertEqual(
                    (409, "unreadable-existing"),
                    (caught.exception.status, caught.exception.code),
                )
                self.assertEqual(garbage, target.read_bytes())
        self.assertEqual([], self.leftovers())

    def test_renamed_segment_is_refused(self):
        self.store()
        with self.assertRaises(PacingRefusal) as caught:
            self.store(segment_record(rev=6, opened="0900"))
        self.assertEqual(
            {"error": "invalid", "detail": "segment-renamed"}, caught.exception.payload()
        )
        self.assertEqual(400, caught.exception.status)
        self.assertEqual([FILE_NAME], sorted(path.name for path in self.records.iterdir()))

    def test_segments_per_date_are_capped(self):
        self.records.mkdir()
        for index in range(pacing.MAX_SEGMENTS_PER_DATE):
            (self.records / f"{DAY}_0859_unit_{index:012x}.json").write_text("{}")
        (self.records / f"2026-01-02_0859_unit_{SEGMENT}.json").write_text("{}")
        with self.assertRaises(PacingRefusal) as caught:
            self.store()
        self.assertEqual((429, "too-many-segments"),
                         (caught.exception.status, caught.exception.code))
        self.assertFalse((self.records / FILE_NAME).exists())
        # An existing segment still saves its next revision under the cap.
        existing = self.records / f"{DAY}_0859_unit_{0:012x}.json"
        existing.write_text(json.dumps({"schema": 2, "rev": 1}), encoding="utf-8")
        self.store(segment_record(segment=f"{0:012x}", rev=2))
        self.assertEqual(2, json.loads(existing.read_text(encoding="utf-8"))["rev"])

    def test_records_folder_must_be_a_real_folder(self):
        self.records.write_text("not a folder", encoding="utf-8")
        with self.assertRaises(PacingRefusal) as caught:
            self.store()
        self.assertEqual((503, "not-writable"), (caught.exception.status, caught.exception.code))
        self.assertEqual("not a folder", self.records.read_text(encoding="utf-8"))
        with self.assertRaises(PacingRefusal):
            pacing.probe_unit(self.unit)

    def test_symlinked_records_folder_is_refused(self):
        outside = Path(self.directory.name) / "outside"
        outside.mkdir()
        try:
            os.symlink(outside, self.records, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaises(PacingRefusal) as caught:
            self.store()
        self.assertEqual((503, "not-writable"), (caught.exception.status, caught.exception.code))
        self.assertEqual([], list(outside.iterdir()))
        with self.assertRaises(PacingRefusal):
            pacing.probe_unit(self.unit)

    @unittest.skipUnless(os.name == "nt", "Windows junctions")
    def test_junctioned_records_folder_is_refused(self):
        import _winapi

        outside = Path(self.directory.name) / "outside"
        outside.mkdir()
        _winapi.CreateJunction(str(outside), str(self.records))
        with self.assertRaises(PacingRefusal) as caught:
            self.store()
        self.assertEqual((503, "not-writable"), (caught.exception.status, caught.exception.code))
        self.assertEqual([], list(outside.iterdir()))
        with self.assertRaises(PacingRefusal):
            pacing.probe_unit(self.unit)
        os.rmdir(self.records)  # removes the junction, not its target

    def test_unit_names_become_safe_tokens(self):
        for unit, token in (("unit one", "unit-one"), ("é/..", "unit")):
            with self.subTest(unit=unit):
                record = parse(segment_record(unit=unit), unit=unit)
                result = pacing.store_record(
                    self.unit, unit, record, host="h", version=__version__, now=NOW
                )
                name = f"{DAY}_0859_{token}_{SEGMENT}.json"
                self.assertEqual(f"pacing-records/{name}", result["file"])
                self.assertTrue((self.records / name).is_file())
                (self.records / name).unlink()

    def test_replace_retries_a_briefly_locked_target(self):
        real_replace = os.replace
        calls = []

        def flaky(source, target):
            calls.append(target)
            if len(calls) <= 2:
                raise PermissionError("held by another process")
            return real_replace(source, target)

        with (
            patch("lecturedeck.pacing.os.replace", side_effect=flaky),
            patch("lecturedeck.pacing.time.sleep") as sleep,
        ):
            result = self.store()
        self.assertTrue(result["ok"])
        self.assertEqual(3, len(calls))
        self.assertEqual(2, sleep.call_count)
        self.assertTrue((self.records / FILE_NAME).is_file())
        self.assertEqual([], self.leftovers())

    def test_replace_that_never_succeeds_gives_503_and_no_temp_file(self):
        self.store(segment_record(rev=1))
        before = (self.records / FILE_NAME).read_bytes()
        with (
            patch("lecturedeck.pacing.os.replace", side_effect=PermissionError("held")) as fake,
            patch("lecturedeck.pacing.time.sleep"),
        ):
            with self.assertRaises(PacingRefusal) as caught:
                self.store(segment_record(rev=2))
        self.assertEqual((503, "write-failed"), (caught.exception.status, caught.exception.code))
        self.assertEqual(pacing.REPLACE_RETRIES + 1, fake.call_count)
        self.assertEqual(before, (self.records / FILE_NAME).read_bytes())
        self.assertEqual([], self.leftovers())

    def test_probe_writes_nothing(self):
        pacing.probe_unit(self.unit)
        self.assertFalse(self.records.exists())


class HTTPHelpers:
    """Requests whose bodies the server reads; pre-read refusals use raw_request."""

    root: Path

    def post(self, port, record=None, *, body=None, path="/__lecturedeck/pacing", **changes):
        headers = {
            "Host": f"127.0.0.1:{port}",
            "Origin": f"http://127.0.0.1:{port}",
            "Content-Type": "application/json",
            "X-Lecturedeck-Pacing": "2",
        }
        headers.update({key.replace("_", "-"): value for key, value in changes.items()})
        payload = body if body is not None else encode(record or segment_record())
        headers["Content-Length"] = str(len(payload))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request("POST", path, body=payload, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            self.assertNotIn(str(self.root).encode(), raw)
            self.assertNotIn(self.root.as_posix().encode(), raw)
            self.assertEqual("no-store", response.getheader("Cache-Control"))
            self.assertEqual("nosniff", response.getheader("X-Content-Type-Options"))
            return response.status, json.loads(raw)
        finally:
            connection.close()

    def get(self, port, path, method="GET", **headers):
        headers = {key.replace("_", "-"): value for key, value in headers.items()}
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            return response.status, response.read(), response
        finally:
            connection.close()


class PacingHTTPTest(HTTPHelpers, unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.unit = make_unit(self.root)
        self.records = self.unit / "pacing-records"

    def serve(self, unit=None, **kwargs):
        server = make_server(unit or self.unit, "127.0.0.1", 0, livereload=False, quiet=True,
                             **kwargs)
        return serving(server)

    def test_valid_post_writes_beside_webdeck_only(self):
        webdeck = self.unit / "webdeck"
        version_before = content_version(webdeck)
        listing_before = webdeck_listing(self.unit)
        with self.serve() as port:
            status, reply = self.post(port)
        self.assertEqual(200, status, reply)
        self.assertEqual({"ok", "rev", "file", "savedAt"}, set(reply))
        self.assertEqual(f"pacing-records/{FILE_NAME}", reply["file"])
        self.assertEqual(5, reply["rev"])
        self.assertRegex(reply["savedAt"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
        written = json.loads((self.records / FILE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(__version__, written["savedBy"]["lecturedeck"])
        self.assertEqual(pacing.machine_label(), written["savedBy"]["host"])
        self.assertEqual(version_before, content_version(webdeck))
        self.assertEqual(listing_before, webdeck_listing(self.unit))

    def test_probe_is_ready_and_creates_nothing(self):
        with self.serve() as port:
            status, reply = self.post(port, body=b"", X_Lecturedeck_Pacing="probe")
        self.assertEqual(200, status)
        self.assertEqual({"ok": True, "ready": True, "folder": "pacing-records/"}, reply)
        self.assertFalse(self.records.exists())

    def test_each_connection_serves_one_request(self):
        # The handler speaks HTTP/1.0: even a keep-alive request gets its
        # answer and then the end of the connection, so no unread body or
        # idle connection outlives a pacing POST.
        with self.serve() as port:
            head = pacing_head(port, length=0, X_Lecturedeck_Pacing="probe",
                               Connection="keep-alive")
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                sock.sendall(head.replace("\n", "\r\n").encode("latin-1") + b"\r\n")
                chunks = []
                while data := sock.recv(65536):  # a kept-alive socket would time out here
                    chunks.append(data)
        raw = b"".join(chunks)
        self.assertTrue(raw.startswith(b"HTTP/1.0 200 "), raw[:40])
        self.assertEqual(1, raw.count(b"HTTP/1."))

    def test_header_refusals_close_before_reading_the_body(self):
        with self.serve() as port:
            cases = [
                ("proxied", {"Forwarded": "for=192.0.2.1"}),
                ("proxied", {"X-Forwarded-For": "192.0.2.1"}),
                ("proxied", {"X-Real-IP": "192.0.2.1"}),
                ("proxied", {"Via": "1.1 proxy"}),
                ("host", {"Host": f"evil.example:{port}", "Origin": f"http://evil.example:{port}"}),
                ("host", {"Host": f"127.0.0.1:{port + 1}"}),
                ("origin", {"Origin": "null"}),
                ("origin", {"Origin": "http://evil.example"}),
                ("origin", {"Host": f"localhost:{port}"}),
                ("fetch-site", {"Sec-Fetch-Site": "cross-site"}),
                ("fetch-site", {"Sec-Fetch-Site": "same-site"}),
                ("header", {"X-Lecturedeck-Pacing": "1"}),
            ]
            for code, extra in cases:
                with self.subTest(code=code, headers=extra):
                    head = pacing_head(port, **{key.replace("-", "_"): value
                                                for key, value in extra.items()})
                    status, payload = raw_request(port, head)
                    self.assertEqual(403, status)
                    self.assertEqual({"error": code}, json.loads(payload))
            for code, omitted in (("origin", "Origin"), ("header", "X-Lecturedeck-Pacing")):
                with self.subTest(code=code, omitted=omitted):
                    status, payload = raw_request(port, pacing_head(port, omit=(omitted,)))
                    self.assertEqual((403, {"error": code}), (status, json.loads(payload)))
            status, payload = raw_request(port, pacing_head(port, omit=("Content-Length",)))
            self.assertEqual(411, status)
            chunked = pacing_head(port, omit=("Content-Length",), Transfer_Encoding="chunked")
            self.assertEqual(411, raw_request(port, chunked)[0])
            status, payload = raw_request(port, pacing_head(port, length=2 * 1024 * 1024))
            self.assertEqual((413, {"error": "too-large"}), (status, json.loads(payload)))
            text_plain = pacing_head(port, Content_Type="text/plain")
            self.assertEqual(415, raw_request(port, text_plain)[0])
        self.assertFalse(self.records.exists())

    def test_foreign_peer_is_refused_before_the_body_is_read(self):
        with self.serve() as port, patch("lecturedeck.pacing.same_machine", return_value=False):
            status, payload = raw_request(port, pacing_head(port, length=100), timeout=5)
            self.assertEqual((403, {"error": "not-same-machine"}), (status, json.loads(payload)))
            version = json.loads(self.get(port, "/__lecturedeck/version")[1])
            self.assertEqual("not-this-machine", version["pacing"])
        self.assertFalse(self.records.exists())

    def test_body_and_schedule_refusals(self):
        with self.serve() as port:
            self.assertEqual(
                (400, {"error": "invalid", "detail": "json"}),
                self.post(port, body=b"{not json"),
            )
            self.assertEqual(
                (422, {"error": "not-scheduled"}),
                self.post(port, segment_record(date="2026-01-02")),
            )
            self.assertEqual(
                (422, {"error": "wrong-unit"}), self.post(port, segment_record(unit="other"))
            )
            status, reply = self.post(port, segment_record(rev=0))
            self.assertEqual((400, {"error": "invalid", "detail": "rev"}), (status, reply))
            status, _, response = self.get(
                port, "/__lecturedeck/pacing", "OPTIONS",
                Origin="http://evil.example", Access_Control_Request_Method="POST",
                Access_Control_Request_Headers="content-type,x-lecturedeck-pacing",
            )
            self.assertEqual(501, status)
            self.assertFalse(
                [name for name, _ in response.getheaders()
                 if name.lower().startswith("access-control-")]
            )
            self.assertEqual(404, self.get(port, "/__lecturedeck/pacing")[0])
            status, payload = raw_request(port, pacing_head(port, path="/__lecturedeck/other"))
            self.assertEqual((404, {"error": "not-found"}), (status, json.loads(payload)))
        self.assertFalse(self.records.exists())

        bare = make_unit(self.root, "bare", schedule=None)
        with self.serve(bare) as port:
            self.assertEqual((404, {"error": "no-schedule"}),
                             self.post(port, segment_record(unit="bare")))
            self.assertEqual(
                (404, {"error": "no-schedule"}),
                self.post(port, body=b"", X_Lecturedeck_Pacing="probe"),
            )
        self.assertFalse((bare / "pacing-records").exists())

        with self.serve(pacing_records=False) as port:
            status, payload = raw_request(port, pacing_head(port))
            self.assertEqual((404, {"error": "disabled"}), (status, json.loads(payload)))
        self.assertFalse(self.records.exists())

    def test_sink_injection_and_version_state(self):
        with self.serve() as port:
            status, body, _ = self.get(port, "/webdeck/", Host=f"127.0.0.1:{port}")
            self.assertEqual(200, status)
            self.assertIn(
                b'<script src="../__lecturedeck/pacing-sink.js" data-unit="unit"></script>', body
            )
            self.assertIn(b"pacing-sink.js", self.get(port, "/webdeck/index.html")[1])
            self.assertIn(b"pacing-sink.js",
                          self.get(port, "/webdeck/", Host=f"localhost:{port}")[1])
            for host in (f"evil.example:{port}", f"mac.local:{port}"):
                with self.subTest(host=host):
                    body = self.get(port, "/webdeck/", Host=host)[1]
                    self.assertNotIn(b"pacing-sink.js", body)
                    self.assertNotIn(b"data-unit", body)
                    self.assertIn(b"__lecturedeck/adjust.js", body)
                    self.assertEqual(404, self.get(port, pacing.PACING_SINK_ROUTE, Host=host)[0])
                    version = json.loads(self.get(port, "/__lecturedeck/version", Host=host)[1])
                    self.assertEqual("use-local-address", version["pacing"])
            proxied = self.get(port, "/webdeck/", X_Forwarded_For="192.0.2.1")[1]
            self.assertNotIn(b"pacing-sink.js", proxied)
            version = json.loads(self.get(port, "/__lecturedeck/version", Via="1.1 proxy")[1])
            self.assertEqual("proxied", version["pacing"])
            status, body, response = self.get(port, pacing.PACING_SINK_ROUTE)
            self.assertEqual(200, status)
            self.assertEqual("text/javascript", response.getheader("Content-Type"))
            self.assertIn(b"lecturedeckPacingSink", body)
            self.assertEqual(200, self.get(port, pacing.PACING_SINK_ROUTE, "HEAD")[0])
            version = json.loads(self.get(port, "/__lecturedeck/version")[1])
            self.assertEqual("on", version["pacing"])
        with self.serve(pacing_records=False) as port:
            body = self.get(port, "/webdeck/")[1]
            self.assertNotIn(b"pacing-sink.js", body)
            self.assertNotIn(b"data-unit", body)
            self.assertEqual(404, self.get(port, pacing.PACING_SINK_ROUTE)[0])
            self.assertEqual(404, self.get(port, pacing.PACING_SINK_ROUTE, "HEAD")[0])
            version = json.loads(self.get(port, "/__lecturedeck/version")[1])
            self.assertEqual("off", version["pacing"])

    def test_concurrent_revisions_keep_the_newest(self):
        barrier = threading.Barrier(2)
        results = {}
        with self.serve() as port:
            def send(rev):
                barrier.wait(5)
                results[rev] = self.post(port, segment_record(rev=rev))[0]

            threads = [threading.Thread(target=send, args=(rev,)) for rev in (10, 11)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)
        self.assertEqual(200, results[11])
        self.assertIn(results[10], {200, 409})
        stored = json.loads((self.records / FILE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(11, stored["rev"])
        self.assertEqual([FILE_NAME], sorted(path.name for path in self.records.iterdir()))


class SelectorPacingTest(HTTPHelpers, unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.folder = self.root / "presentations"
        self.folder.mkdir()
        self.unit = make_unit(self.folder, "unit one")
        self.other = make_unit(self.folder, "other")

    def test_selector_routes_records_to_the_chosen_unit_only(self):
        record = segment_record(unit="unit one", path="/decks/unit%20one/webdeck/")
        name = f"{DAY}_0859_unit-one_{SEGMENT}.json"
        server = make_selector_server(self.folder, "127.0.0.1", 0, livereload=False, quiet=True)
        with serving(server) as port:
            status, reply = self.post(
                port, record, path="/decks/unit%20one/__lecturedeck/pacing"
            )
            self.assertEqual((200, f"pacing-records/{name}"), (status, reply["file"]))
            self.assertEqual(
                (422, {"error": "wrong-unit"}),
                self.post(port, record, path="/decks/other/__lecturedeck/pacing"),
            )
            moved = dict(record, unit="other")
            self.assertEqual(
                (422, {"error": "wrong-path"}),
                self.post(port, moved, path="/decks/other/__lecturedeck/pacing"),
            )
            for path in ("/decks/missing/__lecturedeck/pacing", "/__lecturedeck/pacing"):
                with self.subTest(path=path):
                    status, payload = raw_request(port, pacing_head(port, path=path))
                    self.assertEqual((404, {"error": "not-found"}), (status, json.loads(payload)))
            for path in (
                f"/decks/unit%20one/pacing-records/{name}",
                f"/decks/unit%20one/webdeck/../pacing-records/{name}",
                f"/decks/unit%20one/webdeck/%2e%2e/pacing-records/{name}",
                f"/pacing-records/{name}",
                "/decks/unit%20one/pacing-records/",
            ):
                with self.subTest(path=path):
                    self.assertEqual(404, self.get(port, path)[0])
            body = self.get(port, "/decks/unit%20one/webdeck/")[1]
            self.assertIn(b'data-unit="unit one"', body)
            status, body, _ = self.get(port, "/decks/unit%20one/__lecturedeck/pacing-sink.js")
            self.assertEqual(200, status)
            self.assertEqual(404, self.get(port, pacing.PACING_SINK_ROUTE)[0])
            version = json.loads(self.get(port, "/decks/other/__lecturedeck/version")[1])
            self.assertEqual("on", version["pacing"])
        self.assertTrue((self.unit / "pacing-records" / name).is_file())
        self.assertEqual([name], [p.name for p in (self.unit / "pacing-records").iterdir()])
        self.assertFalse((self.other / "pacing-records").exists())
        self.assertFalse((self.folder / "pacing-records").exists())

    def test_selector_without_pacing_records(self):
        server = make_selector_server(self.folder, "127.0.0.1", 0, livereload=False,
                                      quiet=True, pacing_records=False)
        with serving(server) as port:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connection.request("GET", "/decks/other/webdeck/")
            self.assertNotIn(b"pacing-sink.js", connection.getresponse().read())
            connection.close()
            status, payload = raw_request(
                port, pacing_head(port, path="/decks/other/__lecturedeck/pacing")
            )
            self.assertEqual((404, {"error": "disabled"}), (status, json.loads(payload)))


class InstantBoundsTest(unittest.TestCase):
    def test_instants_stay_within_the_date_plus_minus_14_hours(self):
        # UTC+14 starts its day at 10:00Z the day before; UTC-12 ends it at 12:00Z after.
        wide = segment_record()
        wide["window"]["before"] = 240
        wide["window"]["from"] = "2026-01-01T05:00:00.000Z"
        self.assertEqual(240, parse(wide)["window"]["before"])
        early = segment_record()
        early["slot"]["startAt"] = "2025-12-31T09:59:59.999Z"
        late = segment_record()
        late["window"]["to"] = "2026-01-02T14:00:00.001Z"
        for record, detail in ((early, "slot.startAt"), (late, "window.to")):
            with self.subTest(detail), self.assertRaises(PacingRefusal) as caught:
                parse(record, now=NOW + timedelta(days=2))
            self.assertEqual(detail, caught.exception.detail)


if __name__ == "__main__":
    unittest.main()
