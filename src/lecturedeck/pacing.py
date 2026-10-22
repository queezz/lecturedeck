"""Serve-time pacing records: gates, schema, and the atomic writer.

The only file lecturedeck writes while serving. A browser on the serving
computer POSTs one page load's pacing segment; the server checks where the
request came from, validates the record against a strict whitelist, and
writes it to ``<unit>/pacing-records/`` beside ``webdeck/``, never inside it.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import socket
import stat
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

RECORDS_DIR = "pacing-records"
PACING_ROUTE = "/__lecturedeck/pacing"
PACING_SINK_ROUTE = "/__lecturedeck/pacing-sink.js"
PACING_HEADER = "X-Lecturedeck-Pacing"
RECORD_KIND = "lecturedeck-pacing-segment"
MAX_BODY = 262144
MAX_SLIDES = 1000
MAX_VISITS = 5000
MAX_PAUSES = 5000
MAX_TEXT = 500
MAX_DECK_TEXT = 300
MAX_SLIDE_ID = 200
MAX_SEGMENTS_PER_DATE = 100
MAX_EXISTING_BYTES = 4 * 1024 * 1024
MAX_SCHEDULE_BYTES = 1024 * 1024
REPLACE_RETRIES = 5
REPLACE_DELAY_S = 0.1
FUTURE_SLACK = timedelta(minutes=5)
DAY_SLACK = timedelta(hours=14)
PHASE_SLACK_MS = 1000
MAX_DURATION_MS = 86_400_000
MAX_REV = 2**31 - 1
PROXY_HEADERS = ("Forwarded", "X-Forwarded-For", "X-Real-IP", "Via")
PHASES = frozenset({"before", "slot", "after"})
PAUSE_REASONS = frozenset({"overview", "report", "dialog", "hidden", "suspended", "clock"})

_SEGMENT = re.compile(r"[0-9a-f]{12}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_HHMM = re.compile(r"(?:[01][0-9]|2[0-3])[0-5][0-9]")
_CLOCK = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
_INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z")
_TIME_ZONE = re.compile(r"[A-Za-z0-9_+/-]{1,64}")
_LABEL = re.compile(r"[BH]?[0-9]{1,6}")
_VIEWER = re.compile(r"[0-9A-Za-z.+-]{1,40}")
_HOST = re.compile(
    r"(?:\[(?P<v6>[0-9A-Fa-f:.]+)\]|(?P<name>[A-Za-z0-9.-]+))(?::(?P<port>[0-9]{1,5}))?"
)
_LENGTH = re.compile(r"[0-9]+")
_BAD_TEXT = re.compile("[\x00-\x1f\x7f\ud800-\udfff]")
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_UNSAFE_HOST = re.compile(r"[^A-Za-z0-9.-]+")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MS = timedelta(milliseconds=1)
_MULTIPLE = "\x00"  # a repeated header: present, but never equal to an allowed value
_LOCK = threading.Lock()


class PacingRefusal(Exception):
    """A request the server answers with ``status`` and a JSON error body."""

    def __init__(self, status: int, code: str, detail: str | None = None, **extra) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra

    def payload(self) -> dict:
        body: dict = {"error": self.code}
        if self.detail is not None:
            body["detail"] = self.detail
        body.update(self.extra)
        return body


class StaleRecord(PacingRefusal):
    """The stored segment already has this revision or a newer one."""

    def __init__(self, rev: int) -> None:
        super().__init__(409, "stale", rev=rev)
        self.rev = rev


def _invalid(detail: str) -> PacingRefusal:
    return PacingRefusal(400, "invalid", detail)


# Request gates ---------------------------------------------------------------


def _header_values(headers, name: str) -> list[str]:
    get_all = getattr(headers, "get_all", None)
    if get_all is not None:
        return [str(value) for value in (get_all(name) or [])]
    lowered = name.lower()
    return [str(value) for key, value in headers.items() if key.lower() == lowered]


def _one(headers, name: str) -> str | None:
    values = _header_values(headers, name)
    if not values:
        return None
    return values[0] if len(values) == 1 else _MULTIPLE


def _address(value: object):
    try:
        address = ipaddress.ip_address(str(value))
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


_LOOPBACK_LITERALS = (ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1"))


def same_machine(peer: object, local: object) -> bool:
    """A loopback peer, or one connecting from the server's own address."""
    peer_address = _address(peer)
    if peer_address is None:
        return False
    if peer_address.is_loopback:
        return True
    local_address = _address(local)
    return local_address is not None and peer_address == local_address


def host_allowed(host: str | None, local: object, port: int) -> bool:
    """localhost, 127.0.0.1, [::1] or the connection's own IP literal, on our port."""
    if not isinstance(host, str):
        return False
    match = _HOST.fullmatch(host)
    if match is None:
        return False
    host_port = int(match["port"]) if match["port"] is not None else 80
    if host_port != port:
        return False
    name = match["name"]
    if name is not None and name.lower() == "localhost":
        return True
    literal = match["v6"] if match["v6"] is not None else name
    try:
        parsed = ipaddress.ip_address(literal)
    except ValueError:
        return False
    if (match["v6"] is not None) != (parsed.version == 6):
        return False
    address = _address(parsed)
    if address in _LOOPBACK_LITERALS:
        return True
    local_address = _address(local)
    return local_address is not None and address == local_address


def page_problem(headers, peer: object, local: object, port: int) -> str | None:
    """Why this request does not come from a browser on the serving computer."""
    if any(_header_values(headers, name) for name in PROXY_HEADERS):
        return "proxied"
    if not same_machine(peer, local):
        return "not-same-machine"
    if not host_allowed(_one(headers, "Host"), local, port):
        return "host"
    return None


def write_problem(headers) -> str | None:
    """Why this request is not a same-origin pacing POST from the sink."""
    origin = _one(headers, "Origin")
    host = _one(headers, "Host")
    if (
        origin is None
        or host is None
        or not origin.startswith("http://")
        or origin[len("http://"):].lower() != host.lower()
    ):
        return "origin"
    fetch_site = _one(headers, "Sec-Fetch-Site")
    if fetch_site is not None and fetch_site != "same-origin":
        return "fetch-site"
    if _one(headers, PACING_HEADER) not in {"2", "probe"}:
        return "header"
    return None


def body_length(headers) -> int:
    """The declared body length; refuses chunked, missing or oversized bodies.

    Runs before any byte of the body is read.
    """
    if _header_values(headers, "Transfer-Encoding"):
        raise PacingRefusal(411, "length-required")
    declared = _one(headers, "Content-Length")
    if declared is None or not _LENGTH.fullmatch(declared):
        raise PacingRefusal(411, "length-required")
    digits = declared.lstrip("0") or "0"
    if len(digits) > 9 or int(digits) > MAX_BODY:
        raise PacingRefusal(413, "too-large")
    return int(digits)


def is_json_content(headers) -> bool:
    value = _one(headers, "Content-Type")
    return value is not None and value.split(";", 1)[0].strip().lower() == "application/json"


# Schedule and file names -----------------------------------------------------


def _real_date(value: object) -> bool:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def scheduled_dates(webdeck: Path) -> frozenset[str] | None:
    """The unit's teaching dates from webdeck/presentation-time.json, if any."""
    path = Path(webdeck) / "presentation-time.json"
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_SCHEDULE_BYTES + 1)
        if len(raw) > MAX_SCHEDULE_BYTES:
            return None
        data = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("dates"), list):
        return None
    return frozenset(value for value in data["dates"] if _real_date(value))


def unit_token(unit: str) -> str:
    """The unit name made safe for a file name, at most 60 characters."""
    token = _UNSAFE_NAME.sub("-", unit).strip("-.")
    token = token[:60].strip("-.")
    return token or "unit"


def record_filename(record: dict, unit: str) -> str:
    return f"{record['date']}_{record['opened']}_{unit_token(unit)}_{record['segment']}.json"


def machine_label() -> str:
    """This computer's host name, reduced to [A-Za-z0-9.-]{1,64}."""
    try:
        name = socket.gethostname()
    except OSError:
        name = ""
    label = _UNSAFE_HOST.sub("-", name).strip("-.")[:64].strip("-.")
    return label or "unknown"


def instant_text(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return f"{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond // 1000:03d}Z"


# Record schema ---------------------------------------------------------------

_TOP_KEYS = frozenset({
    "schema", "kind", "segment", "rev", "unit", "path", "deck", "viewer", "date",
    "opened", "timeZone", "slot", "window", "slides", "visits", "pauses", "fullscreenMs",
})
_TOP_OPTIONAL = frozenset({"migratedFrom"})
_SLOT_KEYS = frozenset({"start", "end", "startAt", "endAt"})
_WINDOW_KEYS = frozenset({"before", "after", "from", "to"})
_SLIDE_KEYS = frozenset({"number", "label", "title", "section"})
_SLIDE_OPTIONAL = frozenset({"backup", "review"})
_VISIT_KEYS = frozenset({"slideId", "startedAt", "durationMs", "phase"})
_PAUSE_KEYS = frozenset({"startedAt", "durationMs", "why"})


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _refuse_constant(_name: str):
    raise ValueError("non-finite number")


def _load(body: bytes) -> object:
    try:
        text = body.decode("utf-8")
        return json.loads(
            text, parse_constant=_refuse_constant, object_pairs_hook=_unique_object
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise _invalid("json") from error


def _object(value: object, keys: frozenset, optional: frozenset, field: str) -> dict:
    if not isinstance(value, dict):
        raise _invalid(field)
    present = set(value)
    if not keys <= present or not present <= keys | optional:
        raise _invalid(field)
    return value


def _int(value: object, field: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise _invalid(field)
    return value


def _text(value: object, field: str, *, high: int = MAX_TEXT, low: int = 0) -> str:
    if (
        not isinstance(value, str)
        or not low <= len(value) <= high
        or _BAD_TEXT.search(value)
    ):
        raise _invalid(field)
    return value


def _pattern(value: object, pattern: re.Pattern, field: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise _invalid(field)
    return value


class _Instants:
    """Parses record instants and bounds them to the teaching date."""

    def __init__(self, day: str, now: datetime) -> None:
        start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        self.low = (start - DAY_SLACK - _EPOCH) // _MS
        self.high = (start + timedelta(days=1) + DAY_SLACK - _EPOCH) // _MS
        self.latest = (now.astimezone(timezone.utc) + FUTURE_SLACK - _EPOCH) // _MS

    def parse(self, value: object, field: str, *, recorded: bool) -> int:
        if not isinstance(value, str) or not _INSTANT.fullmatch(value):
            raise _invalid(field)
        try:
            moment = datetime(
                int(value[0:4]), int(value[5:7]), int(value[8:10]),
                int(value[11:13]), int(value[14:16]), int(value[17:19]),
                int(value[20:23]) * 1000, tzinfo=timezone.utc,
            )
        except ValueError as error:
            raise _invalid(field) from error
        ms = (moment - _EPOCH) // _MS
        if not self.low <= ms <= self.high or (recorded and ms > self.latest):
            raise _invalid(field)
        return ms

    def recorded_end(self, ms: int, field: str) -> None:
        if ms > self.latest:
            raise _invalid(field)


def parse_record(
    body: bytes,
    *,
    dates: frozenset[str],
    unit: str,
    route_path: str,
    now: datetime,
) -> dict:
    """Validate one schema-2 segment and rebuild it from whitelisted fields.

    ``route_path`` is the deck path the server routed this POST for, e.g.
    ``/webdeck/`` or ``/decks/<quoted unit>/webdeck/``. Raises PacingRefusal
    (400 invalid with a field-path detail, or 422) and never echoes a value.
    """
    data = _load(body)
    data = _object(data, _TOP_KEYS, _TOP_OPTIONAL, "record")
    _int(data["schema"], "schema", 2, 2)
    if data["kind"] != RECORD_KIND:
        raise _invalid("kind")
    segment = _pattern(data["segment"], _SEGMENT, "segment")
    rev = _int(data["rev"], "rev", 1, MAX_REV)
    migrated = "migratedFrom" in data
    if migrated:
        _int(data["migratedFrom"], "migratedFrom", 1, 1)

    if _text(data["unit"], "unit") != unit:
        raise PacingRefusal(422, "wrong-unit")
    path = unquote(_text(data["path"], "path"))
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    if path != unquote(route_path):
        raise PacingRefusal(422, "wrong-path")

    deck = _text(data["deck"], "deck", high=MAX_DECK_TEXT)
    viewer = _pattern(data["viewer"], _VIEWER, "viewer")
    day = data["date"]
    if not _real_date(day):
        raise _invalid("date")
    if day not in dates:
        raise PacingRefusal(422, "not-scheduled")
    opened = _pattern(data["opened"], _HHMM, "opened")
    time_zone = _pattern(data["timeZone"], _TIME_ZONE, "timeZone")
    instants = _Instants(day, now)

    slot = _object(data["slot"], _SLOT_KEYS, frozenset(), "slot")
    slot_start = _pattern(slot["start"], _CLOCK, "slot.start")
    slot_end = _pattern(slot["end"], _CLOCK, "slot.end")
    start_at = instants.parse(slot["startAt"], "slot.startAt", recorded=False)
    end_at = instants.parse(slot["endAt"], "slot.endAt", recorded=False)
    window = _object(data["window"], _WINDOW_KEYS, frozenset(), "window")
    before = _int(window["before"], "window.before", 0, 240)
    after = _int(window["after"], "window.after", 0, 240)
    window_from = instants.parse(window["from"], "window.from", recorded=False)
    window_to = instants.parse(window["to"], "window.to", recorded=False)
    if not window_from <= start_at < end_at <= window_to:
        raise _invalid("window")
    if (
        window_from < start_at - before * 60_000 - PHASE_SLACK_MS
        or window_to > end_at + after * 60_000 + PHASE_SLACK_MS
    ):
        raise _invalid("window")

    raw_slides = data["slides"]
    if not isinstance(raw_slides, dict) or len(raw_slides) > MAX_SLIDES:
        raise _invalid("slides")
    slides: dict[str, dict] = {}
    for index, (slide_id, raw) in enumerate(raw_slides.items()):
        field = f"slides[{index}]"
        _text(slide_id, field, high=MAX_SLIDE_ID, low=1)
        raw = _object(raw, _SLIDE_KEYS, _SLIDE_OPTIONAL, field)
        slide = {
            "number": _int(raw["number"], f"{field}.number", 1, 100_000),
            "label": _pattern(raw["label"], _LABEL, f"{field}.label"),
            "title": _text(raw["title"], f"{field}.title"),
            "section": _text(raw["section"], f"{field}.section"),
        }
        for flag in ("backup", "review"):
            if flag in raw:
                if not isinstance(raw[flag], bool):
                    raise _invalid(f"{field}.{flag}")
                slide[flag] = raw[flag]
        slides[slide_id] = slide

    phase_bounds = {
        "before": (window_from, start_at),
        "slot": (start_at, end_at),
        "after": (end_at, window_to),
    }
    raw_visits = data["visits"]
    if not isinstance(raw_visits, list) or len(raw_visits) > MAX_VISITS:
        raise _invalid("visits")
    visits: list[dict] = []
    visited_ms = 0
    previous_end: int | None = None
    for index, raw in enumerate(raw_visits):
        field = f"visits[{index}]"
        raw = _object(raw, _VISIT_KEYS, frozenset(), field)
        slide_id = raw["slideId"]
        if not isinstance(slide_id, str) or slide_id not in slides:
            raise _invalid(f"{field}.slideId")
        started = instants.parse(raw["startedAt"], f"{field}.startedAt", recorded=True)
        duration = _int(raw["durationMs"], f"{field}.durationMs", 0, MAX_DURATION_MS)
        phase = raw["phase"]
        if not isinstance(phase, str) or phase not in PHASES:
            raise _invalid(f"{field}.phase")
        ended = started + duration
        instants.recorded_end(ended, f"{field}.durationMs")
        low, high = phase_bounds[phase]
        if started < low - PHASE_SLACK_MS or ended > high + PHASE_SLACK_MS:
            raise _invalid(f"{field}.phase")
        if not migrated and previous_end is not None and started < previous_end:
            raise _invalid(f"{field}.startedAt")
        previous_end = ended
        visited_ms += duration
        visits.append({
            "slideId": slide_id,
            "startedAt": raw["startedAt"],
            "durationMs": duration,
            "phase": phase,
        })
    if visited_ms > window_to - window_from:
        raise _invalid("visits")

    raw_pauses = data["pauses"]
    if not isinstance(raw_pauses, list) or len(raw_pauses) > MAX_PAUSES:
        raise _invalid("pauses")
    pauses: list[dict] = []
    for index, raw in enumerate(raw_pauses):
        field = f"pauses[{index}]"
        raw = _object(raw, _PAUSE_KEYS, frozenset(), field)
        started = instants.parse(raw["startedAt"], f"{field}.startedAt", recorded=True)
        if not window_from - PHASE_SLACK_MS <= started <= window_to + PHASE_SLACK_MS:
            raise _invalid(f"{field}.startedAt")
        duration = _int(raw["durationMs"], f"{field}.durationMs", 0, MAX_DURATION_MS)
        instants.recorded_end(started + duration, f"{field}.durationMs")
        why = raw["why"]
        if not isinstance(why, str) or why not in PAUSE_REASONS:
            raise _invalid(f"{field}.why")
        pauses.append({"startedAt": raw["startedAt"], "durationMs": duration, "why": why})

    fullscreen = data["fullscreenMs"]
    if fullscreen is None:
        if not migrated:
            raise _invalid("fullscreenMs")
    else:
        _int(fullscreen, "fullscreenMs", 0, visited_ms)

    record: dict = {
        "schema": 2,
        "kind": RECORD_KIND,
        "segment": segment,
        "rev": rev,
        "unit": unit,
        "path": route_path,
        "deck": deck,
        "viewer": viewer,
        "date": day,
        "opened": opened,
        "timeZone": time_zone,
        "slot": {
            "start": slot_start,
            "end": slot_end,
            "startAt": slot["startAt"],
            "endAt": slot["endAt"],
        },
        "window": {
            "before": before,
            "after": after,
            "from": window["from"],
            "to": window["to"],
        },
    }
    if migrated:
        record["migratedFrom"] = 1
    record["slides"] = slides
    record["visits"] = visits
    record["pauses"] = pauses
    record["fullscreenMs"] = fullscreen
    return record


# Writer ----------------------------------------------------------------------


def _is_link(path: Path) -> bool:
    """A symlink or a Windows junction (never a Dropbox placeholder)."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    junction = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", None)
    return junction is not None and getattr(info, "st_reparse_tag", 0) == junction


def _folder_refused(folder: Path) -> bool:
    return _is_link(folder) or (os.path.lexists(folder) and not folder.is_dir())


def probe_unit(unit_root: Path) -> None:
    """Raise 503 not-writable unless a record could be saved; writes nothing."""
    root = Path(unit_root)
    folder = root / RECORDS_DIR
    if not root.is_dir() or not os.access(root, os.W_OK) or _folder_refused(folder):
        raise PacingRefusal(503, "not-writable")
    if folder.is_dir() and not os.access(folder, os.W_OK):
        raise PacingRefusal(503, "not-writable")


def _stored_rev(target: Path) -> int:
    """The revision of the file about to be replaced; refuses anything unreadable."""
    try:
        with target.open("rb") as handle:
            raw = handle.read(MAX_EXISTING_BYTES + 1)
    except OSError as error:
        raise PacingRefusal(503, "write-failed") from error
    try:
        if len(raw) > MAX_EXISTING_BYTES:
            raise ValueError("oversized")
        existing = json.loads(raw.decode("utf-8"), parse_constant=_refuse_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise PacingRefusal(409, "unreadable-existing") from error
    if (
        not isinstance(existing, dict)
        or type(existing.get("schema")) is not int
        or existing["schema"] != 2
        or type(existing.get("rev")) is not int
    ):
        raise PacingRefusal(409, "unreadable-existing")
    return existing["rev"]


def _replace(source: Path, target: Path) -> None:
    """os.replace, retried while Dropbox or antivirus briefly holds the target."""
    for attempt in range(REPLACE_RETRIES + 1):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == REPLACE_RETRIES:
                raise
            time.sleep(REPLACE_DELAY_S)


def _sync_folder(folder: Path) -> None:
    if os.name != "posix":
        return
    try:
        descriptor = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def store_record(
    unit_root: Path,
    unit: str,
    record: dict,
    *,
    host: str,
    version: str,
    now: datetime,
) -> dict:
    """Atomically write one validated segment to <unit>/pacing-records/.

    The record must come from parse_record. Raises PacingRefusal (StaleRecord
    for an equal or lower revision). Never deletes a record.
    """
    root = Path(unit_root).resolve()
    name = record_filename(record, unit)
    saved_at = instant_text(now)
    with _LOCK:
        folder = root / RECORDS_DIR
        if _folder_refused(folder):
            raise PacingRefusal(503, "not-writable")
        try:
            folder.mkdir(exist_ok=True)
        except OSError as error:
            raise PacingRefusal(503, "not-writable") from error
        if _folder_refused(folder):
            raise PacingRefusal(503, "not-writable")
        target = folder / name
        parent = target.parent.resolve()
        if parent != root / RECORDS_DIR or root not in parent.parents:
            raise PacingRefusal(503, "not-writable")

        same_segment = list(folder.glob(f"{record['date']}_*_{record['segment']}.json"))
        if any(path.name != name for path in same_segment):
            raise PacingRefusal(400, "invalid", "segment-renamed")
        if same_segment or os.path.lexists(target):
            if _is_link(target) or not target.is_file():
                raise PacingRefusal(409, "unreadable-existing")
            stored = _stored_rev(target)
            if stored >= record["rev"]:
                raise StaleRecord(stored)
        else:
            dated = sum(1 for _ in folder.glob(f"{record['date']}_*.json"))
            if dated >= MAX_SEGMENTS_PER_DATE:
                raise PacingRefusal(429, "too-many-segments")

        document = dict(record)
        document["savedAt"] = saved_at
        document["savedBy"] = {"host": host, "lecturedeck": version}
        payload = (json.dumps(document, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        temporary = folder / f".~{name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        try:
            with open(temporary, "xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            _replace(temporary, target)
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise PacingRefusal(503, "write-failed") from error
        _sync_folder(folder)
    return {"ok": True, "rev": record["rev"], "file": f"{RECORDS_DIR}/{name}", "savedAt": saved_at}
