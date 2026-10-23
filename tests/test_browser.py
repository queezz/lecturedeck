"""Chromium smoke suite for the presenter contract.

Runs only when the optional Playwright dev dependency and its Chromium
browser are installed; otherwise every test is skipped. The suite asserts
the mechanical contract — loading paths, navigation, step-by-step reveals,
wheel input, overview, fullscreen, theme, media attributes, iframe
interaction, and the serve-only geometry-adjust guards, and the pacing
recorder: its window, journal, report and saving to disk through the
serve-only sink. Visual density and pedagogical quality remain human
judgment and are deliberately out of scope.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import struct
import tempfile
import threading
import time
import unittest
import zlib
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lecturedeck import __version__
from lecturedeck.server import make_selector_server, make_server
from lecturedeck.validation import release_unit

try:
    from playwright.sync_api import sync_playwright

    HAVE_PLAYWRIGHT = True
except ImportError:
    HAVE_PLAYWRIGHT = False


def png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        data = kind + payload
        return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    body = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", body) + chunk(b"IEND", b"")
    )


def build_json_unit(unit: Path) -> None:
    webdeck = unit / "webdeck"
    assets = webdeck / "assets"
    assets.mkdir(parents=True)
    (assets / "figure.png").write_bytes(png(320, 180, (131, 165, 152)))
    (assets / "poster.png").write_bytes(png(320, 180, (250, 189, 47)))
    (assets / "clip.mp4").write_bytes(b"not a real encoding; attributes only")
    demo = assets / "demo"
    demo.mkdir()
    (demo / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Demo</title>"
        "<body><button id='next'>Next slide</button>"
        "<script type='module' src='./app.js'></script></body>",
        encoding="utf-8",
    )
    (demo / "app.js").write_text(
        'import { advance } from "./lib.js";\n'
        "document.querySelector('#next').addEventListener('click', advance);\n",
        encoding="utf-8",
    )
    (demo / "lib.js").write_text(
        "export const advance = () =>"
        ' parent.postMessage({type: "lecturedeck:navigate", direction: 1}, "*");\n',
        encoding="utf-8",
    )
    deck = {
        "deck": 1,
        "meta": {
            "title": "Smoke deck",
            "tabTitle": "Smoke deck · 1",
            "section": "SMOKE",
            "opening": "OPENING",
            "favicon": "complex",
            "selectorGroup": "Lectures",
            "selectorHero": "assets/figure.png",
        },
        "slides": [
            {"id": "s-title", "type": "title", "title": "Smoke deck", "claim": "Slide one."},
            {"id": "s-a", "title": "Statement A", "claim": "Second slide."},
            {
                "id": "s-figure",
                "title": "Figure",
                "figure": {
                    "id": "fig-1",
                    "src": "assets/figure.png",
                    "alt": "Figure",
                    "shift": [10, -6],
                    "scale": 1.1,
                },
            },
            {
                "id": "s-video",
                "title": "Video",
                "video": {
                    "src": "assets/clip.mp4",
                    "type": "video/mp4",
                    "poster": "assets/poster.png",
                    "title": "Smoke video",
                },
            },
            {
                "id": "s-interactive",
                "chrome": False,
                "interactive": {"src": "assets/demo/index.html", "title": "Demo"},
            },
            {"id": "s-b", "title": "Statement B", "claim": "Sixth slide."},
            {"id": "s-c", "title": "Statement C", "claim": "Seventh slide."},
            {"id": "s-d", "title": "Statement D", "claim": "Eighth slide."},
            {
                "id": "s-formula",
                "title": "Modest formula",
                "eyebrow": "Practice",
                "beat": "INTERNAL-S14",
                "layout": "equation",
                "formula": {
                    "mathml": "<math xmlns='http://www.w3.org/1998/Math/MathML' "
                    "display='block'><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow></math>"
                },
            },
            {
                "id": "s-huge-formula",
                "title": "Oversized formula",
                "layout": "equation",
                "formula": {
                    "mathml": "<math xmlns='http://www.w3.org/1998/Math/MathML' "
                    "display='block'><mrow>"
                    + "<msup><mi>x</mi><mn>2</mn></msup><mo>+</mo>" * 12
                    + "<mn>1</mn></mrow></math>"
                },
            },
            {
                "id": "s-derivation",
                "title": "Aligned derivation",
                "layout": "equation",
                "formula": {
                    "mathml": "<math xmlns='http://www.w3.org/1998/Math/MathML' "
                    "display='block'><mtable columnalign='right left'>"
                    "<mtr><mtd><mi>S</mi></mtd><mtd></mtd></mtr>"
                    "<mtr><mtd></mtd><mtd><mo form='infix'>=</mo><mi>a</mi>"
                    "<mo>+</mo><mi>b</mi></mtd></mtr>"
                    "<mtr><mtd></mtd><mtd><mo form='infix'>≤</mo><mn>2</mn>"
                    "<mi>b</mi></mtd></mtr>"
                    "</mtable></math>"
                },
            },
        ],
    }
    (webdeck / "deck.json").write_text(json.dumps(deck), encoding="utf-8")


APPENDIX_DECK = {
    "deck": 1,
    "meta": {"title": "Appendix deck", "section": "SMOKE", "opening": "OPENING"},
    "slides": [
        {"id": "a-title", "type": "title", "title": "Appendix deck", "claim": "Main one."},
        {"id": "a-two", "title": "Main two", "claim": "Main two."},
        {"id": "a-three", "title": "Main three", "claim": "Main three."},
        {"id": "a-backup", "type": "section", "title": "Backup", "appendix": True},
        {"id": "a-derivation", "title": "Backup derivation", "claim": "Backup two."},
    ],
}


# One slide with a source line in its footer, for the controls gear.
FOOTER_DECK = {
    "deck": 1,
    "meta": {"title": "Footer deck", "section": "SMOKE", "opening": "OPENING"},
    "slides": [
        {"id": "f-one", "title": "With a source", "claim": "Claim.",
         "source": "A source line that starts at the slide's left edge"},
    ],
}


# A meeting that opens with a homework review: the review reads H1, H2 and
# the lecture's own slides count 1, 2, 3 around it.
REVIEW_DECK = {
    "deck": 1,
    "meta": {"title": "Review deck", "section": "SMOKE", "opening": "OPENING"},
    "slides": [
        {"id": "r-title", "type": "title", "title": "Review deck", "claim": "Main one."},
        {"id": "r-review", "type": "section", "title": "Homework review", "review": True},
        {"id": "r-solution", "title": "Solution", "claim": "Worked.", "review": True},
        {"id": "r-part", "type": "section", "title": "Part A"},
        {"id": "r-idea", "title": "Idea", "claim": "Main three."},
        {"id": "r-backup", "type": "section", "title": "Backup", "appendix": True},
    ],
}


STEPS_DECK = {
    "deck": 1,
    "meta": {"title": "Steps deck", "section": "SMOKE", "opening": "OPENING"},
    "slides": [
        {"id": "st-plain", "type": "title", "title": "Steps deck",
         "claim": 'No steps here; <a id="st-jump" href="#/1.2">all of slide two</a>.'},
        {"id": "st-copy", "title": "Copy steps", "claim": "Always shown.",
         "body": '<p data-step="1" id="st-one">First point.</p>'
                 '<p data-step="2" id="st-two-a">Second point.</p>'
                 '<p data-step="2" id="st-two-b">Shown with it, <a id="st-link" href="#/0">'
                 "a link</a>.</p>"},
        {"id": "st-figure", "title": "Figure step",
         "claim": '<span data-step="1" id="st-claim">Look here.</span>',
         "figure": {"id": "fig-step", "src": "assets/figure.png", "alt": "Figure", "step": 2}},
        {"id": "st-cards", "title": "Card steps", "cards": [
            {"value": "Always"}, {"value": "One", "step": 1}, {"value": "Two", "step": 2}]},
        {"id": "st-demo", "title": "Demo step",
         "claim": '<span data-step="1" id="st-after-demo">Revealed by the demo.</span>',
         "interactive": {"src": "assets/demo/index.html", "title": "Demo"}},
        {"id": "st-video", "title": "Video step",
         "video": {"src": "assets/clip.mp4", "type": "video/mp4", "poster": "assets/poster.png",
                   "title": "Clip", "step": 1,
                   "caption": '<span data-step="2" id="st-caption">After the clip.</span>'}},
        {"id": "st-backup", "type": "section", "title": "Backup", "appendix": True,
         "claim": '<span data-step="1" id="st-backup-step">Backup detail.</span>'},
    ],
}

# The controls strip's step dots read as text: ● for a step shown, ○ for
# one to come (they are drawn marks, not glyphs).
CONTROL_DOTS = (
    "[...document.querySelector('#step-indicator').children]"
    ".map(m => m.classList.contains('shown') ? '●' : '○').join('')"
)

STEP_STATE = """() => {
  const frame = document.querySelector('#deck .slide-frame');
  const dots = document.querySelector('#step-indicator');
  const name = node => node.id || node.dataset.figureId || node.textContent.trim();
  return {
    index: Number(frame.dataset.index),
    hash: location.hash,
    hidden: [...frame.querySelectorAll('.step-hidden')].map(name),
    current: [...frame.querySelectorAll('.step-current')].map(name),
    counter: document.querySelector('#counter').textContent,
    dots: dots.hidden ? null : %s,
  };
}""" % CONTROL_DOTS

# Ten main slides and two backups: steps on some (index: count), the same
# long source line on all. The line wraps near the footer's width, so any
# room the step dots took from it would change its box, and 9 / 10 and
# 10 / 10 differ in width unless the page number keeps one box.
FIXED_STEPS = {1: 1, 2: 3, 5: 2, 9: 3, 11: 2}
FIXED_SOURCE = "Source: " + "a long citation that fills the footer line, " * 5


def fixed_box_slide(index: int) -> dict:
    steps = FIXED_STEPS.get(index, 0)
    body = "".join(f'<p data-step="{n}">Point {n}.</p>' for n in range(1, steps + 1))
    slide = {"id": f"fx-{index}", "title": f"Slide {index}", "claim": "Always shown.",
             "body": body or "<p>No steps here.</p>", "source": FIXED_SOURCE}
    if index == 10:
        slide["appendix"] = True
    return slide


FIXED_BOX_DECK = {
    "deck": 1,
    "meta": {"title": "Fixed boxes", "section": "COURSE NAME"},
    "slides": [fixed_box_slide(index) for index in range(12)],
}

# The boxes of every fixed element, and where the step dots sit.
FIXED_BOXES = """() => {
  const rect = s => {
    const r = document.querySelector(s).getBoundingClientRect();
    return [r.x, r.y, r.width, r.height];
  };
  const selectors = ['#deck .page-number', '#deck .course-name', '#deck .source',
    '#deck .slide-foot', '#deck .slide-head', '#deck .slide-body',
    '#counter', '#controls-tools', '#appearance-button', '#viewer-version'];
  const boxes = Object.fromEntries(selectors.map(s => [s, rect(s)]));
  const frame = document.querySelector('#deck .slide-frame').getBoundingClientRect();
  const scale = frame.width / 1280;
  const number = document.querySelector('#deck .page-number').getBoundingClientRect();
  const counter = document.querySelector('#counter').getBoundingClientRect();
  const cue = document.querySelector('#deck .footer-nav > .step-cue');
  const dots = document.querySelector('#step-indicator');
  const marks = node => node && node.checkVisibility()
    ? [...node.children].map(m => m.classList.contains('shown') ? 'shown' : '') : [];
  const problems = [];
  if (cue) {
    const r = cue.getBoundingClientRect();
    if (r.top < number.bottom || r.bottom > frame.bottom - 4 * scale)
      problems.push(`cue not under the page number inside the frame: ${r.top}-${r.bottom}`);
    if (Math.abs(r.right - number.right) > 0.5) problems.push('cue not right under the number');
    for (const m of cue.children) {
      const b = m.getBoundingClientRect();
      if (Math.abs(b.width - 8 * scale) > 0.5 || Math.abs(b.height - 8 * scale) > 0.5)
        problems.push(`cue mark ${b.width}x${b.height}`);
    }
  }
  const slot = document.querySelector('.counter-slot').getBoundingClientRect();
  if (['x', 'y', 'width', 'height'].some(k => slot[k] !== counter[k]))
    problems.push('the counter slot is not exactly the counter box');
  for (const m of dots.hidden ? [] : dots.children) {
    const b = m.getBoundingClientRect();
    if (b.width < 5 || b.left < counter.left || b.right > counter.right
        || b.top < counter.top || b.bottom > counter.bottom)
      problems.push(`controls dot ${b.left},${b.top} ${b.width} outside the counter`);
  }
  return {hash: location.hash, boxes, cue: marks(cue), dots: marks(dots), problems};
}"""


def crowded_link_deck() -> dict:
    """A title page linking forward, a roomy equation slide, then a sweep of overfull ones.

    Chromium's page fragmentation pushed the whole body of an equation slide
    that overflowed its page past the page and out of the clipped frame: a
    blank page in the PDF (found on five formula pages of a 149-slide deck,
    2026-10-14). It happens only inside a narrow band of overflow, and the
    band moves with the font: without containment Calibri drops the body at
    22-26 gloss lines, Arial at 20-23, and more overflow does not reproduce
    it. So the deck sweeps 18-28 lines, one slide each, to land in the band
    whatever font the machine has. Each body ends with a link home, and a
    dropped body drops its link annotation.
    """
    formula = (
        "<math display='block'><mi>R</mi><mo>=</mo><msubsup><mo>∫</mo><mn>0</mn>"
        "<mi>∞</mi></msubsup><mi>r</mi><mi>d</mi><mi>ω</mi></math>"
    )
    crowded = [
        {
            "id": f"crowded-{lines}",
            "title": f"Crowded {lines}",
            "layout": "equation",
            "claim": "A claim long enough to wrap onto a second line of the equation layout.",
            "formula": {
                "label": "Label",
                "mathml": formula,
                "gloss": [f"Gloss line {n} of a crowded equation slide" for n in range(lines)]
                + ['Names: <a href="#/0">back to the start</a>'],
            },
        }
        for lines in (2, *range(18, 29))
    ]
    return {
        "deck": 1,
        "meta": {"title": "Crowded deck", "section": "SMOKE"},
        "slides": [
            {"id": "start", "type": "title", "title": "Crowded deck",
             "claim": 'Jump to <a href="#/2">the first overfull slide</a>.'},
            *crowded,
        ],
    }


# Photo viewer: a figure photo with a later step, a grid of a photo and a
# drawn SVG, a photo card and the pictures that never open (a linked image,
# one marked off, a formula), a video, a stepped video, an interactive page
# and a plain slide.
DRAWN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90" viewBox="0 0 160 90">'
    '<rect width="160" height="90"'
    ' fill="#334"/><circle cx="80" cy="45" r="30" fill="#fb4934"/></svg>'
)
PHOTO_DECK = {
    "deck": 1,
    "meta": {"title": "Photo deck", "section": "COURSE NAME"},
    "slides": [
        {"id": "ph-title", "type": "title", "title": "Photo deck", "claim": "No pictures."},
        {"id": "ph-figure", "title": "A photo", "claim": "Look at it.",
         "body": '<p data-step="1" id="ph-later">Then this.</p>', "source": "Source line",
         "figure": {"id": "ph-photo", "src": "assets/figure.png", "alt": "A photo",
                    "caption": "Caption"}},
        {"id": "ph-grid", "title": "A grid", "layout": "figures", "claim": "Two pictures.",
         "figures": [{"id": "ph-grid-photo", "src": "assets/figure.png", "alt": "Grid photo"},
                     {"id": "ph-drawn", "src": "assets/drawn.svg", "alt": "Drawn figure"}]},
        {"id": "ph-card", "title": "A photo card", "claim": "Authored HTML.",
         "body": '<figure class="photo-card"><img id="ph-card-photo" src="assets/figure.png"'
                 ' alt="Card photo"></figure><p>A <a href="#/0"><img id="ph-linked"'
                 ' src="assets/figure.png" width="40" alt="Linked"></a> link and '
                 '<span data-photo="off"><img id="ph-off" src="assets/figure.png" width="40"'
                 ' alt="Off"></span> one marked off.</p>'
                 '<p><img class="math-display" id="ph-math" src="assets/drawn.svg"'
                 ' alt="An image formula"></p><details><summary><img id="ph-summary"'
                 ' src="assets/figure.png" width="40" alt="Summary"></summary>Opened.</details>',
         "formula": {"mathml": "<math display='block'><mi>a</mi><mo>=</mo><mi>b</mi></math>"}},
        {"id": "ph-video", "title": "A video",
         "video": {"src": "assets/clip.webm", "type": "video/webm", "title": "Clip",
                   "caption": "A caption"}},
        {"id": "ph-video-step", "title": "A stepped video", "claim": "Then the clip.",
         "video": {"src": "assets/clip.webm", "type": "video/webm", "title": "Stepped clip",
                   "step": 1}},
        {"id": "ph-demo", "title": "A demo",
         "interactive": {"src": "assets/demo/index.html", "title": "Demo"}},
        {"id": "ph-end", "title": "The end", "claim": "Plain."},
    ],
}

# The viewer's state, values with their no-break spaces made plain.
PHOTO_STATE = """() => {
  const viewer = document.querySelector('#photo-viewer');
  const media = viewer.querySelector('.photo-media');
  const box = node => {
    const r = node.getBoundingClientRect();
    return {x: r.x, y: r.y, w: r.width, h: r.height};
  };
  const frame = document.querySelector('#deck .slide-frame');
  return {
    open: viewer.open,
    kind: viewer.dataset.kind || null,
    values: [...viewer.querySelectorAll('.photo-value')]
      .map(v => v.textContent.replace(/\\u00a0/g, ' ')),
    filter: media ? media.style.filter : null,
    media: media ? box(media) : null,
    stage: box(viewer.querySelector('.photo-stage')),
    hash: location.hash,
    index: Number(frame.dataset.index),
    hidden: [...frame.querySelectorAll('.step-hidden')]
      .map(n => n.id || n.dataset.figureId || n.tagName),
  };
}"""

# A MediaRecorder clip of a changing canvas: a real, seekable WebM once it is
# served with Range support, which `lecturedeck serve` does not offer.
RECORD_CLIP = """async () => {
  if (typeof MediaRecorder !== 'function') return null;
  if (!MediaRecorder.isTypeSupported('video/webm')) return null;
  const canvas = Object.assign(document.createElement('canvas'), {width: 320, height: 180});
  const paint = canvas.getContext('2d');
  const recorder = new MediaRecorder(canvas.captureStream(30), {mimeType: 'video/webm'});
  const parts = [];
  recorder.ondataavailable = event => parts.push(event.data);
  let frame = 0;
  const timer = setInterval(() => {
    paint.fillStyle = `hsl(${(frame += 9) % 360} 70% 50%)`;
    paint.fillRect(0, 0, 320, 180);
  }, 33);
  recorder.start();
  await new Promise(resolve => setTimeout(resolve, 3000));
  recorder.stop();
  clearInterval(timer);
  await new Promise(resolve => { recorder.onstop = resolve; });
  const bytes = new Uint8Array(await new Blob(parts).arrayBuffer());
  let text = '';
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text);
}"""


def ranged(body: bytes, content_type: str):
    """A route handler answering Range requests, so a browser can seek."""

    def fulfill(route):
        match = re.match(r"bytes=(\d+)-(\d*)", route.request.headers.get("range", ""))
        headers = {"Content-Type": content_type, "Accept-Ranges": "bytes"}
        if not match:
            route.fulfill(status=200, body=body, headers=headers)
            return
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else len(body) - 1
        headers["Content-Range"] = f"bytes {start}-{end}/{len(body)}"
        route.fulfill(status=206, body=body[start:end + 1], headers=headers)

    return fulfill


def marked_png(width: int, height: int, marks: list, background=(60, 60, 60)) -> bytes:
    """A flat picture with a coloured square centred on each (x, y, rgb)
    mark, x and y fractions of its width and height."""
    side = max(6, round(min(width, height) * 0.05))
    rows = [[background] * width for _ in range(height)]
    for fx, fy, rgb in marks:
        cx, cy = fx * width, fy * height
        for y in range(max(0, int(cy - side / 2)), min(height, int(cy + side / 2) + 1)):
            for x in range(max(0, int(cx - side / 2)), min(width, int(cx + side / 2) + 1)):
                rows[y][x] = rgb

    def chunk(kind: bytes, payload: bytes) -> bytes:
        data = kind + payload
        return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    body = zlib.compress(b"".join(b"\x00" + bytes(c for px in row for c in px) for row in rows))
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", body) + chunk(b"IEND", b"")
    )


# Photo hotspots: a 5:3 photo and a portrait one, each with coloured marks
# exactly where its hotspots are, so a screenshot proves a ring sits on its
# spot of the picture as the browser draws it.
PHOTO_MARKS = [(0.25, 0.5, (230, 40, 40)), (0.8, 0.3, (40, 200, 60)), (0.05, 0.92, (40, 80, 230))]
TALL_MARKS = [(0.5, 0.25, (40, 80, 230)), (0.3, 0.6, (40, 200, 60)), (0.85, 0.5, (230, 40, 40)),
              (0.5, 0.9, (240, 220, 40))]
HOTSPOTS = [
    {"x": 0.25, "y": 0.5, "r": 0.05, "label": "Left person",
     "html": "<strong>Left person</strong> (1858–1947)<br>Energy quanta, 1900."},
    {"x": 0.8, "y": 0.3, "r": 0.04, "label": "Right person",
     "html": "<p>Light quanta: <math><mi>E</mi><mo>=</mo><mi>h</mi><mi>ν</mi></math></p>"
             '<p><a id="hs-link" href="#/5">The end</a></p>'},
    {"x": 0.05, "y": 0.92, "r": 0.03, "label": "Corner person"},
]
TALL_HOTSPOTS = [{"x": x, "y": y, "r": 0.06, "label": f"Tall {n}"}
                 for n, (x, y, _) in enumerate(TALL_MARKS)]
HOTSPOT_DECK = {
    "deck": 1,
    "meta": {"title": "Hotspot deck", "section": "COURSE NAME"},
    "slides": [
        {"id": "hs-title", "type": "title", "title": "Hotspot deck", "claim": "No pictures."},
        {"id": "hs-figure", "title": "A group photo", "claim": "Who is who.",
         "source": "Source line",
         "figure": {"id": "hs-photo", "src": "assets/marked.png", "alt": "A group photo",
                    "caption": "Caption", "hotspots": HOTSPOTS}},
        {"id": "hs-tall", "title": "A letterboxed portrait",
         "claim": "Contain, max-height, shift and scale.",
         "figure": {"id": "hs-tall", "src": "assets/tall.png", "alt": "A portrait",
                    "shift": [14, -9], "scale": 0.9, "hotspots": TALL_HOTSPOTS}},
        {"id": "hs-cover", "title": "A cropped portrait", "claim": "Cover, padding, border.",
         "figure": {"id": "hs-cover", "src": "assets/tall.png", "alt": "A cropped portrait",
                    "hotspots": TALL_HOTSPOTS}},
        {"id": "hs-grid", "title": "A stepped photo", "layout": "figures", "claim": "Later.",
         "figures": [{"id": "hs-step", "src": "assets/marked.png", "alt": "Stepped photo",
                      "hotspots": HOTSPOTS[:2], "step": 1},
                     {"id": "hs-plain", "src": "assets/marked.png", "alt": "Plain photo"}]},
        {"id": "hs-end", "title": "The end", "claim": "Plain."},
    ],
}
HOTSPOT_CSS = (
    '.figure-card[data-figure-id="hs-tall"] img { width: 520px; max-height: 300px; }\n'
    '.figure-card[data-figure-id="hs-cover"] img { width: 400px; height: 200px;'
    " object-fit: cover; object-position: 30% 60%; padding: 6px; border: 3px solid #000; }\n"
)
HOTSPOTS_BY_FIGURE = {"hs-photo": HOTSPOTS, "hs-tall": TALL_HOTSPOTS, "hs-cover": TALL_HOTSPOTS,
                      "hs-step": HOTSPOTS[:2]}

# Each ring of the live slide (or of the viewer) against the picture as the
# browser draws it, computed here on its own: the image's content box in
# screen pixels, then object-fit and object-position.
HOTSPOT_GEOMETRY = """([spotsByFigure, inViewer]) => {
  const frame = document.querySelector('#deck .slide-frame');
  const k = frame.getBoundingClientRect().width / frame.offsetWidth;
  const measure = (img, spots, rings, ringScale, clip = null) => {
    const s = getComputedStyle(img);
    const box = img.getBoundingClientRect();
    const scale = box.width / img.offsetWidth;
    const edge = side => (parseFloat(s['border' + side + 'Width'])
      + parseFloat(s['padding' + side])) * scale;
    const content = {x: box.x + edge('Left'), y: box.y + edge('Top'),
      w: box.width - edge('Left') - edge('Right'), h: box.height - edge('Top') - edge('Bottom')};
    const nw = img.naturalWidth, nh = img.naturalHeight;
    const fit = s.objectFit === 'cover' ? Math.max(content.w / nw, content.h / nh)
      : s.objectFit === 'fill' ? null : Math.min(content.w / nw, content.h / nh);
    const drawn = fit === null ? {...content} : {w: nw * fit, h: nh * fit};
    if (fit !== null) {
      const [px, py] = s.objectPosition.split(' ').map(v => parseFloat(v) / 100);
      drawn.x = content.x + (content.w - drawn.w) * px;
      drawn.y = content.y + (content.h - drawn.h) * py;
    }
    return rings.map((ring, n) => {
      const r = ring.getBoundingClientRect();
      const spot = spots[n];
      const ex = drawn.x + spot.x * drawn.w, ey = drawn.y + spot.y * drawn.h;
      return {label: ring.getAttribute('aria-label'), cx: r.x + r.width / 2, cy: r.y + r.height / 2,
        w: r.width, h: r.height, ex, ey, ew: Math.max(18 * ringScale, 2 * spot.r * drawn.w),
        inside: ex > content.x && ex < content.x + content.w && ey > content.y
          && ey < content.y + content.h && (!clip || (ex > clip.left && ex < clip.right
            && ey > clip.top && ey < clip.bottom)),
        hit: document.elementFromPoint(ex, ey) === ring};
    });
  };
  if (inViewer) {
    // A zoomed photo runs past the stage, which shows only its middle.
    const img = document.querySelector('#photo-viewer .photo-media');
    const id = document.querySelector('#deck .figure-card.has-hotspots').dataset.figureId;
    return measure(img, spotsByFigure[id],
      [...document.querySelectorAll('#photo-viewer .hotspot-layer > .hotspot')], 1,
      document.querySelector('#photo-viewer .photo-stage').getBoundingClientRect());
  }
  return [...document.querySelectorAll('#deck .figure-card.has-hotspots')].flatMap(card =>
    measure(card.querySelector(':scope > img'), spotsByFigure[card.dataset.figureId],
      [...document.querySelectorAll(
        `#deck .hotspot-layer[data-figure-id="${card.dataset.figureId}"] > .hotspot`)], k));
}"""

# Pixels of a screenshot, read through a canvas.
SCREEN_PIXELS = """async ([data, points]) => {
  const image = new Image();
  image.src = 'data:image/png;base64,' + data;
  await image.decode();
  const canvas = Object.assign(document.createElement('canvas'),
    {width: image.width, height: image.height});
  const paint = canvas.getContext('2d');
  paint.drawImage(image, 0, 0);
  return points.map(([x, y]) => [...paint.getImageData(Math.floor(x), Math.floor(y), 1, 1).data]
    .slice(0, 3));
}"""

# The popup on screen, in the frame's or stage's own pixels.
HOTSPOT_POPUP = """(where) => {
  const popup = document.querySelector(where === 'viewer' ? '#hotspot-popup-viewer'
    : '#hotspot-popup-slide');
  if (!popup || popup.hidden || !popup.isConnected) return null;
  const host = popup.parentElement;
  const box = host.getBoundingClientRect();
  const k = box.width / parseFloat(getComputedStyle(host).width);
  const p = popup.getBoundingClientRect();
  const ring = document.querySelector('.hotspot.is-active');
  const r = ring.getBoundingClientRect();
  const style = getComputedStyle(popup);
  return {
    text: popup.textContent, html: popup.innerHTML, host: host.className,
    fontSize: parseFloat(style.fontSize), screenFont: parseFloat(style.fontSize) * k,
    background: style.backgroundColor, color: style.color,
    left: (p.left - box.left) / k, top: (p.top - box.top) / k,
    right: (p.right - box.left) / k, bottom: (p.bottom - box.top) / k,
    width: box.width / k, height: box.height / k,
    ring: {label: ring.getAttribute('aria-label'), left: (r.left - box.left) / k,
      top: (r.top - box.top) / k, right: (r.right - box.left) / k,
      bottom: (r.bottom - box.top) / k, describedBy: ring.getAttribute('aria-describedby'),
      opacity: getComputedStyle(ring).opacity},
    side: popup.dataset.side,
  };
}"""

RING_OPACITY = """(where) => [...document.querySelectorAll(
  where === 'viewer' ? '#photo-viewer .hotspot' : '#deck .hotspot')]
  .map(ring => getComputedStyle(ring).opacity)"""


def build_legacy_unit(unit: Path) -> None:
    webdeck = unit / "webdeck"
    assets = webdeck / "assets"
    assets.mkdir(parents=True)
    (assets / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<circle cx="8" cy="8" r="7" fill="#fb4934"/></svg>',
        encoding="utf-8",
    )
    (webdeck / "slides.js").write_text(
        "window.LECTUREDECK = {\n"
        '  meta: { title: "Legacy smoke", section: "SMOKE", opening: "OPENING", '
        'favicon: "assets/favicon.svg" },\n'
        '  slides: [\n'
        '    { type: "title", title: "Legacy smoke", claim: "Fallback slide." },\n'
        '    { title: "Legacy two", claim: "Second legacy slide." }\n'
        "  ]\n"
        "};\n",
        encoding="utf-8",
    )


def utc(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 1, 1, hour, minute, second, tzinfo=timezone.utc)


def epoch_ms(text: str) -> int:
    return round(datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp() * 1000)


def iso_ms(value: int) -> str:
    moment = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def visit_end(visit: dict) -> str:
    return iso_ms(epoch_ms(visit["startedAt"]) + visit["durationMs"])


def journal(page) -> list[dict]:
    """Every schema-2 journal entry in the page's localStorage, oldest first."""
    entries = page.evaluate(
        """() => Object.keys(localStorage)
          .filter(key => key.startsWith('lecturedeck-pacing2:'))
          .map(key => ({key, ...JSON.parse(localStorage.getItem(key))}))"""
    )
    return sorted(entries, key=lambda e: min(
        [v["startedAt"] for v in e["record"]["visits"]] or [e["record"]["window"]["from"]]
    ))


def set_visibility(page, state: str) -> None:
    page.evaluate(
        "state => { Object.defineProperty(document, 'visibilityState', "
        "{configurable: true, value: state}); "
        "document.dispatchEvent(new Event('visibilitychange')); }",
        state,
    )


def build_broken_unit(unit: Path) -> None:
    webdeck = unit / "webdeck"
    (webdeck / "assets").mkdir(parents=True)
    (webdeck / "deck.json").write_text('{"deck": 1, broken', encoding="utf-8")


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright is not installed")
class BrowserSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._root = tempfile.TemporaryDirectory()
        root = Path(cls._root.name)
        cls.servers = []
        cls.urls = {}
        for name, builder in (
            ("json", build_json_unit),
            ("legacy", build_legacy_unit),
            ("broken", build_broken_unit),
        ):
            unit = root / name
            unit.mkdir()
            builder(unit)
            server = make_server(unit, "127.0.0.1", 0, livereload=False)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cls.servers.append(server)
            cls.urls[name] = f"http://127.0.0.1:{server.server_address[1]}/webdeck/"
        selector = make_selector_server(root, "127.0.0.1", 0, livereload=False)
        threading.Thread(target=selector.serve_forever, daemon=True).start()
        cls.servers.append(selector)
        cls.selector_url = f"http://127.0.0.1:{selector.server_address[1]}/"
        original_cwd = Path.cwd()
        try:
            try:
                os.chdir(root)
                cls._playwright = sync_playwright().start()
                cls.browser = cls._playwright.chromium.launch()
            finally:
                os.chdir(original_cwd)
        except Exception as exc:  # browser binaries absent
            cls._playwright.stop()
            for server in cls.servers:
                server.shutdown()
                server.server_close()
            cls._root.cleanup()
            raise unittest.SkipTest(f"chromium is not installed ({exc})")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
            cls._playwright.stop()
            for server in cls.servers:
                server.shutdown()
                server.server_close()
            cls._root.cleanup()

    def open_deck(self, name: str, fragment: str = ""):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.goto(self.urls[name] + fragment)
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        return page

    def test_scheduled_clock_uses_wall_time_and_recovers_after_reload(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/presentation-time.json", lambda route: route.fulfill(
            json={"start": "09:00", "end": "10:30", "timeZone": "UTC"}
        ))
        page.clock.install(time=datetime(2026, 1, 1, 8, 59, tzinfo=timezone.utc))
        page.goto(self.urls["json"])
        clock = page.locator("#lecture-clock")
        clock.wait_for()
        self.assertEqual(clock.inner_text(), "08:59 · starts 09:00")
        page.clock.fast_forward(61 * 60 * 1000)
        self.assertEqual(clock.inner_text(), "10:00 · 30 min left")
        page.keyboard.press("ArrowRight")
        self.assertEqual(clock.inner_text(), "10:00 · 30 min left")
        page.reload()
        clock.wait_for()
        self.assertEqual(clock.inner_text(), "10:00 · 30 min left")
        page.clock.fast_forward(25 * 60 * 1000)
        self.assertEqual(clock.get_attribute("data-state"), "last-five")
        page.clock.fast_forward(5 * 60 * 1000)
        self.assertEqual(clock.inner_text(), "10:30 · time's up")
        page.clock.fast_forward(90 * 1000)
        self.assertEqual(clock.inner_text(), "10:31 · +2 min over")
        page.locator("#controls-toggle").click()
        page.locator("#clock-button").click()
        self.assertFalse(clock.is_visible())
        page.reload()
        page.wait_for_function("Boolean(document.querySelector('#lecture-clock'))")
        self.assertFalse(clock.is_visible())
        page.locator("#controls-toggle").click()
        page.locator("#clock-button").click()
        self.assertTrue(clock.is_visible())
        page.keyboard.press("o")
        self.assertFalse(clock.is_visible())
        page.keyboard.press("Escape")
        self.assertTrue(clock.is_visible())

    def test_clock_timezone_invalid_config_and_print(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        timing = {"start": "09:00", "end": "10:30", "timeZone": "Asia/Tokyo"}
        page.route("**/presentation-time.json", lambda route: route.fulfill(json=timing))
        page.clock.install(time=datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc))
        page.goto(self.urls["json"])
        clock = page.locator("#lecture-clock")
        clock.wait_for()
        self.assertEqual(clock.inner_text(), "09:15 · 75 min left")
        timing["timeZone"] = "invalid/timezone"
        page.reload()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.assertEqual(clock.count(), 0)
        timing["timeZone"] = "UTC"
        timing["end"] = "25:00"
        page.reload()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.assertEqual(clock.count(), 0)
        timing["end"] = "10:30"
        page.goto(self.urls["json"] + "?print=1")
        page.wait_for_function("Boolean(window.LECTUREDECK_PRINT_READY)")
        self.assertEqual(clock.count(), 0)

    def test_pacer_records_window_phases_and_pauses(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        timing = {"start": "09:00", "end": "09:01", "timeZone": "UTC",
                  "dates": ["2026-01-01"]}
        page.route("**/presentation-time.json", lambda route: route.fulfill(json=timing))
        page.clock.install(time=utc(8, 59, 50))
        page.clock.pause_at(utc(8, 59, 50))
        page.goto(self.urls["json"])
        page.wait_for_selector("#pacing-button")
        # Ten minutes before the slot is inside the recording window.
        self.assertEqual("true", page.get_attribute("#pacing-button", "data-recording"))
        page.clock.run_for(5000)
        page.keyboard.press("ArrowRight")
        page.clock.run_for(8000)  # crosses 09:00:00
        page.keyboard.press("o")
        page.clock.run_for(2000)
        page.keyboard.press("Escape")
        page.clock.run_for(2000)
        set_visibility(page, "hidden")
        page.clock.run_for(3000)
        self.assertEqual("false", page.get_attribute("#pacing-button", "data-recording"))
        set_visibility(page, "visible")
        page.clock.run_for(2000)
        page.locator("#controls-toggle").click()
        page.locator("#pacing-button").click()
        page.clock.run_for(3000)
        page.keyboard.press("Escape")
        page.wait_for_selector("#pacing-dialog", state="hidden")
        page.clock.run_for(50000)  # crosses 09:01:00
        entries = journal(page)
        self.assertEqual(1, len(entries))
        record = entries[0]["record"]
        self.assertEqual((2, "lecturedeck-pacing-segment"), (record["schema"], record["kind"]))
        self.assertEqual(
            {"before": 30, "after": 60, "from": "2026-01-01T08:30:00.000Z",
             "to": "2026-01-01T10:01:00.000Z"},
            record["window"],
        )
        self.assertEqual("2026-01-01T09:00:00.000Z", record["slot"]["startAt"])
        self.assertEqual("0859", record["opened"])
        self.assertEqual(
            {"s-title": {"number": 1, "label": "1", "title": "Smoke deck", "section": "Opening"},
             "s-a": {"number": 2, "label": "2", "title": "Statement A", "section": "Opening"}},
            record["slides"],
        )
        self.assertEqual(
            [("s-title", "08:59:50", 5000, "before"), ("s-a", "08:59:55", 5000, "before"),
             ("s-a", "09:00:00", 3000, "slot"), ("s-a", "09:00:05", 2000, "slot"),
             ("s-a", "09:00:10", 2000, "slot"), ("s-a", "09:00:15", 45000, "slot"),
             ("s-a", "09:01:00", 5000, "after")],
            [(v["slideId"], v["startedAt"][11:19], v["durationMs"], v["phase"])
             for v in record["visits"]],
        )
        self.assertEqual(
            [("09:00:03", 2000, "overview"), ("09:00:07", 3000, "hidden"),
             ("09:00:12", 3000, "report")],
            [(p["startedAt"][11:19], p["durationMs"], p["why"]) for p in record["pauses"]],
        )
        self.assertEqual(0, record["fullscreenMs"])
        page.locator("#pacing-button").click()
        with page.expect_download() as download:
            page.locator("#pacing-export").click()
        data = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        self.assertRegex(download.value.suggested_filename, r"^2026-01-01_\d{4}_.+_export\.json$")
        self.assertTrue(download.value.suggested_filename.startswith(
            f"2026-01-01_{data['segments'][0]['opened']}_"))
        self.assertEqual((2, "lecturedeck-pacing-export"), (data["schema"], data["kind"]))
        self.assertEqual([record["segment"]], [s["segment"] for s in data["segments"]])
        self.assertEqual(
            (10000, 52000, 5000),
            (data["summary"]["beforeMs"], data["summary"]["inSlotMs"], data["summary"]["afterMs"]),
        )
        self.assertEqual(3000, data["summary"]["pausedInSlotByReason"]["report"])
        page.keyboard.press("Escape")
        page.clock.pause_at(utc(10, 1, 0))
        page.clock.run_for(1000)
        self.assertEqual("false", page.get_attribute("#pacing-button", "data-recording"))

    def test_pacer_does_not_record_non_teaching_date(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/presentation-time.json", lambda route: route.fulfill(
            json={"start": "09:00", "end": "10:30", "timeZone": "UTC",
                  "dates": ["2026-01-02"]}
        ))
        page.clock.install(time=datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc))
        page.goto(self.urls["json"])
        page.wait_for_selector("#pacing-button")
        page.clock.run_for(5000)
        self.assertEqual(page.locator("#pacing-button").get_attribute("data-recording"), "false")
        page.locator("#controls-toggle").click()
        page.locator("#pacing-button").click()
        self.assertIn("No recorded lecture yet", page.locator("#pacing-dialog").inner_text())
        self.assertTrue(page.locator("#pacing-export").is_disabled())

    def current_index(self, page) -> int:
        return page.evaluate(
            "Number(document.querySelector('.slide-frame')?.dataset.index)"
        )

    def open_appendix_deck(self, fragment: str = ""):
        # Serve the appendix deck in place of the smoke deck's data, so the
        # selector and the other tests keep their own fixture unchanged.
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=APPENDIX_DECK))
        page.goto(self.urls["json"] + fragment)
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        return page

    def numbering_state(self, page) -> dict:
        return page.evaluate(
            """() => {
              const frame = document.querySelector('#deck .slide-frame');
              return {
                index: Number(frame.dataset.index),
                counter: document.querySelector('#counter').textContent,
                footer: frame.querySelector('.page-number')?.textContent ?? null,
                aria: frame.getAttribute('aria-label'),
                appendix: frame.getAttribute('data-appendix'),
                bodyClass: document.body.classList.contains('in-appendix'),
                hash: location.hash,
              };
            }"""
        )

    def overview_labels(self, page) -> list[str]:
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        labels = page.locator(".overview-label").all_inner_texts()
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")
        return labels

    def test_appendix_numbers_main_slides_and_labels_backup(self):
        page = self.open_appendix_deck()
        self.assertEqual(
            {"index": 0, "counter": "1 / 3", "footer": "1 / 3",
             "aria": "Slide 1 of 3: Appendix deck", "appendix": None,
             "bodyClass": False, "hash": "#/0"},
            self.numbering_state(page),
        )
        page.keyboard.press("End")
        self.assertEqual(
            {"index": 4, "counter": "B2 / 2", "footer": "B2 / 2",
             "aria": "Backup slide B2 of 2: Backup derivation", "appendix": "true",
             "bodyClass": True, "hash": "#/4"},
            self.numbering_state(page),
        )
        self.assertTrue(page.locator("#next-button").is_disabled())
        page.keyboard.press("ArrowLeft")
        state = self.numbering_state(page)
        self.assertEqual(
            ("B1 / 2", "B1 / 2", "#/3"), (state["counter"], state["footer"], state["hash"])
        )
        self.assertEqual("Backup slide B1 of 2: Backup", state["aria"])
        page.keyboard.press("ArrowLeft")
        state = self.numbering_state(page)
        self.assertEqual(("3 / 3", "3 / 3", None), (
            state["counter"], state["footer"], state["appendix"]))
        self.assertFalse(state["bodyClass"])
        page.keyboard.press("Home")
        self.assertEqual(0, self.current_index(page))
        self.assertEqual(
            ["1. Appendix deck", "2. Main two", "3. Main three", "B1. Backup",
             "B2. Backup derivation"],
            self.overview_labels(page),
        )
        # Deep links keep the raw zero-based index.
        deep = self.open_appendix_deck("#/3")
        self.assertEqual("B1 / 2", self.numbering_state(deep)["counter"])
        self.assertTrue(self.numbering_state(deep)["bodyClass"])

    def test_review_slides_read_h_and_leave_the_main_count(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=REVIEW_DECK))
        page.goto(self.urls["json"] + "#/2")
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        def state():
            return page.evaluate("""() => {
          const frame = document.querySelector('#deck .slide-frame');
          return {
            counter: document.querySelector('#counter').textContent,
            footer: frame.querySelector('.page-number').textContent,
            aria: frame.getAttribute('aria-label'),
            review: frame.getAttribute('data-review'),
            appendix: frame.getAttribute('data-appendix'),
            inReview: document.body.classList.contains('in-review'),
            hash: location.hash,
          };
        }""")
        self.assertEqual(
            {"counter": "H2 / 2", "footer": "H2 / 2", "aria": "Review slide H2 of 2: Solution",
             "review": "true", "appendix": None, "inReview": True, "hash": "#/2"},
            state(),
        )
        page.keyboard.press("ArrowRight")
        self.assertEqual(
            {"counter": "2 / 3", "footer": "2 / 3", "aria": "Slide 2 of 3: Part A",
             "review": None, "appendix": None, "inReview": False, "hash": "#/3"},
            state(),
        )
        page.keyboard.press("End")
        self.assertEqual(("B1 / 1", "true", False), (
            state()["counter"], state()["appendix"], state()["inReview"]))
        self.assertEqual(
            ["1. Review deck", "H1. Homework review", "H2. Solution", "2. Part A", "3. Idea",
             "B1. Backup"],
            self.overview_labels(page),
        )

    def test_pacer_labels_review_visits(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=REVIEW_DECK))
        page.route("**/presentation-time.json", lambda route: route.fulfill(
            json={"start": "09:00", "end": "10:00", "timeZone": "UTC",
                  "dates": ["2026-01-01"]}
        ))
        page.clock.install(time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc))
        page.goto(self.urls["json"] + "#/2")
        page.wait_for_selector("#pacing-button")
        page.clock.run_for(2000)
        page.keyboard.press("ArrowRight")
        page.clock.run_for(2000)
        (entry,) = journal(page)
        self.assertEqual(
            {"r-solution": {"number": 3, "label": "H2", "title": "Solution",
                            "section": "Homework review", "review": True},
             "r-part": {"number": 4, "label": "2", "title": "Part A", "section": "Part A"}},
            entry["record"]["slides"],
        )

    def test_appendix_labels_print_pages(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=APPENDIX_DECK))
        page.goto(self.urls["json"] + "?print=1")
        page.wait_for_function("window.LECTUREDECK_PRINT_READY === true")
        self.assertEqual(
            ["1 / 3", "2 / 3", "3 / 3", "B1 / 2", "B2 / 2"],
            page.locator("#deck .page-number").all_inner_texts(),
        )
        self.assertEqual(2, page.locator('#deck .slide-frame[data-appendix="true"]').count())

    def test_deck_without_appendix_keeps_plain_numbering(self):
        page = self.open_deck("json", "#/1")
        self.assertEqual(
            {"index": 1, "counter": "2 / 11", "footer": "2 / 11",
             "aria": "Slide 2: Statement A", "appendix": None,
             "bodyClass": False, "hash": "#/1"},
            self.numbering_state(page),
        )
        labels = self.overview_labels(page)
        self.assertEqual(11, len(labels))
        self.assertEqual("1. Smoke deck", labels[0])
        self.assertEqual("11. Aligned derivation", labels[-1])
        self.assertEqual(0, page.locator("[data-appendix]").count())
        self.assertNotIn("in-appendix", page.evaluate("document.body.className"))
        page.keyboard.press("End")
        state = self.numbering_state(page)
        self.assertEqual(("11 / 11", "11 / 11"), (state["counter"], state["footer"]))
        self.assertEqual("Slide 11: Aligned derivation", state["aria"])

    def test_pacer_labels_appendix_visits(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=APPENDIX_DECK))
        page.route("**/presentation-time.json", lambda route: route.fulfill(
            json={"start": "09:00", "end": "10:00", "timeZone": "UTC",
                  "dates": ["2026-01-01"]}
        ))
        page.clock.install(time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc))
        page.goto(self.urls["json"] + "#/2")
        page.wait_for_selector("#pacing-button")
        page.clock.run_for(2000)
        page.keyboard.press("ArrowRight")
        page.clock.run_for(2000)
        page.locator("#controls-toggle").click()
        page.locator("#pacing-button").click()
        rows = page.locator(
            ".pacing-slides tbody tr:not(.pacing-group) td:first-child"
        ).all_text_contents()
        self.assertEqual(["3", "B1"], rows)
        self.assertEqual(
            ["Opening", "Backup slides (B1)"],
            page.locator(".pacing-sections tbody th").all_text_contents(),
        )
        (entry,) = journal(page)
        record = entry["record"]
        self.assertEqual(["a-three", "a-backup"], [v["slideId"] for v in record["visits"]])
        self.assertEqual(
            {"a-three": {"number": 3, "label": "3", "title": "Main three", "section": "Opening"},
             "a-backup": {"number": 4, "label": "B1", "title": "Backup", "section": "Backup",
                          "backup": True}},
            record["slides"],
        )

    def test_selector_filters_and_opens_a_deck(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.goto(self.selector_url)
        self.assertEqual(3, page.locator("li[data-search]").count())
        self.assertTrue(page.locator(".topbar").is_visible())
        self.assertEqual(
            "sticky", page.locator(".topbar").evaluate("el => getComputedStyle(el).position")
        )
        self.assertEqual(1, page.locator("img.hero").count())
        rail_top = page.locator(".rail").evaluate("el => el.getBoundingClientRect().top")
        page.evaluate("scrollTo(0, 600)")
        self.assertAlmostEqual(
            rail_top,
            page.locator(".rail").evaluate("el => el.getBoundingClientRect().top"),
            delta=1,
        )
        self.assertEqual(
            0, page.locator(".topbar").evaluate("el => el.getBoundingClientRect().top")
        )
        page.evaluate("scrollTo(0, 0)")
        page.get_by_role("button", name=re.compile("Lectures")).click()
        self.assertEqual(3, page.locator("li[data-search]:visible").count())
        page.locator("#filter").fill("smoke deck")
        self.assertEqual(1, page.locator("li[data-search]:visible").count())
        page.get_by_role("link", name=re.compile("Smoke deck")).click()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.assertIn("/decks/json/webdeck/", page.url)
        self.assertIn("Smoke deck", page.title())
        selector_link = page.locator("#deck-selector-link")
        self.assertIsNone(selector_link.get_attribute("hidden"))
        self.assertEqual("Back to deck selector", selector_link.get_attribute("aria-label"))
        if page.locator("#controls-toggle").is_visible():
            page.locator("#controls-toggle").click()
        selector_link.click()
        page.wait_for_url(self.selector_url)
        self.assertEqual(3, page.locator("li[data-search]").count())

    def test_json_deck_loads_and_navigates(self):
        page = self.open_deck("json")
        self.assertIn("Smoke deck", page.title())
        self.assertEqual(11, page.evaluate("window.LECTUREDECK.slides.length"))
        self.assertEqual("s-title", page.evaluate(
            "document.querySelector('.slide-frame').dataset.slideId"
        ))
        page.keyboard.press("ArrowRight")
        self.assertEqual(1, self.current_index(page))
        page.keyboard.press("ArrowLeft")
        self.assertEqual(0, self.current_index(page))
        page.keyboard.press("End")
        self.assertEqual(10, self.current_index(page))
        page.keyboard.press("Home")
        self.assertEqual(0, self.current_index(page))
        self.assertEqual("1 / 11", page.text_content("#counter"))
        self.assertEqual(f"v{__version__}", page.text_content("#viewer-version"))

    def test_stable_tab_title_survives_navigation_and_reload(self):
        page = self.open_deck("json")
        self.assertEqual("Smoke deck · 1", page.title())
        page.keyboard.press("ArrowRight")
        self.assertEqual("Smoke deck · 1", page.title())
        page.reload()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.assertEqual("Smoke deck · 1", page.title())
        legacy = self.open_deck("legacy")
        self.assertNotEqual("Smoke deck · 1", legacy.title())

    def test_deck_favicon_sets_browser_identity(self):
        page = self.open_deck("json")
        href = page.get_attribute('link[rel~="icon"]', "href")
        self.assertTrue(href.startswith("data:image/svg+xml,%3Csvg"), href)
        self.assertIn("i%CE%B8", href)

        legacy = self.open_deck("legacy")
        self.assertEqual(
            "assets/favicon.svg",
            legacy.get_attribute('link[rel~="icon"]', "href"),
        )

    def test_print_mode_renders_one_pdf_page_per_slide(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 720})
        self.addCleanup(page.close)
        page.add_init_script(
            "localStorage.setItem('lecturedeck-presentation-style', 'gradient-title-rule')"
        )
        page.goto(self.urls["json"] + "?print=1&theme=light")
        page.wait_for_function("window.LECTUREDECK_PRINT_READY === true")
        self.assertEqual(11, page.locator("#deck > .slide-frame").count())
        self.assertTrue(page.evaluate("document.body.classList.contains('light-theme')"))
        self.assertEqual("default", page.evaluate("document.body.dataset.presentationStyle"))
        self.assertEqual(0, page.locator(".interactive-frame iframe").count())
        self.assertEqual(1, page.locator(".interactive-placeholder").count())
        page.emulate_media(media="print")
        payload = page.pdf(print_background=True, prefer_css_page_size=True)
        self.assertTrue(payload.startswith(b"%PDF-"))
        self.assertGreater(len(payload), 10_000)
        self.assertEqual(11, len(re.findall(rb"/Type\s*/Page\b", payload)))

    def test_print_pdf_links_jump_inside_the_document(self):
        deck = crowded_link_deck()
        page = self.browser.new_page(viewport={"width": 1280, "height": 720})
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=deck))
        page.goto(self.urls["json"] + "?print=1&theme=light")
        page.wait_for_function("window.LECTUREDECK_PRINT_READY === true")
        ids = page.locator("#deck > .slide-frame").evaluate_all("frames => frames.map(f => f.id)")
        self.assertEqual([f"slide-{i}" for i in range(len(deck["slides"]))], ids)
        hrefs = page.locator("#deck a").evaluate_all(
            "links => links.map(a => a.getAttribute('href'))"
        )
        crowded = len(deck["slides"]) - 1
        self.assertEqual(["#slide-2"] + ["#slide-0"] * crowded, hrefs)
        page.emulate_media(media="print")
        payload = page.pdf(print_background=True, prefer_css_page_size=True)
        self.assertEqual(len(deck["slides"]), len(re.findall(rb"/Type\s*/Page\b", payload)))
        # Every link survives as a named destination, each overfull page's
        # too; none is a dead URL back into the export's temporary server.
        self.assertEqual(
            [b"slide-0"] * crowded + [b"slide-2"],
            sorted(re.findall(rb"/Dest\s*/(slide-\d+)", payload)),
        )
        self.assertNotIn(b"127.0.0.1", payload)

    def test_declarative_figure_geometry_renders(self):
        page = self.open_deck("json", "#/2")
        transform = page.evaluate(
            "document.querySelector('.figure-card').style.transform"
        )
        self.assertEqual("translate(10px, -6px) scale(1.1)", transform)
        self.assertEqual("fig-1", page.evaluate(
            "document.querySelector('.figure-card').dataset.figureId"
        ))

    def test_legacy_deck_loads_via_fallback(self):
        page = self.open_deck("legacy")
        self.assertIn("Legacy smoke", page.title())
        self.assertTrue(page.evaluate(
            "Boolean(document.querySelector('script[src=\"slides.js\"]'))"
        ))
        page.keyboard.press("ArrowRight")
        self.assertEqual(1, self.current_index(page))

    def test_broken_deck_json_reports_error(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.goto(self.urls["broken"])
        page.wait_for_selector(".deck-error")
        self.assertIn("not valid JSON", page.text_content(".deck-error"))

    def test_slashless_webdeck_redirects(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.goto(self.urls["json"].rstrip("/"))
        self.assertTrue(page.url.endswith("/webdeck/"))

    def test_rapid_wheel_notches_page_one_slide_each(self):
        page = self.open_deck("json")
        page.mouse.move(400, 300)
        for _ in range(3):
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(90)
        self.assertEqual(3, self.current_index(page))

    def test_trackpad_glide_pages_once(self):
        page = self.open_deck("json")
        page.mouse.move(400, 300)
        for _ in range(10):
            page.mouse.wheel(0, 15)
        page.wait_for_timeout(120)
        self.assertEqual(1, self.current_index(page))

    def test_overview_open_click_close(self):
        page = self.open_deck("json")
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        self.assertEqual(11, page.locator(".overview-card").count())
        page.locator(".overview-card[data-index='5']").click()
        page.wait_for_function("document.querySelector('#overview').hidden")
        self.assertEqual(5, self.current_index(page))
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")

    def test_overview_jumps_preserve_history_without_paging_entries(self):
        page = self.open_deck("json")
        page.keyboard.press("ArrowRight")
        self.assertEqual(1, self.current_index(page))
        before = page.evaluate("history.length")
        page.keyboard.press("o")
        page.locator(".overview-card[data-index='5']").click()
        self.assertEqual(5, self.current_index(page))
        self.assertEqual(before + 1, page.evaluate("history.length"))
        page.keyboard.press("ArrowRight")
        self.assertEqual(6, self.current_index(page))
        self.assertEqual(before + 1, page.evaluate("history.length"))
        page.keyboard.press("o")
        page.locator(".overview-card[data-index='9']").click()
        page.reload()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.assertEqual(9, self.current_index(page))
        self.assertEqual("10 / 11", page.text_content("#counter"))
        page.go_back()
        page.wait_for_function("location.hash === '#/6'")
        self.assertEqual(6, self.current_index(page))
        page.go_back()
        page.wait_for_function("location.hash === '#/1'")
        self.assertEqual(1, self.current_index(page))
        page.go_forward()
        page.wait_for_function("location.hash === '#/6'")
        self.assertEqual(6, self.current_index(page))
        page.go_forward()
        page.wait_for_function("location.hash === '#/9'")
        self.assertEqual(9, self.current_index(page))
        before = page.evaluate("history.length")
        page.keyboard.press("o")
        page.locator(".overview-card[data-index='9']").click()
        self.assertEqual(before, page.evaluate("history.length"))
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))

    def test_laser_pointer_toggles_tracks_and_yields_to_overview(self):
        page = self.open_deck("json")
        page.keyboard.press("l")
        page.wait_for_selector(".laser-dot", state="attached")
        self.assertTrue(page.evaluate("document.body.classList.contains('laser-active')"))
        self.assertEqual("true", page.get_attribute("#laser-button", "aria-pressed"))
        # The arrow is hidden over the slide but kept on the controls.
        self.assertEqual(
            "none",
            page.evaluate("getComputedStyle(document.querySelector('.deck')).cursor"),
        )
        self.assertNotEqual(
            "none",
            page.evaluate("getComputedStyle(document.querySelector('#laser-button')).cursor"),
        )

        page.mouse.move(400, 300)
        page.wait_for_function("!document.querySelector('.laser-dot').hidden")
        centre = page.evaluate(
            "() => { const r = document.querySelector('.laser-dot').getBoundingClientRect();"
            " return {x: r.left + r.width / 2, y: r.top + r.height / 2}; }"
        )
        self.assertAlmostEqual(400, centre["x"], delta=2)
        self.assertAlmostEqual(300, centre["y"], delta=2)
        # The halo takes the accent of the slide being pointed at.
        halo = (
            "document.querySelector('.laser-dot').style"
            ".getPropertyValue('--laser-accent').trim()"
        )
        self.assertTrue(page.evaluate(halo))
        # And it is repainted on every slide change, so a laser left switched
        # on while paging does not keep the accent it was lit under. The
        # smoke deck's slides share one accent, so clear the property and
        # assert that navigating restores it.
        page.evaluate("document.querySelector('.laser-dot').style.removeProperty('--laser-accent')")
        self.assertEqual("", page.evaluate(halo))
        page.keyboard.press("ArrowRight")
        page.wait_for_function(f"{halo}.length > 0")

        # Opening the overview switches it off so the cards stay clickable.
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        self.assertFalse(page.evaluate("document.body.classList.contains('laser-active')"))
        self.assertTrue(page.evaluate("document.querySelector('.laser-dot').hidden"))
        self.assertEqual("false", page.get_attribute("#laser-button", "aria-pressed"))
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")

        # The control toggles it as well as the key. The strip is collapsed
        # behind the gear until it is expanded, and is inert until then.
        if page.locator("#controls-toggle").is_visible():
            page.locator("#controls-toggle").click()
        page.click("#laser-button")
        self.assertEqual("true", page.get_attribute("#laser-button", "aria-pressed"))
        page.click("#laser-button")
        self.assertEqual("false", page.get_attribute("#laser-button", "aria-pressed"))
        self.assertTrue(page.evaluate("document.querySelector('.laser-dot').hidden"))

    def test_fullscreen_toggles_and_exits(self):
        page = self.browser.new_page(viewport={"width": 1600, "height": 1000})
        self.addCleanup(page.close)
        page.goto(self.urls["json"] + "#/4")
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        windowed = page.locator(".slide-frame").bounding_box()
        self.assertIsNotNone(windowed)
        self.assertAlmostEqual(1600, windowed["width"], delta=1)
        self.assertAlmostEqual(900, windowed["height"], delta=1)
        self.assertAlmostEqual(50, windowed["y"], delta=1)

        page.keyboard.press("f")
        page.wait_for_function(
            "document.querySelector('#fullscreen-button').textContent === 'Exit full screen'"
        )
        page.wait_for_function(
            "() => Math.abs(document.querySelector('.slide-frame')"
            ".getBoundingClientRect().height - innerHeight) < 1"
        )
        fullscreen = page.locator(".slide-frame").bounding_box()
        self.assertIsNotNone(fullscreen)
        self.assertAlmostEqual(1600, fullscreen["width"], delta=1)
        self.assertAlmostEqual(1000, fullscreen["height"], delta=1)
        self.assertAlmostEqual(0, fullscreen["x"], delta=1)
        self.assertAlmostEqual(0, fullscreen["y"], delta=1)
        controls_toggle = page.locator("#controls-toggle")
        self.assertTrue(controls_toggle.is_visible())
        controls_box = controls_toggle.bounding_box()
        self.assertIsNotNone(controls_box)
        self.assertGreaterEqual(controls_box["x"], 0)
        self.assertLessEqual(controls_box["x"] + controls_box["width"], 1600)
        self.assertGreaterEqual(controls_box["y"], 0)
        self.assertLessEqual(controls_box["y"] + controls_box["height"], 1000)
        controls_toggle.click()
        self.assertEqual("true", controls_toggle.get_attribute("aria-expanded"))

        native = page.evaluate("Boolean(document.fullscreenElement)")
        page.keyboard.press("f")
        page.wait_for_function(
            "document.querySelector('#fullscreen-button').textContent === 'Full screen'"
        )
        page.wait_for_function(
            "() => Math.abs(document.querySelector('.slide-frame')"
            ".getBoundingClientRect().height - 900) < 1"
        )
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        if native:
            # Browser-reserved Escape exits native fullscreen and opens the overview.
            page.keyboard.press("f")
            page.wait_for_function("Boolean(document.fullscreenElement)")
            page.keyboard.press("Escape")
            page.wait_for_function("!document.querySelector('#overview').hidden")

    def test_footer_starts_after_the_gear_over_the_slide(self):
        # A 16:9 window (and full screen) leaves no room above or below the
        # slide, so the collapsed gear sits in its bottom-left corner. The
        # footer's source line starts after the gear, at any scale.
        page = self.browser.new_page(viewport={"width": 1280, "height": 720})
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=FOOTER_DECK))
        page.goto(self.urls["json"])
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        for width, height in ((1280, 720), (960, 540)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(200)
            gear = page.locator("#controls-toggle").bounding_box()
            source = page.locator(".slide-frame .slide-foot .source").bounding_box()
            self.assertIsNotNone(gear)
            self.assertIsNotNone(source)
            self.assertLess(gear["y"], source["y"] + source["height"])
            self.assertGreaterEqual(source["x"], gear["x"] + gear["width"])
        # With room below the slide the controls leave it, and the footer
        # keeps its own place.
        page.set_viewport_size({"width": 1280, "height": 900})
        page.wait_for_function(
            "getComputedStyle(document.querySelector('.slide-foot')).paddingLeft === '0px'"
        )

    def test_appearance_closes_on_a_click_outside(self):
        page = self.open_deck("json")
        page.keyboard.press("t")
        page.wait_for_selector("#appearance-dialog[open]")
        is_open = "document.querySelector('#appearance-dialog').open"
        box = page.locator("#appearance-dialog").bounding_box()
        self.assertIsNotNone(box)
        # A click inside keeps it open.
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + 12)
        self.assertTrue(page.evaluate(is_open))
        # So does a drag that starts inside and ends outside, as in selecting text.
        page.mouse.move(box["x"] + 30, box["y"] + 30)
        page.mouse.down()
        page.mouse.move(5, 5)
        page.mouse.up()
        self.assertTrue(page.evaluate(is_open))
        # A click on the backdrop closes it, as Escape does.
        page.mouse.click(5, 5)
        page.wait_for_selector("#appearance-dialog", state="hidden")
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))

    def test_appearance_selection_is_accessible_and_persists(self):
        page = self.open_deck("json")
        page.keyboard.press("t")
        page.wait_for_selector("#appearance-dialog[open]")
        page.get_by_label("Light", exact=True).check()
        page.get_by_label("Gradient and title rule", exact=True).check()
        self.assertTrue(page.evaluate("document.body.classList.contains('light-theme')"))
        self.assertEqual(
            "gradient-title-rule",
            page.evaluate("document.body.dataset.presentationStyle"),
        )
        page.keyboard.press("Escape")
        page.wait_for_selector("#appearance-dialog", state="hidden")
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        page.reload()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.assertTrue(page.evaluate("document.body.classList.contains('light-theme')"))
        self.assertEqual(
            "gradient-title-rule",
            page.evaluate("document.body.dataset.presentationStyle"),
        )
        page.keyboard.press("t")
        self.assertTrue(page.get_by_label("Light", exact=True).is_checked())
        self.assertTrue(page.get_by_label("Gradient and title rule", exact=True).is_checked())
        page.get_by_label("Dark", exact=True).check()
        page.get_by_label("Deck default", exact=True).check()
        self.assertFalse(page.evaluate("document.body.classList.contains('light-theme')"))
        self.assertEqual("default", page.evaluate("document.body.dataset.presentationStyle"))

    def test_video_fullscreen_exit_stays_on_slide(self):
        page = self.open_deck("json", "#/3")
        page.evaluate("""() => {
            const button = document.createElement('button');
            button.id = 'video-fullscreen-test';
            button.textContent = 'Fullscreen video';
            button.style.cssText = 'position:fixed;top:0;left:0;z-index:99999';
            button.onclick = () => document.querySelector('video').requestFullscreen();
            document.body.append(button);
        }""")
        page.click("#video-fullscreen-test")
        page.wait_for_function("document.fullscreenElement === document.querySelector('video')")
        # The native player's return-to-normal control calls this same browser API.
        page.evaluate("document.exitFullscreen()")
        page.wait_for_function("!document.fullscreenElement")
        page.evaluate(
            "() => new Promise(resolve => requestAnimationFrame("
            "() => requestAnimationFrame(resolve)))"
        )
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        self.assertEqual(3, self.current_index(page))

    def test_video_slide_attributes_and_key_guard(self):
        page = self.open_deck("json", "#/3")
        video = page.locator("video")
        self.assertEqual("metadata", video.get_attribute("preload"))
        self.assertIsNotNone(video.get_attribute("controls"))
        self.assertIn("poster.png", video.get_attribute("poster"))
        page.evaluate("document.querySelector('video').focus()")
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(80)
        self.assertEqual(3, self.current_index(page))

        stage_box = page.locator(".layout-video").bounding_box()
        video_box = video.bounding_box()
        self.assertIsNotNone(stage_box)
        self.assertIsNotNone(video_box)
        self.assertLess(video_box["width"], stage_box["width"])
        self.assertAlmostEqual(
            video_box["x"] + video_box["width"] / 2,
            stage_box["x"] + stage_box["width"] / 2,
            delta=1,
        )

    def test_laser_tracks_over_an_interactive_frame(self):
        # An embedded animation is its own document and keeps the mouse to
        # itself, so the laser froze at its edge (owner report, 2026-10-14).
        page = self.open_deck("json", "#/4")
        frame = page.wait_for_selector(".interactive-frame iframe")
        box = frame.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.keyboard.press("l")
        page.mouse.move(x - 40, y - 30)
        page.mouse.move(x, y)
        page.wait_for_function(
            "(p) => { const d = document.querySelector('.laser-dot');"
            " if (d.hidden) return false; const r = d.getBoundingClientRect();"
            " return Math.abs(r.left + r.width / 2 - p.x) < 2"
            " && Math.abs(r.top + r.height / 2 - p.y) < 2; }",
            arg={"x": x, "y": y},
        )
        # Switching the laser off gives the animation its mouse back.
        page.keyboard.press("l")
        self.assertEqual("auto", frame.evaluate("f => getComputedStyle(f).pointerEvents"))

    def test_interactive_iframe_pointer_navigates(self):
        page = self.open_deck("json", "#/4")
        page.wait_for_selector(".interactive-frame iframe")
        self.assertTrue(page.evaluate(
            "document.body.classList.contains('immersive-slide')"
        ))
        page.frame_locator(".interactive-frame iframe").locator("#next").click()
        page.wait_for_function(
            "Number(document.querySelector('.slide-frame')?.dataset.index) === 5"
        )

    def test_touch_swipe_navigates(self):
        page = self.open_deck("json")
        page.evaluate(
            """() => {
              const touch = x => new Touch({identifier: 1, target: document.body,
                clientX: x, clientY: 300});
              dispatchEvent(new TouchEvent("touchstart",
                {changedTouches: [touch(500)], bubbles: true}));
              dispatchEvent(new TouchEvent("touchend",
                {changedTouches: [touch(380)], bubbles: true}));
            }"""
        )
        self.assertEqual(1, self.current_index(page))

    def swipe(self, page, start, end, target=".slide-frame", multi=False, cancel=False):
        page.evaluate(
            """({start, end, target, multi, cancel}) => {
              const element = document.querySelector(target);
              const finger = (point, id = 1) => new Touch({identifier: id,
                target: element, clientX: point[0], clientY: point[1]});
              const first = finger(start);
              element.dispatchEvent(new TouchEvent("touchstart", {
                touches: multi ? [first, finger(start, 2)] : [first],
                changedTouches: [first], bubbles: true,
              }));
              element.dispatchEvent(new TouchEvent(cancel ? "touchcancel" : "touchend", {
                touches: [], changedTouches: [finger(end)], bubbles: true,
              }));
            }""",
            dict(start=start, end=end, target=target, multi=multi, cancel=cancel),
        )

    def test_mobile_gear_overview_and_controls_fit(self):
        for width, height in [(320, 480), (390, 844), (844, 390)]:
            with self.subTest(width=width, height=height):
                page = self.open_deck("json")
                page.set_viewport_size(dict(width=width, height=height))
                gear = page.locator("#mobile-menu-button")
                gear.wait_for(state="visible")
                self.assertTrue(page.locator("#touch-nav").is_hidden())
                gear.click()
                for selector in ["#touch-overview-button", "#previous-button",
                                 "#next-button", "#touch-fullscreen-button",
                                 "#touch-controls-button", "#appearance-button", "#laser-button"]:
                    button = page.locator(selector)
                    self.assertTrue(button.is_visible(), selector)
                    box = button.bounding_box()
                    self.assertGreaterEqual(box["x"], 0, selector)
                    self.assertLessEqual(box["x"] + box["width"], width + 1, selector)
                    self.assertGreaterEqual(box["y"], 0, selector)
                    self.assertLessEqual(box["y"] + box["height"], height + 1, selector)
                    self.assertGreaterEqual(box["width"], 44, selector)
                    self.assertGreaterEqual(box["height"], 44, selector)
                page.locator("#next-button").click()
                self.assertEqual(1, self.current_index(page))
                page.locator("#touch-overview-button").click()
                self.assertEqual(11, page.locator(".overview-card").count())
                self.assertTrue(page.locator("#touch-controls-button").is_hidden())
                self.assertEqual(
                    "Close overview", page.locator("#touch-overview-button").inner_text()
                )
                self.swipe(page, [200, 300], [60, 300], "#overview")
                self.assertEqual(1, self.current_index(page))
                page.locator("#overview").evaluate("e => {e.scrollTop = e.scrollHeight}")
                self.assertTrue(page.locator("#touch-overview-button").is_visible())
                page.locator("#touch-overview-button").click()
                self.assertEqual(1, self.current_index(page))
                self.assertTrue(page.locator("#touch-nav").is_hidden())
                gear.click()
                page.locator("#touch-overview-button").click()
                page.locator(".overview-card[data-index='5']").click()
                self.assertEqual(5, self.current_index(page))
                page.reload()
                page.wait_for_function("Boolean(window.LECTUREDECK)")
                gear.wait_for(state="visible")
                self.assertEqual(5, self.current_index(page))
                self.assertTrue(page.locator("#touch-nav").is_hidden())

    def test_mobile_swipes_menu_and_protected_gestures(self):
        page = self.open_deck("json")
        page.set_viewport_size(dict(width=390, height=844))
        page.locator("#mobile-menu-button").wait_for(state="visible")
        self.swipe(page, [200, 500], [210, 350])
        self.assertTrue(page.locator("#touch-nav").is_visible())
        self.assertEqual(0, self.current_index(page))
        self.swipe(page, [200, 350], [210, 500])
        self.assertTrue(page.locator("#touch-nav").is_hidden())
        self.swipe(page, [300, 400], [100, 410])
        self.assertEqual(1, self.current_index(page))
        self.swipe(page, [100, 400], [300, 410])
        self.assertEqual(0, self.current_index(page))
        for options in [dict(multi=True), dict(cancel=True)]:
            self.swipe(page, [300, 400], [100, 400], **options)
            self.assertEqual(0, self.current_index(page))
        page.locator("#mobile-menu-button").click()
        self.swipe(page, [300, 400], [100, 400], "#touch-overview-button")
        self.assertEqual(0, self.current_index(page))
        page.locator("#appearance-button").click()
        self.swipe(page, [300, 400], [100, 400], "#appearance-dialog")
        self.assertEqual(0, self.current_index(page))
        page.locator("#appearance-close").click()
        page.locator("#touch-controls-button").click()
        page.keyboard.press("End")
        self.swipe(page, [200, 500], [200, 350])
        self.assertTrue(page.locator("#next-button").is_disabled())

    def test_mobile_fullscreen_fallback_and_immersive_menu(self):
        page = self.open_deck("json", "#/4")
        page.set_viewport_size(dict(width=390, height=844))
        page.locator("#mobile-menu-button").wait_for(state="visible")
        self.assertTrue(page.locator("#touch-nav").is_hidden())
        page.evaluate("() => { document.documentElement.requestFullscreen = () => "
                      "Promise.reject(new Error('unavailable')); }")
        page.locator("#mobile-menu-button").click()
        page.locator("#touch-fullscreen-button").click()
        page.wait_for_function("document.body.classList.contains('pseudo-fullscreen')")
        self.assertTrue(page.locator("#touch-nav").is_hidden())
        page.locator("#mobile-menu-button").click()
        self.assertEqual("Exit full screen", page.locator("#touch-fullscreen-button").inner_text())
        page.locator("#touch-fullscreen-button").click()
        self.assertFalse(page.evaluate("document.body.classList.contains('pseudo-fullscreen')"))
        self.assertEqual(4, self.current_index(page))
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))

    def test_oversized_formula_shrinks_to_fit(self):
        page = self.open_deck("json", "#/9")
        page.wait_for_selector(".formula-math math")
        fitted = page.evaluate(
            """() => {
              const formula = document.querySelector('.formula');
              const math = formula.querySelector('.formula-math math');
              return {
                fontSize: parseFloat(getComputedStyle(formula).fontSize),
                inkWidth: math.scrollWidth,
                boxWidth: math.clientWidth,
              };
            }"""
        )
        self.assertLessEqual(fitted["inkWidth"], fitted["boxWidth"] + 2, fitted)
        self.assertLess(fitted["fontSize"], 72)

    def test_fitting_formula_keeps_stylesheet_size(self):
        page = self.open_deck("json", "#/8")
        page.wait_for_selector(".formula-math math")
        self.assertEqual(72, page.evaluate(
            "parseFloat(getComputedStyle(document.querySelector('.formula')).fontSize)"
        ))

    def test_formula_is_centred_and_author_labels_are_respected(self):
        page = self.open_deck("json", "#/8")
        for height in (700, 1000):
            page.set_viewport_size({"width": 1280, "height": height})
            page.wait_for_selector(".formula-math math")
            offset = page.evaluate("""() => {
                const math = document.querySelector('.formula math');
                const tokens = [...math.querySelectorAll('mi')];
                const first = tokens[0].getBoundingClientRect();
                const last = tokens.at(-1).getBoundingClientRect();
                const box = math.getBoundingClientRect();
                return (first.left + last.right - box.left - box.right) / 2;
            }""")
            self.assertLess(abs(offset), 2)
            self.assertEqual("PRACTICE", page.locator(".slide-head .eyebrow").inner_text())
            self.assertNotIn("INTERNAL-S14", page.locator("body").inner_text())
        page.goto(self.urls["json"] + "#/1")
        self.assertEqual("OPENING", page.locator(".slide-head .eyebrow").inner_text())

    def test_derivation_rows_align_on_the_relation_column(self):
        page = self.open_deck("json", "#/10")
        page.wait_for_selector(".formula-math mtable")
        lefts = page.evaluate(
            """() => [...document.querySelectorAll('.formula-math mtr')]
              .map(row => row.querySelector('mtd:last-child mo'))
              .filter(Boolean)
              .map(mo => mo.getBoundingClientRect().left)"""
        )
        self.assertEqual(2, len(lefts))
        self.assertLess(abs(lefts[0] - lefts[1]), 6, lefts)

    def test_legacy_span_controls_do_not_duplicate_or_oscillate(self):
        page = self.open_deck("json")
        page.add_style_tag(content=".deck-chrome span { border:1px solid gray; padding:7px 10px; }")
        page.set_viewport_size({"width": 1280, "height": 720})
        toggle = page.locator("#controls-toggle")
        heights = {"true": [], "false": []}
        for _ in range(20):
            toggle.click()
            state = toggle.get_attribute("aria-expanded")
            height = page.locator("#presentation-controls").evaluate("e => e.offsetHeight")
            heights[state].append(height)
            self.assertEqual(1, toggle.count())
            border = toggle.locator("span").evaluate("e => getComputedStyle(e).borderWidth")
            self.assertEqual("0px", border)
        for values in heights.values():
            self.assertEqual(1, len(set(values)))
        # Near the expanded-height boundary, repeated layout must agree.
        page.set_viewport_size({"width": 1280, "height": 830})
        classes = []
        for _ in range(6):
            page.evaluate("dispatchEvent(new Event('resize'))")
            classes.append(page.locator("#presentation-controls").get_attribute("class"))
        self.assertEqual(1, len(set(classes)))
        if toggle.is_visible():
            toggle.click()
            self.assertEqual("true", toggle.get_attribute("aria-expanded"))
        else:
            self.assertTrue(page.locator("#overview-button").is_visible())

    def test_controls_strip_is_single_row_and_stable(self):
        page = self.browser.new_page(viewport={"width": 1280, "height": 760})
        self.addCleanup(page.close)
        page.goto(self.urls["json"])
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        page.wait_for_selector(".slide-frame")

        def strip():
            return page.evaluate(
                "() => { const r = document.querySelector('#presentation-controls')"
                ".getBoundingClientRect();"
                " return {left: Math.round(r.left), top: Math.round(r.top),"
                " height: Math.round(r.height)}; }"
            )

        first = strip()
        self.assertGreaterEqual(first["left"], 24, first)
        self.assertLessEqual(first["height"], 40, first)
        self.assertEqual("⚙️", page.text_content("#controls-toggle").strip())
        self.assertEqual(
            "Show presentation controls",
            page.get_attribute("#controls-toggle", "aria-label"),
        )
        self.assertTrue(page.locator("#deck-selector-link").is_hidden())
        page.click("#controls-toggle")
        page.wait_for_timeout(250)
        self.assertEqual(
            "Hide presentation controls",
            page.get_attribute("#controls-toggle", "aria-label"),
        )
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(100)
        page.click("#controls-toggle")
        page.wait_for_timeout(250)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(100)
        last = strip()
        self.assertEqual(first["top"], last["top"])
        self.assertLessEqual(last["height"], 40, last)
        self.assertLessEqual(last["top"] + last["height"], 760)

    def test_adjust_hud_nudges_without_paging(self):
        page = self.open_deck("json", "#/2")
        page.keyboard.press("g")
        page.wait_for_selector(".lecturedeck-adjust-hud:not([hidden])")
        page.keyboard.press("ArrowRight")
        self.assertEqual(2, self.current_index(page))
        self.assertIn("shift: [12, -6]", page.text_content(".lecturedeck-adjust-hud code"))
        page.keyboard.press("Escape")
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        page.wait_for_selector(".lecturedeck-adjust-hud", state="hidden")

    def test_adjust_hud_stays_off_the_overview(self):
        page = self.open_deck("json", "#/2")
        page.keyboard.press("g")
        page.wait_for_selector(".lecturedeck-adjust-hud:not([hidden])")
        page.keyboard.press("o")
        page.wait_for_selector(".lecturedeck-adjust-hud", state="hidden")
        page.keyboard.press("g")
        self.assertTrue(page.evaluate(
            "document.querySelector('.lecturedeck-adjust-hud').hidden"
        ))
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")

    # Step-by-step reveals ------------------------------------------------

    def open_steps_deck(self, fragment: str = "", **context):
        # The smoke unit's assets (figure, demo, clip) under a stepped deck.
        page = self.browser.new_page(**context)
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=STEPS_DECK))
        page.goto(self.urls["json"] + fragment)
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        return page

    def steps(self, page) -> dict:
        return page.evaluate(STEP_STATE)

    def box(self, page, selector: str) -> dict:
        return page.evaluate(
            "s => { const r = document.querySelector(s).getBoundingClientRect();"
            " return {x: r.x, y: r.y, w: r.width, h: r.height}; }",
            selector,
        )

    def test_steps_reveal_on_next_and_hide_on_previous(self):
        page = self.open_steps_deck("#/1")
        state = self.steps(page)
        self.assertEqual(
            {"index": 1, "hash": "#/1", "hidden": ["st-one", "st-two-a", "st-two-b"],
             "current": [], "counter": "2 / 6", "dots": "○○"},
            state,
        )
        late = self.box(page, "#st-two-b")
        self.assertEqual("hidden", page.evaluate(
            "getComputedStyle(document.querySelector('#st-one')).visibility"))
        self.assertEqual("true", page.get_attribute("#st-one", "aria-hidden"))
        self.assertIsNotNone(page.get_attribute("#st-one", "inert"))
        # A hidden step's link cannot take focus.
        focused = "s => { document.querySelector(s).focus(); return document.activeElement.id; }"
        self.assertNotEqual("st-link", page.evaluate(focused, "#st-link"))
        self.assertEqual(
            ["2", "0", "0"],
            page.evaluate("(({stepCount, stepShown, stepCurrent}) => [stepCount, stepShown,"
                          " stepCurrent])(document.querySelector('.slide-frame').dataset)"),
        )

        page.keyboard.press("ArrowRight")
        state = self.steps(page)
        self.assertEqual((1, "#/1.1", ["st-two-a", "st-two-b"], ["st-one"], "●○"), (
            state["index"], state["hash"], state["hidden"], state["current"], state["dots"]))
        self.assertIsNone(page.get_attribute("#st-one", "aria-hidden"))
        self.assertIsNone(page.get_attribute("#st-one", "inert"))
        page.wait_for_function(
            "getComputedStyle(document.querySelector('#st-one')).opacity === '1'")
        # Elements sharing a number appear together.
        page.keyboard.press(" ")
        state = self.steps(page)
        self.assertEqual(("#/1.2", [], ["st-two-a", "st-two-b"], "●●", "2 / 6"), (
            state["hash"], state["hidden"], state["current"], state["dots"], state["counter"]))
        self.assertEqual(late, self.box(page, "#st-two-b"))  # nothing reflowed
        self.assertEqual("st-link", page.evaluate(focused, "#st-link"))
        page.evaluate("document.activeElement.blur()")

        # A fully shown slide advances; the next one arrives bare.
        page.keyboard.press("PageDown")
        state = self.steps(page)
        self.assertEqual((2, "#/2", ["st-claim", "fig-step"], "3 / 6"), (
            state["index"], state["hash"], state["hidden"], state["counter"]))
        # Previous on a bare slide goes back, and arrives fully revealed.
        page.keyboard.press("ArrowLeft")
        state = self.steps(page)
        self.assertEqual((1, "#/1.2", []), (state["index"], state["hash"], state["hidden"]))
        page.keyboard.press("PageUp")
        self.assertEqual("#/1.1", self.steps(page)["hash"])
        page.locator("#previous-button").evaluate("button => button.click()")
        state = self.steps(page)
        self.assertEqual(("#/1", 3), (state["hash"], len(state["hidden"])))
        page.keyboard.press("ArrowUp")
        state = self.steps(page)
        self.assertEqual((0, "#/0", None), (state["index"], state["hash"], state["dots"]))

        # The Next control, a wheel notch and a swipe step too.
        page.keyboard.press("ArrowDown")
        page.locator("#next-button").evaluate("button => button.click()")
        self.assertEqual("#/1.1", self.steps(page)["hash"])
        page.mouse.move(400, 300)
        page.mouse.wheel(0, 120)
        page.wait_for_timeout(90)
        self.assertEqual("#/1.2", self.steps(page)["hash"])
        self.swipe(page, [500, 300], [380, 300])
        self.assertEqual("#/2", self.steps(page)["hash"])
        self.swipe(page, [380, 300], [500, 300])
        self.assertEqual("#/1.2", self.steps(page)["hash"])

    def test_step_deep_links_reload_and_hash_changes(self):
        # A plain #/N deep link opens the slide with none of its steps shown.
        bare = self.open_steps_deck("#/1")
        self.assertEqual(3, len(self.steps(bare)["hidden"]))
        page = self.open_steps_deck("#/1.1")
        self.assertEqual(["st-two-a", "st-two-b"], self.steps(page)["hidden"])
        # A step beyond the last one shows the whole slide, named exactly.
        page = self.open_steps_deck("#/1.9")
        state = self.steps(page)
        self.assertEqual(("#/1.2", []), (state["hash"], state["hidden"]))
        page.reload()  # live reload reloads the same way
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        state = self.steps(page)
        self.assertEqual(("#/1.2", []), (state["hash"], state["hidden"]))
        page.evaluate("location.hash = '#/2.1'")
        page.wait_for_function("location.hash === '#/2.1' && "
                               "document.querySelector('.slide-frame').dataset.index === '2'")
        self.assertEqual(["fig-step"], self.steps(page)["hidden"])
        page.evaluate("location.hash = '#/2'")  # same slide, back to its first state
        page.wait_for_function("document.querySelectorAll('.step-hidden').length === 2")
        # An in-deck link to #/N.k jumps there.
        page.keyboard.press("Home")
        page.click("#st-jump")
        page.wait_for_function("location.hash === '#/1.2'")
        self.assertEqual([], self.steps(page)["hidden"])

    def test_figure_card_and_video_steps_come_from_step_fields(self):
        page = self.open_steps_deck("#/2")
        figure = page.locator(".figure-card")
        self.assertEqual(("2", "fig-step"), (
            figure.get_attribute("data-step"), figure.get_attribute("data-figure-id")))
        before = self.box(page, ".figure-card")
        page.keyboard.press("ArrowRight")
        self.assertEqual(["fig-step"], self.steps(page)["hidden"])
        page.keyboard.press("ArrowRight")
        state = self.steps(page)
        self.assertEqual(([], ["fig-step"]), (state["hidden"], state["current"]))
        self.assertEqual(before, self.box(page, ".figure-card"))

        page.keyboard.press("ArrowRight")
        state = self.steps(page)
        self.assertEqual((3, ["One", "Two"]), (state["index"], state["hidden"]))
        self.assertIsNone(page.locator(".concept-card").first.get_attribute("data-step"))
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        self.assertEqual(["Two"], self.steps(page)["current"])

        # A video stepped back out of view stops playing.
        video = self.open_steps_deck("#/5")
        video.evaluate("""() => { window.__paused = 0;
          HTMLMediaElement.prototype.pause = function () { window.__paused += 1; }; }""")
        card, caption = video.locator(".video-card"), video.locator(".video-card > figcaption")
        self.assertEqual("1", card.get_attribute("data-step"))
        self.assertIsNotNone(card.get_attribute("inert"))
        # A step that is a caption's whole content takes the caption box with
        # it, so no empty bar waits on screen.
        self.assertEqual(("2", "step-hidden"), (
            caption.get_attribute("data-step"), caption.get_attribute("class")))
        video.keyboard.press("ArrowRight")
        self.assertIsNone(card.get_attribute("inert"))
        self.assertEqual("hidden", caption.evaluate("c => getComputedStyle(c).visibility"))
        video.keyboard.press("ArrowRight")
        video.wait_for_function("getComputedStyle(document.querySelector("
                                "'.video-card > figcaption')).opacity === '1'")
        video.keyboard.press("ArrowLeft")
        video.keyboard.press("ArrowLeft")
        self.assertGreaterEqual(video.evaluate("window.__paused"), 1)
        self.assertEqual((5, "#/5"), (self.steps(video)["index"], self.steps(video)["hash"]))
        # Only the live slide lends a step to its box; overview thumbnails never.
        video.keyboard.press("o")
        video.wait_for_selector(".overview-card")
        self.assertEqual(0, video.locator("#overview figcaption[data-step]").count())

    def test_interactive_navigate_messages_step_first(self):
        page = self.open_steps_deck("#/4")
        page.wait_for_selector(".interactive-frame iframe")
        demo = page.frame_locator(".interactive-frame iframe")
        demo.locator("#next").click()
        page.wait_for_function("location.hash === '#/4.1'")
        self.assertEqual([], self.steps(page)["hidden"])
        demo.locator("#next").click()
        page.wait_for_function("location.hash === '#/5'")
        page.evaluate("location.hash = '#/4.1'")
        page.wait_for_function("document.querySelector('.slide-frame').dataset.index === '4'")
        page.wait_for_selector(".interactive-frame iframe")
        frame = next(f for f in page.frames if f.url.endswith("/assets/demo/index.html"))
        frame.wait_for_load_state()
        back = "parent.postMessage({type: 'lecturedeck:navigate', direction: -1}, '*')"
        frame.evaluate(back)
        page.wait_for_function("location.hash === '#/4'")
        frame.evaluate(back)
        page.wait_for_function("location.hash === '#/3.2'")

    def test_overview_print_and_dialogs_show_every_step(self):
        page = self.open_steps_deck("#/1")
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        self.assertGreater(page.locator("#overview [data-step]").count(), 0)
        self.assertEqual(0, page.locator("#overview .step-hidden").count())
        self.assertEqual(
            [], page.locator("#overview [data-step]").evaluate_all(
                "nodes => nodes.filter(n => getComputedStyle(n).visibility !== 'visible'"
                " || n.hasAttribute('inert') || n.hasAttribute('aria-hidden')).map(n => n.id)"),
        )
        # Closing the overview returns to the step the slide was left on.
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")
        state = self.steps(page)
        self.assertEqual(("#/1", 3), (state["hash"], len(state["hidden"])))
        page.keyboard.press("ArrowRight")
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")
        self.assertEqual("#/1.1", self.steps(page)["hash"])
        # A jump from the overview opens another slide bare.
        page.keyboard.press("o")
        page.locator(".overview-card[data-index='2']").click()
        state = self.steps(page)
        self.assertEqual(("#/2", 2), (state["hash"], len(state["hidden"])))
        # The Appearance dialog leaves the slide's steps as they were.
        page.keyboard.press("ArrowRight")
        page.keyboard.press("t")
        page.wait_for_selector("#appearance-dialog[open]")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Escape")
        page.wait_for_selector("#appearance-dialog", state="hidden")
        self.assertEqual("#/2.1", self.steps(page)["hash"])
        # Printing a live page never drops a hidden step.
        page.emulate_media(media="print")
        self.assertEqual("visible", page.evaluate(
            "getComputedStyle(document.querySelector('.figure-card')).visibility"))
        page.emulate_media(media="screen")

        printed = self.browser.new_page(viewport={"width": 1280, "height": 720})
        self.addCleanup(printed.close)
        printed.route("**/deck.json", lambda route: route.fulfill(json=STEPS_DECK))
        printed.goto(self.urls["json"] + "?print=1#/1.1")
        printed.wait_for_function("window.LECTUREDECK_PRINT_READY === true")
        self.assertEqual(7, printed.locator("#deck > .slide-frame").count())
        self.assertEqual(0, printed.locator(
            "#deck .step-hidden, #deck [inert], #deck [aria-hidden='true']").count())
        self.assertEqual(
            [], printed.locator("#deck [data-step]").evaluate_all(
                "nodes => nodes.filter(n => getComputedStyle(n).visibility !== 'visible'"
                " || getComputedStyle(n).opacity !== '1').map(n => n.id)"),
        )
        self.assertEqual("#slide-1", printed.get_attribute("#st-jump", "href"))

    def test_reduced_motion_drops_the_step_fade(self):
        duration = (
            "s => getComputedStyle(document.querySelector(s)).transitionDuration"
            ".split(',').map(d => parseFloat(d))"
        )
        page = self.open_steps_deck("#/1")
        self.assertGreater(max(page.evaluate(duration, "#st-one")), 0)
        # Arriving at a slide sets its hidden steps at once, with no fade.
        page.keyboard.press("Home")
        page.keyboard.press("ArrowRight")
        self.assertEqual("0", page.evaluate(
            "getComputedStyle(document.querySelector('#st-one')).opacity"))
        still = self.open_steps_deck("#/1", reduced_motion="reduce")
        self.assertEqual(0, max(still.evaluate(duration, "#st-one")))
        still.keyboard.press("ArrowRight")
        self.assertEqual("1", still.evaluate(
            "getComputedStyle(document.querySelector('#st-one')).opacity"))

    def test_home_end_buttons_and_backup_numbering_with_steps(self):
        page = self.open_steps_deck()
        self.assertTrue(page.locator("#previous-button").is_disabled())
        page.keyboard.press("End")  # the deck's last state: the final slide whole
        state = self.steps(page)
        self.assertEqual((6, "#/6.1", [], "B1 / 1", "●"), (
            state["index"], state["hash"], state["hidden"], state["counter"], state["dots"]))
        self.assertTrue(page.locator("#next-button").is_disabled())
        self.assertTrue(page.evaluate("document.body.classList.contains('in-appendix')"))
        page.keyboard.press("ArrowLeft")
        state = self.steps(page)
        self.assertEqual(("#/6", ["st-backup-step"], "B1 / 1", "○"), (
            state["hash"], state["hidden"], state["counter"], state["dots"]))
        self.assertFalse(page.locator("#next-button").is_disabled())
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")  # nothing beyond the last step
        self.assertEqual("#/6.1", self.steps(page)["hash"])
        page.keyboard.press("Home")
        self.assertEqual("#/0", self.steps(page)["hash"])

    def test_adjust_mode_reads_step_hashes_and_ghosts_a_hidden_figure(self):
        page = self.open_steps_deck("#/2")
        page.keyboard.press("ArrowRight")
        self.assertEqual("#/2.1", self.steps(page)["hash"])
        page.keyboard.press("g")
        page.wait_for_selector(".lecturedeck-adjust-hud:not([hidden])")
        self.assertIn("figure 1/1", page.text_content(".lecturedeck-adjust-hud"))
        ghost = page.evaluate(
            "() => { const s = getComputedStyle(document.querySelector('.figure-card'));"
            " return [s.visibility, s.opacity]; }")
        self.assertEqual(["visible", "0.45"], ghost)
        page.keyboard.press("ArrowRight")
        self.assertIn("shift: [2, 0]", page.text_content(".lecturedeck-adjust-hud code"))
        self.assertEqual("#/2.1", self.steps(page)["hash"])
        page.keyboard.press("Escape")
        page.wait_for_selector(".lecturedeck-adjust-hud", state="hidden")
        page.wait_for_function(
            "getComputedStyle(document.querySelector('.figure-card')).visibility === 'hidden'")

    def test_unchecked_decks_never_get_a_dead_press(self):
        # check rejects both slides; a legacy or unchecked deck still never
        # spends a press on a step nobody can see.
        deck = {"deck": 1, "meta": {"title": "Unchecked"}, "slides": [
            {"id": "u-demo", "chrome": False, "claim": '<b data-step="1" id="u-hidden">x</b>',
             "interactive": {"src": "assets/demo/index.html", "title": "Demo"}},
            {"id": "u-odd", "title": "Odd values",
             "body": '<p data-step="0" id="u-zero">zero</p><p data-step="x" id="u-x">x</p>'},
        ]}
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=deck))
        page.goto(self.urls["json"])
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        # The never-shown copy waits hidden, but it is no step: no dots, and
        # the first press changes slide.
        self.assertIsNone(self.steps(page)["dots"])
        self.assertEqual("none", page.evaluate(
            "getComputedStyle(document.querySelector('.slide-frame .copy')).display"))
        page.keyboard.press("ArrowRight")
        state = self.steps(page)
        self.assertEqual((1, "#/1", [], None), (
            state["index"], state["hash"], state["hidden"], state["dots"]))
        self.assertEqual(["visible", "visible"], page.evaluate(
            "() => ['#u-zero', '#u-x'].map(s =>"
            " getComputedStyle(document.querySelector(s)).visibility)"))

    def test_decks_without_steps_are_unchanged(self):
        page = self.open_deck("json")
        self.assertTrue(page.locator("#step-indicator").is_hidden())
        for index in range(11):
            with self.subTest(index=index):
                self.assertEqual(index, self.current_index(page))
                self.assertEqual(f"#/{index}", page.evaluate("location.hash"))
                self.assertEqual(0, page.locator(
                    "[data-step], .step-hidden, .step-current, [data-step-count], .step-cue,"
                    " [data-step-src]").count())
                self.assertTrue(page.locator("#step-indicator").is_hidden())
                page.keyboard.press("ArrowRight")
        for index in range(10, 7, -1):
            page.keyboard.press("ArrowLeft")
            self.assertEqual(index - 1, self.current_index(page))
        # Previous lands on the slide as before, and only on the slide.
        self.assertEqual("#/7", page.evaluate("location.hash"))

    def test_pacer_records_slides_not_steps(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=STEPS_DECK))
        page.route("**/presentation-time.json", lambda route: route.fulfill(
            json={"start": "09:00", "end": "10:00", "timeZone": "UTC",
                  "dates": ["2026-01-01"]}
        ))
        page.clock.install(time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc))
        page.goto(self.urls["json"] + "#/1")
        page.wait_for_selector("#pacing-button")
        for _ in range(3):  # two steps, then the next slide
            page.clock.run_for(2000)
            page.keyboard.press("ArrowRight")
        page.clock.run_for(2000)
        page.keyboard.press("ArrowLeft")  # back onto the whole slide
        page.clock.run_for(2000)
        (entry,) = journal(page)
        visits = entry["record"]["visits"]
        # One visit per slide shown, however many steps it revealed; the
        # record keeps its schema (no per-step field).
        self.assertEqual(["st-copy", "st-figure", "st-copy"], [v["slideId"] for v in visits])
        self.assertEqual({"slideId", "startedAt", "durationMs", "phase"}, set(visits[0]))
        self.assertGreaterEqual(visits[0]["durationMs"], 5000)

    def open_stepped(self, deck: dict, fragment: str = "", css: str | None = None, **context):
        page = self.browser.new_page(**context)
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=deck))
        if css is not None:
            page.route("**/deck.css", lambda route: route.fulfill(
                body=css, content_type="text/css"))
        page.goto(self.urls["json"] + fragment)
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        return page

    def demo_frame(self, page):
        """The live slide's demo page, once it has loaded."""
        page.frame_locator(".interactive-frame iframe").locator("#next").wait_for()
        return next(f for f in page.frames if f.url.endswith("/assets/demo/index.html"))

    def visibility(self, page, selector: str) -> str:
        return page.evaluate(
            "s => getComputedStyle(document.querySelector(s)).visibility", selector)

    def test_part_and_course_labels_step_only_their_own_slide(self):
        # check rejects the meta steps; the viewer still never lets a label
        # shown on many slides hide part of them.
        deck = {"deck": 1, "meta": {
            "title": "Labels", "section": '<span data-step="1">COURSE</span>',
            "opening": '<span data-step="1">START</span>'}, "slides": [
            {"id": "open", "title": "Opening slide"},
            {"id": "part", "type": "section",
             "title": '<span data-step="1" class="part-name">Part A</span>'},
            {"id": "plain", "title": "Plain slide", "claim": "Nothing stepped here."},
        ]}
        page = self.open_stepped(deck)
        state = self.steps(page)
        self.assertEqual((None, []), (state["dots"], state["hidden"]))
        self.assertEqual(0, page.locator("#deck [data-step]").count())
        self.assertEqual(("START", "COURSE"), (
            page.text_content(".slide-frame .eyebrow"),
            page.text_content(".slide-frame .course-name")))
        # The section slide keeps its step, in its title and in the eyebrow
        # that repeats it.
        page.keyboard.press("ArrowRight")
        state = self.steps(page)
        self.assertEqual((1, "○", 2), (state["index"], state["dots"], len(state["hidden"])))
        page.keyboard.press("ArrowRight")
        self.assertEqual([], self.steps(page)["hidden"])
        # The slide after it inherits the label whole.
        page.keyboard.press("ArrowRight")
        state = self.steps(page)
        self.assertEqual((2, "#/2", None, []), (
            state["index"], state["hash"], state["dots"], state["hidden"]))
        self.assertEqual("Part A", page.text_content(".slide-frame .eyebrow"))
        self.assertEqual(0, page.locator("#deck [data-step]").count())

    def test_a_step_nested_in_a_later_one_appears_with_it(self):
        # check warns about both; every press still shows something.
        deck = {"deck": 1, "meta": {"title": "Nest"}, "slides": [
            {"id": "nest", "title": "Nest", "claim": '<span data-step="1" id="first">First.</span>',
             "body": '<div data-step="2" id="outer">Outer <span data-step="1" id="inner">'
                     "inner</span></div>",
             "figure": {"id": "late", "src": "assets/figure.png", "alt": "F", "step": 3,
                        "caption": '<b data-step="2" id="early-caption">Caption.</b>'}},
        ]}
        page = self.open_stepped(deck)
        self.assertEqual("○○○", self.steps(page)["dots"])
        self.assertIsNone(page.get_attribute("#inner", "data-step"))
        page.keyboard.press("ArrowRight")
        self.assertEqual(("#/0.1", "visible", "hidden"), (
            self.steps(page)["hash"], self.visibility(page, "#first"),
            self.visibility(page, "#inner")))
        page.keyboard.press("ArrowRight")
        self.assertEqual(("#/0.2", "visible", "hidden"), (
            self.steps(page)["hash"], self.visibility(page, "#inner"),
            self.visibility(page, "#early-caption")))
        page.keyboard.press("ArrowRight")
        self.assertEqual(("#/0.3", "visible", "visible"), (
            self.steps(page)["hash"], self.visibility(page, ".figure-card"),
            self.visibility(page, "#early-caption")))

    def test_same_slide_addresses_are_normalised(self):
        page = self.open_steps_deck("#/1.2")
        page.evaluate("location.hash = '#/1.9'")
        page.wait_for_function("location.hash === '#/1.2'")
        self.assertEqual([], self.steps(page)["hidden"])

    def test_overview_pages_whole_slides(self):
        page = self.open_steps_deck("#/1")
        current = "document.querySelector('.overview-card[aria-current=\"true\"]').dataset.index"
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        page.keyboard.press("ArrowRight")
        self.assertEqual("2", page.evaluate(current))
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")
        self.assertEqual(("#/2", 2), (self.steps(page)["hash"], len(self.steps(page)["hidden"])))
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        page.keyboard.press("ArrowLeft")
        self.assertEqual("1", page.evaluate(current))
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")
        self.assertEqual(("#/1.2", []), (self.steps(page)["hash"], self.steps(page)["hidden"]))

    def test_shift_pages_whole_slides_past_steps(self):
        page = self.open_steps_deck("#/1")
        page.keyboard.press("Shift+ArrowRight")
        state = self.steps(page)
        self.assertEqual(("#/2", 2), (state["hash"], len(state["hidden"])))
        page.keyboard.press("Shift+ArrowLeft")
        self.assertEqual(("#/1.2", []), (self.steps(page)["hash"], self.steps(page)["hidden"]))
        page.keyboard.press("Shift+PageUp")
        self.assertEqual("#/0", self.steps(page)["hash"])
        page.keyboard.press("Shift+PageDown")
        page.keyboard.press("Shift+ArrowDown")
        self.assertEqual("#/2", self.steps(page)["hash"])

    def test_footer_step_cue_follows_the_live_slide(self):
        page = self.open_steps_deck("#/1")
        cue = ".slide-frame .footer-nav > .step-cue"
        marks = f"{cue} > i"
        self.assertEqual(("true", 2, 0), (
            page.get_attribute(cue, "aria-hidden"), page.locator(marks).count(),
            page.locator(f"{marks}.shown").count()))
        number = self.box(page, ".slide-frame .page-number")
        width = self.box(page, cue)["w"]
        page.keyboard.press("ArrowRight")
        self.assertEqual(1, page.locator(f"{marks}.shown").count())
        page.keyboard.press("ArrowRight")
        self.assertEqual(2, page.locator(f"{marks}.shown").count())
        # Stepping never moves the footer.
        self.assertEqual((number, width), (
            self.box(page, ".slide-frame .page-number"), self.box(page, cue)["w"]))
        page.keyboard.press("Home")
        self.assertEqual(0, page.locator(".step-cue").count())
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        self.assertEqual(0, page.locator(".step-cue").count())

    def walk_fixed_boxes(self, page) -> list[dict]:
        """Every slide of FIXED_BOX_DECK at every step, by Next, from #/0."""
        visits = [page.evaluate(FIXED_BOXES)]
        while not page.is_disabled("#next-button"):
            page.keyboard.press("ArrowRight")
            visits.append(page.evaluate(FIXED_BOXES))
        return visits

    def test_step_dots_never_move_a_fixed_element(self):
        # Owner, 2026-10-18: "Your dots shift the page numbers. I HATE it
        # when a thing with a fixed position is shifted." Slides without
        # steps, with one step and with three, at no step, mid-way and
        # whole, and the step from 9 to 10 and into the backup, all keep
        # each fixed element in the same box, to the pixel.
        expected = (
            ["#/0", "#/1", "#/1.1", "#/2", "#/2.1", "#/2.2", "#/2.3", "#/3", "#/4",
             "#/5", "#/5.1", "#/5.2", "#/6", "#/7", "#/8", "#/9", "#/9.1", "#/9.2",
             "#/9.3", "#/10", "#/11", "#/11.1", "#/11.2"])
        for theme in ("dark", "light"):
            for size in ({"width": 1280, "height": 900}, {"width": 960, "height": 720}):
                with self.subTest(theme=theme, size=size):
                    page = self.browser.new_page(viewport=size)
                    self.addCleanup(page.close)
                    page.add_init_script(
                        f"try {{ localStorage.setItem('lecturedeck-theme', '{theme}'); }}"
                        " catch (_) {}")
                    page.route("**/deck.json", lambda route: route.fulfill(json=FIXED_BOX_DECK))
                    page.goto(self.urls["json"] + "#/0")
                    page.wait_for_function("Boolean(window.LECTUREDECK)")
                    self.assertEqual(theme == "light", page.evaluate(
                        "document.body.classList.contains('light-theme')"))
                    # The strip is open at both sizes, so its counter is on screen.
                    self.assertTrue(page.evaluate(
                        "document.querySelector('#presentation-controls')"
                        ".classList.contains('has-safe-space')"))
                    page.wait_for_function(
                        "document.querySelector('#controls-tools').getAnimations().length === 0")
                    visits = self.walk_fixed_boxes(page)
                    self.assertEqual(expected, [v["hash"] for v in visits])
                    first = visits[0]["boxes"]
                    for visit in visits[1:]:
                        for selector, box in visit["boxes"].items():
                            self.assertEqual(first[selector], box, f"{visit['hash']} {selector}")
                    for visit in visits:
                        steps = FIXED_STEPS.get(int(visit["hash"][2:].split(".")[0]), 0)
                        shown = int(visit["hash"].split(".")[1]) if "." in visit["hash"] else 0
                        self.assertEqual(
                            {"footer": steps, "controls": steps},
                            {"footer": len(visit["cue"]), "controls": len(visit["dots"])},
                            visit["hash"])
                        self.assertEqual(
                            ["shown"] * shown + [""] * (steps - shown), visit["cue"], visit["hash"])
                        self.assertEqual(visit["cue"], visit["dots"], visit["hash"])
                        # Legible where they are: under the page number,
                        # inside the frame; inside the counter's own box.
                        for problem in visit["problems"]:
                            self.fail(f"{visit['hash']}: {problem}")
                    # The reserved width is never read as text.
                    self.assertEqual(("B2 / 2", "B2 / 2"), (
                        page.inner_text("#deck .page-number"), page.inner_text("#counter")))

    def test_step_dots_survive_a_legacy_span_pill_rule(self):
        # An older deck.css draws a pill on every span of the strip. The
        # counter keeps its one pill; its slot and dots draw none.
        css = (".deck-chrome button, .deck-chrome span { border: 1px solid #504945;"
               " border-radius: 7px; padding: 7px 10px; background: rgba(29,32,33,.92); }")
        page = self.open_stepped(FIXED_BOX_DECK, "#/2", css=css,
                                 viewport={"width": 1280, "height": 900})
        page.wait_for_function(
            "document.querySelector('#controls-tools').getAnimations().length === 0")
        bare = page.evaluate(FIXED_BOXES)
        page.keyboard.press("ArrowRight")
        stepped = page.evaluate(FIXED_BOXES)
        page.keyboard.press("Shift+ArrowLeft")
        page.keyboard.press("Shift+ArrowLeft")
        plain = page.evaluate(FIXED_BOXES)
        self.assertEqual(("#/2", "#/2.1", "#/0"), (bare["hash"], stepped["hash"], plain["hash"]))
        self.assertEqual((bare["boxes"], bare["boxes"]), (stepped["boxes"], plain["boxes"]))
        self.assertEqual([[], [], []], [v["problems"] for v in (bare, stepped, plain)])
        self.assertEqual(["0px", "0px"], page.evaluate(
            "['.counter-slot', '#step-indicator'].map(s =>"
            " getComputedStyle(document.querySelector(s)).borderTopWidth)"))

    def test_style_guide_dimming_example(self):
        # The STYLE_GUIDE's own deck.css example, as published.
        guide = (Path(__file__).resolve().parents[1] / "STYLE_GUIDE.md").read_text(
            encoding="utf-8").split("## Step reveals", 1)[1]
        css = re.search(r"```css\n(.*?)```", guide, re.S).group(1)
        opacity = "s => getComputedStyle(document.querySelector(s)).opacity"
        settled = ("([s, o]) => getComputedStyle(document.querySelector(s)).opacity === o")
        page = self.open_stepped(STEPS_DECK, "#/5", css=css)
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        caption = page.locator(".video-card > figcaption")
        # A caption the step took over is the current step, never dimmed.
        self.assertEqual(("step-current", None), (
            caption.get_attribute("class"), page.get_attribute("#st-caption", "data-step")))
        page.wait_for_function(settled, arg=[".video-card > figcaption", "1"])
        self.assertEqual("1", page.evaluate(opacity, "#st-caption"))
        self.assertEqual("1", page.evaluate(opacity, ".video-card"))  # media stay bright
        page.evaluate("location.hash = '#/1.2'")
        page.wait_for_function(settled, arg=["#st-one", "0.6"])
        self.assertEqual("1", page.evaluate(opacity, "#st-two-a"))
        page.emulate_media(media="print")
        page.wait_for_function(settled, arg=["#st-one", "1"])

    def test_steps_follow_theme_and_width_changes(self):
        # One twin of a dark/light figure pair shows per theme, and a block
        # appears only on wide screens: each is hidden until its step.
        deck = {"deck": 1, "meta": {"title": "Twins"}, "slides": [
            {"id": "twins", "title": "Twins", "claim": "Claim.", "layout": "figures",
             "body": '<p data-step="2" id="wide-only">Wide only.</p>',
             "figures": [
                 {"id": "dark-twin", "src": "assets/figure.png", "alt": "Dark", "step": 1},
                 {"id": "light-twin", "src": "assets/figure.png", "alt": "Light", "step": 1}]},
        ]}
        css = (
            "body:not(.light-theme) [data-figure-id='light-twin'],"
            " body.light-theme [data-figure-id='dark-twin'] { display: none; }"
            " @media (max-width: 700px) { #wide-only { display: none; } }"
        )
        shown = """() => [...document.querySelectorAll('.slide-frame .figure-card')]
          .filter(n => n.checkVisibility() && getComputedStyle(n).visibility === 'visible')
          .map(n => n.dataset.figureId)"""
        page = self.open_stepped(deck, css=css, viewport={"width": 1280, "height": 720})
        self.assertEqual(("○○", []), (self.steps(page)["dots"], page.evaluate(shown)))
        page.keyboard.press("t")
        page.wait_for_selector("#appearance-dialog[open]")
        page.get_by_label("Light", exact=True).check()
        page.keyboard.press("Escape")
        page.wait_for_selector("#appearance-dialog", state="hidden")
        # The next arrow key pages the deck at once, though focus may still
        # sit on a radio of the closed dialog; it then moves to a control
        # that can take it (the controls strip is collapsed here).
        # The light twin that just appeared waits for its step.
        self.assertEqual(("#/0", []), (self.steps(page)["hash"], page.evaluate(shown)))
        page.keyboard.press("ArrowRight")
        self.assertEqual(
            ("#/0.1", ["light-twin"]), (self.steps(page)["hash"], page.evaluate(shown)))
        page.wait_for_function(
            "!document.querySelector('#appearance-dialog').contains(document.activeElement)")
        # Narrow, the wide-only block is no step; wide again, it waits for one.
        page.set_viewport_size({"width": 600, "height": 400})
        page.wait_for_function(f"{CONTROL_DOTS} === '●'")
        page.set_viewport_size({"width": 1280, "height": 720})
        page.wait_for_function(f"{CONTROL_DOTS} === '●○'")
        self.assertEqual("hidden", self.visibility(page, "#wide-only"))
        page.keyboard.press("ArrowRight")
        self.assertEqual(("#/0.2", "visible"), (
            self.steps(page)["hash"], self.visibility(page, "#wide-only")))

    def test_stepped_interactive_loads_when_it_appears(self):
        deck = {"deck": 1, "meta": {"title": "Demo"}, "slides": [
            {"id": "before", "title": "Before"},
            {"id": "demo", "title": "Demo", "claim": "Always.",
             "interactive": {"src": "assets/demo/index.html", "title": "Demo", "step": 1}},
            {"id": "after", "title": "After"},
        ]}
        page = self.open_stepped(deck)
        iframe = page.locator(".interactive-frame iframe")
        demo = "/assets/demo/index.html"
        page.keyboard.press("ArrowRight")
        # On screen bare, the page is not loaded at all.
        self.assertEqual((None, "assets/demo/index.html"), (
            iframe.get_attribute("src"), iframe.get_attribute("data-step-src")))
        self.assertFalse(any(f.url.endswith(demo) for f in page.frames))
        page.keyboard.press("ArrowRight")
        self.assertEqual(("assets/demo/index.html", None), (
            iframe.get_attribute("src"), iframe.get_attribute("data-step-src")))
        frame = page.frame_locator(".interactive-frame iframe")
        frame.locator("#next").wait_for()
        # Stepped back, it stays loaded.
        page.keyboard.press("ArrowLeft")
        self.assertEqual("assets/demo/index.html", iframe.get_attribute("src"))
        self.assertTrue(any(f.url.endswith(demo) for f in page.frames))
        # A slide reached by Previous arrives whole, and loads at once.
        page.keyboard.press("End")
        page.keyboard.press("ArrowLeft")
        self.assertEqual(("#/1.1", "assets/demo/index.html"), (
            self.steps(page)["hash"], iframe.get_attribute("src")))

    def test_interactive_focus_and_home_end_messages(self):
        deck = {"deck": 1, "meta": {"title": "Demo"}, "slides": [
            {"id": "before", "title": "Before"},
            {"id": "demo", "title": "Demo", "claim": "Always.",
             "interactive": {"src": "assets/demo/index.html", "title": "Demo", "step": 1}},
            {"id": "after", "title": "After", "claim": '<b data-step="1">Late.</b>'},
        ]}
        page = self.open_stepped(deck, "#/1.1")
        frame = self.demo_frame(page)
        frame.focus("#next")
        # The page's own Back hides it: focus leaves the now inert frame, so
        # the keyboard and a clicker keep driving the deck.
        frame.evaluate("parent.postMessage({type: 'lecturedeck:navigate', direction: -1}, '*')")
        page.wait_for_function("location.hash === '#/1'")
        self.assertEqual("BODY", page.evaluate("document.activeElement.tagName"))
        page.keyboard.press("ArrowRight")
        self.assertEqual("#/1.1", self.steps(page)["hash"])
        # A page's Home and End act as the deck's.
        frame.evaluate("parent.postMessage({type: 'lecturedeck:navigate', to: 'last'}, '*')")
        page.wait_for_function("location.hash === '#/2.1'")
        page.evaluate("location.hash = '#/1.1'")
        frame = self.demo_frame(page)
        frame.evaluate("parent.postMessage({type: 'lecturedeck:navigate', to: 'first'}, '*')")
        page.wait_for_function("location.hash === '#/0'")
        # Anything else in `to` is ignored.
        page.evaluate("location.hash = '#/1.1'")
        frame = self.demo_frame(page)
        frame.evaluate("parent.postMessage({type: 'lecturedeck:navigate', to: 'middle'}, '*')")
        page.wait_for_timeout(150)
        self.assertEqual("#/1.1", self.steps(page)["hash"])

    # Photo viewer --------------------------------------------------------

    def open_photo_deck(self, fragment: str = "", deck: dict = PHOTO_DECK, css: str | None = None,
                        init: str | None = None, within=None, **options):
        # `within` opens the page in an existing context, sharing its storage.
        page = within.new_page(**options) if within else self.browser.new_page(**options)
        self.addCleanup(page.close)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual([], errors))
        if init:
            page.add_init_script(init)
        page.route("**/deck.json", lambda route: route.fulfill(json=deck))
        page.route("**/assets/drawn.svg", lambda route: route.fulfill(
            body=DRAWN_SVG, content_type="image/svg+xml"))
        clip = getattr(type(self), "_clip", None)
        if clip:
            page.route("**/assets/clip.webm", ranged(clip, "video/webm"))
        if css is not None:
            page.route("**/deck.css", lambda route: route.fulfill(
                body=css, content_type="text/css"))
        page.goto(self.urls["json"] + fragment)
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        return page

    def photo(self, page) -> dict:
        return page.evaluate(PHOTO_STATE)

    def open_photo(self, page, selector: str) -> dict:
        page.click(selector)
        page.wait_for_selector("#photo-viewer[open]")
        return self.photo(page)

    def close_photo(self, page, key: str = "Escape") -> dict:
        page.keyboard.press(key)
        page.wait_for_selector("#photo-viewer", state="hidden")
        return self.photo(page)

    def recorded_clip(self) -> bytes | None:
        if not hasattr(type(self), "_clip"):
            page = self.browser.new_page()
            try:
                page.goto("about:blank")
                text = page.evaluate(RECORD_CLIP)
            finally:
                page.close()
            type(self)._clip = base64.b64decode(text) if text else None
        return type(self)._clip

    def assert_fits(self, state: dict) -> None:
        media, stage = state["media"], state["stage"]
        self.assertLessEqual(media["w"], stage["w"] + 0.5)
        self.assertLessEqual(media["h"], stage["h"] + 0.5)
        self.assertTrue(abs(media["w"] - stage["w"]) < 1 or abs(media["h"] - stage["h"]) < 1, state)
        self.assertAlmostEqual(media["x"] + media["w"] / 2, stage["x"] + stage["w"] / 2, delta=1)
        self.assertAlmostEqual(media["y"] + media["h"] / 2, stage["y"] + stage["h"] / 2, delta=1)

    def test_photo_opens_full_window_and_any_paging_key_only_closes_it(self):
        # Owner, 2026-10-18: "Projector eats a lot of contrast ... So I can
        # click on any picture, and it fills the screen, and I can adjust
        # brightness/contrast".
        page = self.open_photo_deck("#/1", viewport={"width": 1280, "height": 800})
        image = "#deck .figure-card img"
        self.assertEqual("zoom-in", page.evaluate(
            "s => getComputedStyle(document.querySelector(s)).cursor", image))
        state = self.open_photo(page, image)
        self.assertEqual((True, "image", "#/1", 1, ["ph-later"]), (
            state["open"], state["kind"], state["hash"], state["index"], state["hidden"]))
        self.assertEqual(["Brightness 100 %", "Contrast 100 %", "Zoom 1.0×"], state["values"])
        self.assert_fits(state)
        # The stage and the bar fill the window exactly.
        bar = self.box(page, "#photo-viewer .photo-bar")
        stage = state["stage"]
        self.assertEqual((0, 0, 1280), (stage["x"], stage["y"], stage["w"]))
        self.assertAlmostEqual(800, state["stage"]["h"] + bar["h"], delta=1)
        self.assertEqual("photo-stage", page.evaluate("document.activeElement.className"))
        # Big plain labels on a dark backdrop, in both color modes.
        sizes = page.evaluate(
            "[...document.querySelectorAll('#photo-viewer .photo-bar :is(button, .photo-value)')]"
            ".map(n => parseFloat(getComputedStyle(n).fontSize))")
        self.assertGreaterEqual(min(sizes), 18)
        self.assertEqual("rgb(17, 19, 20)", page.evaluate(
            "getComputedStyle(document.querySelector('#photo-viewer .photo-bar')).backgroundColor"))
        # A clicker or navigation key closes it on the same slide and step;
        # it never pages or steps.
        keys = ["Escape", "PageDown", "PageUp", "ArrowLeft", "ArrowRight", "ArrowUp",
                "ArrowDown", "Space", "Home", "End", "Shift+ArrowRight", "Shift+PageDown"]
        for key in keys:
            with self.subTest(key=key):
                if not self.photo(page)["open"]:
                    self.open_photo(page, image)
                state = self.close_photo(page, key)
                self.assertEqual((False, "#/1", 1, ["ph-later"]), (
                    state["open"], state["hash"], state["index"], state["hidden"]))
        # The Close button and a click on the backdrop close it too.
        page.set_viewport_size({"width": 1280, "height": 1000})
        self.open_photo(page, image)
        page.click('#photo-viewer [data-photo-act="close"]')
        page.wait_for_selector("#photo-viewer", state="hidden")
        self.open_photo(page, image)
        page.mouse.click(640, 20)  # the black band above the fitted photo
        page.wait_for_selector("#photo-viewer", state="hidden")
        self.assertEqual("#/1", self.photo(page)["hash"])
        # The deck pages on as before.
        page.keyboard.press("ArrowRight")
        self.assertEqual("#/1.1", self.photo(page)["hash"])
        # In light mode the overlay keeps its dark backdrop and light labels.
        page.keyboard.press("t")
        page.wait_for_selector("#appearance-dialog[open]")
        page.get_by_label("Light", exact=True).check()
        page.keyboard.press("Escape")
        page.wait_for_selector("#appearance-dialog", state="hidden")
        self.open_photo(page, image)
        self.assertEqual(["rgb(0, 0, 0)", "rgb(251, 241, 199)", "rgb(17, 19, 20)"], page.evaluate(
            "['#photo-viewer', '#photo-viewer .photo-value', '#photo-viewer .photo-bar']"
            ".map((s, i) => getComputedStyle(document.querySelector(s))"
            "[i === 1 ? 'color' : 'backgroundColor'])"))

    def test_photo_brightness_contrast_and_shortcuts(self):
        page = self.open_photo_deck("#/1", viewport={"width": 1280, "height": 800})
        image = "#deck .figure-card img"
        self.open_photo(page, image)
        buttons = ("() => [...document.querySelectorAll('#photo-viewer .photo-bar button')]"
                   ".map(b => { const r = b.getBoundingClientRect();"
                   " return [r.x, r.y, r.width]; })")
        still = page.evaluate(buttons)
        for _ in range(3):
            page.click('#photo-viewer [data-photo-act="brightness-up"]')
        state = self.photo(page)
        self.assertEqual(("Brightness 130 %", "brightness(130%) contrast(100%)"), (
            state["values"][0], state["filter"]))
        page.keyboard.press("Shift+B")
        page.keyboard.press("c")
        page.keyboard.press("c")
        state = self.photo(page)
        self.assertEqual((["Brightness 120 %", "Contrast 120 %", "Zoom 1.0×"],
                          "brightness(120%) contrast(120%)"), (state["values"], state["filter"]))
        page.keyboard.press("Shift+C")
        self.assertEqual("Contrast 110 %", self.photo(page)["values"][1])
        # Limits: 50-300 %, and the button at a limit says so.
        for _ in range(30):
            page.keyboard.press("b")
        self.assertEqual("Brightness 300 %", self.photo(page)["values"][0])
        self.assertEqual("true", page.get_attribute(
            '#photo-viewer [data-photo-act="brightness-up"]', "aria-disabled"))
        for _ in range(30):
            page.keyboard.press("Shift+B")
        self.assertEqual("Brightness 50 %", self.photo(page)["values"][0])
        self.assertEqual(("true", "false"), (
            page.get_attribute('#photo-viewer [data-photo-act="brightness-down"]', "aria-disabled"),
            page.get_attribute('#photo-viewer [data-photo-act="brightness-up"]', "aria-disabled")))
        # No value change moves a button.
        self.assertEqual(still, page.evaluate(buttons))
        page.keyboard.press("+")
        self.assertEqual("Zoom 1.4×", self.photo(page)["values"][2])
        self.assertEqual(still, page.evaluate(buttons))
        # 0 (or Reset) puts everything back.
        page.keyboard.press("0")
        state = self.photo(page)
        self.assertEqual((["Brightness 100 %", "Contrast 100 %", "Zoom 1.0×"], ""), (
            state["values"], state["filter"]))
        self.assert_fits(state)
        # The deck's own shortcuts wait behind the photo.
        for key in ("o", "f", "t", "g"):
            page.keyboard.press(key)
        self.assertEqual([True, True, False, False, True], page.evaluate(
            "() => [document.querySelector('#photo-viewer').open,"
            " document.querySelector('#overview').hidden,"
            " Boolean(document.fullscreenElement)"
            " || document.body.classList.contains('pseudo-fullscreen'),"
            " document.querySelector('#appearance-dialog').open,"
            " document.querySelector('.lecturedeck-adjust-hud').hidden]"))
        # A clicker's Space closes the photo even on a button with the focus
        # (Chromium focuses a clicked button, a keyboard user tabs to one),
        # and never presses that button.
        page.click('#photo-viewer [data-photo-act="brightness-up"]')
        page.focus('#photo-viewer [data-photo-act="brightness-up"]')
        self.assertEqual("brightness-up", page.evaluate("document.activeElement.dataset.photoAct"))
        self.close_photo(page, "Space")
        self.assertEqual("BODY", page.evaluate("document.activeElement.tagName"))
        # The clicker's next Space pages the deck.
        page.keyboard.press("Space")
        self.assertEqual("#/1.1", self.photo(page)["hash"])
        state = self.open_photo(page, image)
        self.assertEqual("Brightness 110 %", state["values"][0])
        # Reset by its button too.
        page.click('#photo-viewer [data-photo-act="reset"]')
        self.assertEqual("Brightness 100 %", self.photo(page)["values"][0])

    def test_photo_zooms_around_the_cursor_pans_and_toggles_on_double_click(self):
        page = self.open_photo_deck("#/1", viewport={"width": 1280, "height": 1000})
        fitted = self.open_photo(page, "#deck .figure-card img")
        media = fitted["media"]
        x, y = media["x"] + media["w"] * 0.3, media["y"] + media["h"] * 0.4
        page.mouse.move(x, y)
        page.mouse.wheel(0, -200)
        page.wait_for_function("document.querySelector('#photo-viewer').dataset.zoomed === 'true'")
        zoomed = self.photo(page)["media"]
        # The point under the cursor stays under it.
        self.assertAlmostEqual(0.3, (x - zoomed["x"]) / zoomed["w"], delta=0.005)
        self.assertAlmostEqual(0.4, (y - zoomed["y"]) / zoomed["h"], delta=0.005)
        self.assertGreater(zoomed["w"], media["w"])
        for _ in range(25):
            page.mouse.wheel(0, -400)
        page.wait_for_function(
            "document.querySelector('[data-photo-value=\"zoom\"]').textContent === 'Zoom 8.0×'")
        self.assertAlmostEqual(8 * media["w"], self.photo(page)["media"]["w"], delta=1)
        for _ in range(25):
            page.mouse.wheel(0, 400)
        page.wait_for_function(
            "document.querySelector('[data-photo-value=\"zoom\"]').textContent === 'Zoom 1.0×'")
        self.assertEqual(media, self.photo(page)["media"])
        # A trackpad pinch (a wheel with ctrlKey) zooms too, never the page.
        page.keyboard.down("Control")
        page.mouse.wheel(0, -30)
        page.keyboard.up("Control")
        page.wait_for_function("document.querySelector('#photo-viewer').dataset.zoomed === 'true'")
        self.assertEqual(1, page.evaluate("visualViewport.scale"))
        page.keyboard.press("0")
        # The keys zoom by steps of the square root of two.
        page.keyboard.press("=")
        page.keyboard.press("+")
        self.assertEqual("Zoom 2.0×", self.photo(page)["values"][2])
        page.keyboard.press("-")
        page.keyboard.press("-")
        page.keyboard.press("-")
        state = self.photo(page)
        self.assertEqual(("Zoom 1.0×", media), (state["values"][2], state["media"]))
        # A double-click toggles between fit and 2x at the point clicked.
        page.mouse.dblclick(x, y)
        state = self.photo(page)
        self.assertEqual("Zoom 2.0×", state["values"][2])
        self.assertAlmostEqual(0.3, (x - state["media"]["x"]) / state["media"]["w"], delta=0.005)
        # Dragging pans and leaves the photo open, though it ends off the picture.
        start = state["media"]
        page.mouse.move(640, 500)
        page.mouse.down()
        page.mouse.move(540, 450, steps=4)
        page.mouse.up()
        state = self.photo(page)
        self.assertTrue(state["open"])
        self.assertAlmostEqual(start["x"] - 100, state["media"]["x"], delta=1)
        self.assertAlmostEqual(start["y"] - 50, state["media"]["y"], delta=1)
        # A pan stops at the picture's edge, never showing a gap.
        page.mouse.move(640, 500)
        page.mouse.down()
        page.mouse.move(1270, 990, steps=4)
        page.mouse.up()
        state = self.photo(page)
        self.assertEqual((0, 0), (state["media"]["x"], max(0, state["media"]["y"])))
        page.mouse.dblclick(state["media"]["x"] + 50, state["media"]["y"] + 50)
        state = self.photo(page)
        self.assertEqual(("Zoom 1.0×", media), (state["values"][2], state["media"]))
        self.assertEqual(1, page.evaluate("visualViewport.scale"))
        self.assertEqual("#/1", self.photo(page)["hash"])
        # A trackpad scroll's momentum that outlasts the photo pages nothing.
        for _ in range(4):
            page.mouse.wheel(0, -30)
        page.keyboard.press("Escape")
        for _ in range(6):
            page.mouse.wheel(0, 30)
        page.wait_for_timeout(100)
        self.assertEqual("#/1", self.photo(page)["hash"])

    def test_photo_settings_are_remembered_per_deck(self):
        context = self.browser.new_context()
        self.addCleanup(context.close)
        page = self.open_photo_deck("#/1", within=context)
        self.open_photo(page, "#deck .figure-card img")
        for key in ("b", "b", "b", "c"):
            page.keyboard.press(key)
        self.close_photo(page)
        key = "lecturedeck-photo:/webdeck/:Photo deck"
        self.assertEqual({"brightness": 130, "contrast": 110, "all": False},
                         json.loads(page.evaluate("k => localStorage.getItem(k)", key)))
        # The next photo opens with the same correction, also after a reload.
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        state = self.open_photo(page, "#deck [data-figure-id='ph-grid-photo'] img")
        self.assertEqual(("#/2", "brightness(130%) contrast(110%)"),
                         (state["hash"], state["filter"]))
        self.close_photo(page)
        page.reload()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        state = self.open_photo(page, "#deck [data-figure-id='ph-grid-photo'] img")
        self.assertEqual(["Brightness 130 %", "Contrast 110 %", "Zoom 1.0×"], state["values"])
        # Another deck keeps its own.
        other = self.open_photo_deck("#/1", deck={**PHOTO_DECK, "meta": {"title": "Other deck"}},
                                     within=context)
        self.assertEqual("", self.open_photo(other, "#deck .figure-card img")["filter"])
        kept = json.loads(other.evaluate("k => localStorage.getItem(k)", key))
        self.assertEqual(130, kept["brightness"])
        # Without storage it works for the page and remembers nothing.
        blocked = ("Object.defineProperty(window, 'localStorage', {configurable: true,"
                   " get() { throw new DOMException('blocked', 'SecurityError'); }});")
        page = self.open_photo_deck("#/1", init=blocked)
        self.open_photo(page, "#deck .figure-card img")
        page.keyboard.press("b")
        page.keyboard.press("a")
        self.assertEqual("brightness(110%) contrast(100%)", self.photo(page)["filter"])
        self.close_photo(page)
        self.assertEqual("brightness(1.1) contrast(1)", page.evaluate(
            "getComputedStyle(document.querySelector('#deck .figure-card img')).filter"))
        page.reload()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.assertEqual("", self.open_photo(page, "#deck .figure-card img")["filter"])

    def test_use_on_all_photos_corrects_photos_and_videos_only(self):
        page = self.open_photo_deck("#/3", viewport={"width": 1280, "height": 800})
        marked = page.evaluate(
            "[...document.querySelectorAll('#deck img')].map(n => [n.id, n.className])")
        self.assertEqual(
            [["ph-card-photo", "photo-zoomable photo-content"], ["ph-linked", ""], ["ph-off", ""],
             ["ph-math", "math-display"], ["ph-summary", ""]],
            marked)
        filters = """() => Object.fromEntries([
          ['card', '#ph-card-photo'], ['linked', '#ph-linked'], ['off', '#ph-off'],
          ['formula', '#deck .formula'], ['counter', '#counter'], ['frame', '#deck .slide-frame'],
        ].map(([k, s]) => [k, getComputedStyle(document.querySelector(s)).filter]))"""
        self.assertEqual({"none"}, set(page.evaluate(filters).values()))
        self.open_photo(page, "#ph-card-photo")
        page.keyboard.press("b")
        page.keyboard.press("b")
        page.keyboard.press("c")
        toggle = '#photo-viewer [data-photo-act="all"]'
        self.assertEqual("false", page.get_attribute(toggle, "aria-pressed"))
        page.click(toggle)
        self.assertEqual("true", page.get_attribute(toggle, "aria-pressed"))
        self.close_photo(page)
        self.assertEqual({"card": "brightness(1.2) contrast(1.1)", "linked": "none", "off": "none",
                          "formula": "none", "counter": "none", "frame": "none"},
                         page.evaluate(filters))
        # A drawn SVG figure stays as drawn; the photo beside it is corrected.
        page.keyboard.press("PageUp")
        grid = ("s => getComputedStyle("
                "document.querySelector(`#deck [data-figure-id='${s}'] img`)).filter")
        self.assertEqual(("brightness(1.2) contrast(1.1)", "none"), (
            page.evaluate(grid, "ph-grid-photo"), page.evaluate(grid, "ph-drawn")))
        # The drawing still opens, with the viewer's correction.
        state = self.open_photo(page, "#deck [data-figure-id='ph-drawn'] img")
        self.assertEqual("brightness(120%) contrast(110%)", state["filter"])
        self.close_photo(page)
        # Videos and the overview thumbnails follow it; print never does.
        page.evaluate("location.hash = '#/4'")
        page.wait_for_function("document.querySelector('#deck .slide-frame').dataset.index === '4'")
        self.assertEqual("brightness(1.2) contrast(1.1)", page.evaluate(
            "getComputedStyle(document.querySelector('#deck video')).filter"))
        page.emulate_media(media="print")
        self.assertEqual("none", page.evaluate(
            "getComputedStyle(document.querySelector('#deck video')).filter"))
        page.emulate_media(media="screen")
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        self.assertEqual(
            ["brightness(1.2) contrast(1.1)", "none"],
            page.evaluate(
                "[\"[data-figure-id='ph-grid-photo'] img\", \"[data-figure-id='ph-drawn'] img\"]"
                ".map(s => getComputedStyle(document.querySelector('#overview ' + s)).filter)"))
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")
        # The Appearance dialog carries the same toggle, and turns it off.
        page.keyboard.press("t")
        page.wait_for_selector("#appearance-dialog[open]")
        checkbox = page.get_by_label("Use on all photos", exact=True)
        self.assertTrue(checkbox.is_checked())
        self.assertIn("Brightness 120 %, contrast 110 %",
                      page.text_content("#photo-all-note").replace("\xa0", " "))
        checkbox.uncheck()
        page.keyboard.press("Escape")
        page.wait_for_selector("#appearance-dialog", state="hidden")
        self.assertEqual("none", page.evaluate(
            "getComputedStyle(document.querySelector('#deck video')).filter"))
        self.assertFalse(json.loads(page.evaluate(
            "localStorage.getItem('lecturedeck-photo:/webdeck/:Photo deck')"))["all"])
        # A filter deck.css gives an image keeps priority over the correction.
        own = "[data-figure-id='ph-grid-photo'] img { filter: grayscale(1); }"
        page = self.open_photo_deck("#/2", css=own, init=(
            "localStorage.setItem('lecturedeck-photo:/webdeck/:Photo deck',"
            " JSON.stringify({brightness: 150, contrast: 100, all: true}))"))
        self.assertEqual(("grayscale(1)", "none"), (
            page.evaluate(grid, "ph-grid-photo"), page.evaluate(grid, "ph-drawn")))

    def test_photo_copy_keeps_the_slide_background_and_deck_filter(self):
        # A drawing with a transparent background and a deck.css invert must
        # read as on the slide, not as dark ink on the black stage.
        css = "body:not(.light-theme) [data-figure-id='ph-drawn'] img { filter: invert(1); }"
        page = self.open_photo_deck("#/2", css=css)
        state = self.open_photo(page, "#deck [data-figure-id='ph-drawn'] img")
        self.assertEqual("invert(1)", state["filter"])
        self.assertEqual("rgb(29, 32, 33)", page.evaluate(
            "getComputedStyle(document.querySelector('#photo-viewer .photo-media'))"
            ".backgroundColor"))
        page.keyboard.press("b")
        self.assertEqual("invert(1) brightness(110%) contrast(100%)", self.photo(page)["filter"])
        self.close_photo(page)
        # With all photos corrected, a photo's copy is corrected once, not twice.
        self.open_photo(page, "#deck [data-figure-id='ph-grid-photo'] img")
        page.keyboard.press("a")
        self.close_photo(page)
        state = self.open_photo(page, "#deck [data-figure-id='ph-grid-photo'] img")
        self.assertEqual("brightness(110%) contrast(100%)", state["filter"])
        self.close_photo(page)
        # In light mode the copy takes the light slide background.
        light = self.open_photo_deck("#/2", init=(
            "localStorage.setItem('lecturedeck-theme', 'light')"))
        self.open_photo(light, "#deck [data-figure-id='ph-drawn'] img")
        self.assertEqual("rgb(250, 247, 237)", light.evaluate(
            "getComputedStyle(document.querySelector('#photo-viewer .photo-media'))"
            ".backgroundColor"))

    def test_style_guide_photo_example(self):
        # The STYLE_GUIDE's own deck.css example, as published, for a figure
        # of this deck: kept out of the correction, still opening corrected.
        guide = (Path(__file__).resolve().parents[1] / "STYLE_GUIDE.md").read_text(
            encoding="utf-8").split("## Photos", 1)[1]
        css = re.search(r"```css\n(.*?)```", guide, re.S).group(1)
        self.assertIn('[data-figure-id="drawn-field"]', css)
        page = self.open_photo_deck("#/1", css=css.replace("drawn-field", "ph-photo"), init=(
            "localStorage.setItem('lecturedeck-photo:/webdeck/:Photo deck',"
            " JSON.stringify({brightness: 150, contrast: 100, all: true}))"))
        self.assertEqual("none", page.evaluate(
            "getComputedStyle(document.querySelector('#deck .figure-card img')).filter"))
        self.assertTrue(page.evaluate("document.body.classList.contains('photos-corrected')"))
        state = self.open_photo(page, "#deck .figure-card img")
        self.assertEqual("brightness(150%) contrast(100%)", state["filter"])

    def test_photo_viewer_never_moves_the_chrome(self):
        boxes = """() => Object.fromEntries(['#deck .page-number', '#deck .course-name',
          '#deck .source', '#deck .slide-foot', '#deck .slide-head', '#deck .slide-body',
          '#deck .figure-card', '#counter', '#controls-tools', '#appearance-button',
          '#laser-button', '#viewer-version', '#presentation-controls'].map(s => {
            const r = document.querySelector(s).getBoundingClientRect();
            return [s, [r.x, r.y, r.width, r.height]]; }))"""
        for size in ({"width": 1280, "height": 900}, {"width": 960, "height": 720}):
            with self.subTest(size=size):
                page = self.open_photo_deck("#/1", viewport=size)
                page.wait_for_function(
                    "document.querySelector('#controls-tools').getAnimations().length === 0")
                before = page.evaluate(boxes)
                self.open_photo(page, "#deck .figure-card img")
                page.keyboard.press("b")
                page.keyboard.press("+")
                self.assertEqual(before, page.evaluate(boxes))
                page.keyboard.press("a")
                self.close_photo(page)
                self.assertEqual(before, page.evaluate(boxes))
                page.keyboard.press("ArrowRight")
                self.assertEqual(before, page.evaluate(boxes))
        # A video's expand control is out of the slide's layout.
        clip = ["#deck .video-card", "#deck video", "#deck .video-card figcaption",
                "#deck .slide-body", "#deck .page-number"]
        rects = ("ss => ss.map(s => { const r = document.querySelector(s).getBoundingClientRect();"
                 " return [r.x, r.y, r.width, r.height]; })")
        page.evaluate("location.hash = '#/4'")
        page.wait_for_selector("#deck .photo-expand", state="attached")
        with_control = page.evaluate(rects, clip)
        page.evaluate("document.querySelectorAll('#deck .photo-expand').forEach(b => b.remove())")
        self.assertEqual(with_control, page.evaluate(rects, clip))

    def test_video_opens_from_its_expand_control_and_plays_on(self):
        if not self.recorded_clip():
            self.skipTest("this browser records no WebM")
        page = self.open_photo_deck("#/4", viewport={"width": 1280, "height": 800})
        page.wait_for_function("document.querySelector('#deck video').readyState >= 1")
        video, button = "#deck video", "#deck .photo-expand"
        page.wait_for_selector(button)
        # Small and on the video's top right corner.
        place = page.evaluate("""() => {
          const frame = document.querySelector('#deck .slide-frame').getBoundingClientRect();
          const scale = frame.width / 1280;
          const v = document.querySelector('#deck video').getBoundingClientRect();
          const b = document.querySelector('#deck .photo-expand').getBoundingClientRect();
          return [(v.right - b.right) / scale, (b.top - v.top) / scale, b.width / scale];
        }""")
        self.assertEqual([12, 12, 44], [round(value, 1) for value in place])
        self.assertEqual("Enlarge the video", page.get_attribute(button, "aria-label"))
        # A click on the video itself plays it, as always, and opens nothing.
        page.click(video)
        page.wait_for_function("() => { const v = document.querySelector('#deck video');"
                               " return !v.paused && v.currentTime > 0.3; }")
        self.assertFalse(self.photo(page)["open"])
        at = page.evaluate("document.querySelector('#deck video').currentTime")
        # The viewer's copy plays on from there.
        page.click(button)
        page.wait_for_selector("#photo-viewer[open]")
        page.wait_for_function("t => { const m = document.querySelector('#photo-viewer video');"
                               " return m && !m.paused && m.currentTime >= t; }", arg=at)
        state = self.photo(page)
        self.assertEqual(("video", "#/4", 4), (state["kind"], state["hash"], state["index"]))
        self.assert_fits(state)
        self.assertTrue(page.evaluate("document.querySelector('#deck video').paused"))
        self.assertTrue(page.evaluate("document.querySelector('#photo-viewer video').controls"))
        page.keyboard.press("b")
        self.assertEqual("brightness(110%) contrast(100%)", self.photo(page)["filter"])
        page.evaluate("""async () => { const m = document.querySelector('#photo-viewer video');
          m.pause(); m.currentTime = 2.25;
          await new Promise(r => m.addEventListener('seeked', r, {once: true})); }""")
        self.close_photo(page, "PageDown")
        # The slide's video waits, paused, where the viewer left it.
        page.wait_for_function(
            "Math.abs(document.querySelector('#deck video').currentTime - 2.25) < 0.05")
        self.assertEqual([True, "#/4", "BODY"], page.evaluate(
            "[document.querySelector('#deck video').paused, location.hash,"
            " document.activeElement.tagName]"))
        # A copy closed before it loaded never plays, unseen.
        page.evaluate("""async () => {
          window.__orphanPlays = 0;
          const play = HTMLMediaElement.prototype.play;
          HTMLMediaElement.prototype.play = function () {
            if (!this.isConnected) window.__orphanPlays += 1;
            return play.call(this);
          };
          const v = document.querySelector('#deck video');
          v.muted = true; v.currentTime = 0.2; await v.play();
          document.querySelector('#deck .photo-expand').click();
          dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}));
        }""")
        page.wait_for_timeout(800)
        self.assertEqual([False, 0], page.evaluate(
            "[document.querySelector('#photo-viewer').open, window.__orphanPlays]"))
        # A stepped video's control appears with its step.
        page.keyboard.press("ArrowRight")
        self.assertEqual(("#/5", True), (self.photo(page)["hash"], page.is_hidden(button)))
        page.keyboard.press("ArrowRight")
        page.wait_for_selector(button)
        self.assertEqual("#/5.1", self.photo(page)["hash"])
        page.keyboard.press("ArrowLeft")
        page.wait_for_selector(button, state="hidden")

    def test_photo_viewer_leaves_links_marked_images_demos_and_chrome_alone(self):
        page = self.open_photo_deck("#/3")
        page.click("#ph-off", force=True)
        page.wait_for_timeout(100)
        self.assertFalse(self.photo(page)["open"])
        # An image formula (img.math-display) is no photo, and an image in a
        # summary still opens its details.
        self.assertEqual("auto", page.evaluate(
            "getComputedStyle(document.querySelector('#ph-math')).cursor"))
        page.click("#ph-math")
        page.click("#ph-summary")
        page.wait_for_timeout(100)
        self.assertEqual([False, True], page.evaluate(
            "[document.querySelector('#photo-viewer').open,"
            " document.querySelector('#deck details').open]"))
        page.click("#ph-linked")
        page.wait_for_function("location.hash === '#/0'")
        self.assertFalse(self.photo(page)["open"])
        page.evaluate("location.hash = '#/6'")
        page.wait_for_selector("#deck .interactive-frame iframe")
        self.assertEqual(0, page.locator("#deck .photo-zoomable, #deck .photo-expand").count())
        if page.locator("#controls-toggle").is_visible():
            page.locator("#controls-toggle").click()
        page.click("#counter")
        self.assertFalse(self.photo(page)["open"])
        # The print page holds no viewer at all.
        printed = self.open_photo_deck("?print=1")
        printed.wait_for_function("window.LECTUREDECK_PRINT_READY === true")
        self.assertEqual(0, printed.locator(
            "#photo-viewer, .photo-expand, .photo-zoomable, .photo-content").count())

    def test_laser_points_over_the_photo(self):
        page = self.open_photo_deck("#/1", viewport={"width": 1280, "height": 800})
        page.keyboard.press("l")
        state = self.open_photo(page, "#deck .figure-card img")
        self.assertTrue(state["open"])
        self.assertTrue(page.evaluate("document.body.classList.contains('laser-active')"))
        page.mouse.move(500, 300)
        page.mouse.move(520, 310)
        page.wait_for_function("!document.querySelector('.laser-dot').hidden")
        dot = page.evaluate("""() => { const d = document.querySelector('.laser-dot');
          const r = d.getBoundingClientRect();
          return [d.parentElement.id, r.left + r.width / 2, r.top + r.height / 2]; }""")
        self.assertEqual("photo-viewer", dot[0])
        self.assertAlmostEqual(520, dot[1], delta=2)
        self.assertAlmostEqual(310, dot[2], delta=2)
        self.assertEqual("none", page.evaluate(
            "getComputedStyle(document.querySelector('#photo-viewer .photo-media')).cursor"))
        # L works inside the viewer too.
        page.keyboard.press("l")
        self.assertFalse(page.evaluate("document.body.classList.contains('laser-active')"))
        page.keyboard.press("l")
        self.close_photo(page)
        self.assertEqual(["BODY", True], page.evaluate(
            "[document.querySelector('.laser-dot').parentElement.tagName,"
            " document.body.classList.contains('laser-active')]"))

    def test_escape_leaving_full_screen_closes_the_photo_only(self):
        page = self.open_photo_deck("#/1")
        page.keyboard.press("f")
        page.wait_for_function("Boolean(document.fullscreenElement)"
                               " || document.body.classList.contains('pseudo-fullscreen')")
        if not page.evaluate("Boolean(document.fullscreenElement)"):
            self.skipTest("no native full screen in this browser")
        self.open_photo(page, "#deck .figure-card img")
        # Above the full-screen deck.
        self.assertTrue(page.evaluate(
            "document.querySelector('#photo-viewer')"
            ".contains(document.elementFromPoint(640, 300))"))
        # The browser takes Escape to leave full screen; it was meant for the photo.
        page.evaluate("document.exitFullscreen()")
        page.wait_for_selector("#photo-viewer", state="hidden")
        self.assertEqual([True, "#/1"], page.evaluate(
            "[document.querySelector('#overview').hidden, location.hash]"))

    def test_pacer_counts_the_photo_as_time_on_its_slide(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        page.route("**/deck.json", lambda route: route.fulfill(json=PHOTO_DECK))
        page.route("**/presentation-time.json", lambda route: route.fulfill(
            json={"start": "09:00", "end": "10:00", "timeZone": "UTC", "dates": ["2026-01-01"]}
        ))
        page.clock.install(time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc))
        page.goto(self.urls["json"] + "#/1")
        page.wait_for_selector("#pacing-button")
        page.clock.run_for(2000)
        page.click("#deck .figure-card img")
        page.wait_for_selector("#photo-viewer[open]")
        page.clock.run_for(5000)
        page.keyboard.press("PageDown")
        page.wait_for_selector("#photo-viewer", state="hidden")
        page.clock.run_for(2000)
        (entry,) = journal(page)
        record = entry["record"]
        # One unbroken visit to the slide, no pause, no slide change.
        self.assertEqual(["ph-figure"], [visit["slideId"] for visit in record["visits"]])
        self.assertGreaterEqual(record["visits"][0]["durationMs"], 9000)
        self.assertEqual([], record["pauses"])

    # Photo hotspots ------------------------------------------------------

    def open_hotspot_deck(self, fragment: str = "", deck: dict = HOTSPOT_DECK,
                          css: str | None = HOTSPOT_CSS, init: str | None = None,
                          within=None, **options):
        page = within.new_page(**options) if within else self.browser.new_page(**options)
        self.addCleanup(page.close)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual([], errors))
        if init:
            page.add_init_script(init)
        marked = marked_png(400, 240, PHOTO_MARKS)
        tall = marked_png(200, 400, TALL_MARKS)
        page.route("**/assets/marked.png", lambda route: route.fulfill(
            body=marked, content_type="image/png"))
        page.route("**/assets/tall.png", lambda route: route.fulfill(
            body=tall, content_type="image/png"))
        page.route("**/deck.json", lambda route: route.fulfill(json=deck))
        if css is not None:
            page.route("**/deck.css", lambda route: route.fulfill(
                body=css, content_type="text/css"))
        page.goto(self.urls["json"] + fragment)
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.wait_hotspots(page)
        return page

    def wait_hotspots(self, page) -> None:
        page.wait_for_function(
            "[...document.querySelectorAll('#deck img')].every(i => i.complete)"
            " && [...document.querySelectorAll('#deck .hotspot-layer')].every(l => !l.hidden)")

    def goto_slide(self, page, fragment: str) -> None:
        page.evaluate("f => { location.hash = f; }", fragment)
        page.wait_for_function(
            "i => document.querySelector('#deck .slide-frame')?.dataset.index === i",
            arg=fragment[2:].split(".")[0])
        self.wait_hotspots(page)

    def park_pointer(self, page) -> None:
        """The pointer on the viewer's bar (or the window's corner), no popup open."""
        bar = page.locator("#photo-viewer .photo-bar")
        if bar.is_visible():
            box = bar.bounding_box()
            page.mouse.move(box["x"] + 4, box["y"] + box["height"] - 4)
        else:
            page.mouse.move(2, 2)
        page.wait_for_function(
            "[...document.querySelectorAll('.hotspot-popup')].every(p => p.hidden)")

    def rings(self, page, viewer: bool = False) -> list[dict]:
        return page.evaluate(HOTSPOT_GEOMETRY, [HOTSPOTS_BY_FIGURE, viewer])

    def screen_pixels(self, page, points: list) -> list:
        data = base64.b64encode(page.screenshot()).decode()
        probe = self.browser.new_page()
        try:
            return probe.evaluate(SCREEN_PIXELS, [data, points])
        finally:
            probe.close()

    def assert_rings_on_marks(self, page, rings: list, marks: list) -> None:
        """Each ring sits on its spot of the picture: on the computed spot
        to half a pixel, as wide as its radius says, and on the coloured
        mark the screenshot shows there."""
        shown = [ring for ring in rings if ring["inside"]]
        for ring in rings:
            with self.subTest(ring=ring["label"]):
                self.assertAlmostEqual(ring["ex"], ring["cx"], delta=0.5)
                self.assertAlmostEqual(ring["ey"], ring["cy"], delta=0.5)
                self.assertAlmostEqual(ring["ew"], ring["w"], delta=0.5)
                self.assertAlmostEqual(ring["w"], ring["h"], delta=0.5)
                # A spot cropped away by object-fit is no target either.
                self.assertEqual(ring["inside"], ring["hit"])
        colours = {ring["label"]: rgb for ring, (_, _, rgb) in zip(rings, marks)}
        pixels = self.screen_pixels(page, [[ring["cx"], ring["cy"]] for ring in shown])
        for ring, pixel in zip(shown, pixels):
            with self.subTest(mark=ring["label"]):
                for got, want in zip(pixel, colours[ring["label"]]):
                    self.assertAlmostEqual(want, got, delta=14)

    def test_hotspots_sit_on_the_drawn_picture(self):
        # Two window sizes; a figure, a letterboxed portrait under a deck's
        # width and max-height, and object-fit cover with object-position,
        # padding and a border, where two spots are cropped away.
        slides = {"#/1": PHOTO_MARKS, "#/2": TALL_MARKS, "#/3": TALL_MARKS}
        for size in ({"width": 1280, "height": 800}, {"width": 960, "height": 720}):
            for fragment, marks in slides.items():
                with self.subTest(size=size, slide=fragment):
                    page = self.open_hotspot_deck(fragment, viewport=size)
                    rings = self.rings(page)
                    self.assertEqual(len(marks), len(rings))
                    self.assert_rings_on_marks(page, rings, marks)
                    if fragment == "#/2":
                        # The portrait really is letterboxed in a wider box.
                        self.assertEqual("300px", page.evaluate(
                            "getComputedStyle(document.querySelector('#deck img')).height"))
                    if fragment == "#/3":
                        self.assertEqual([False, True, True, False],
                                         [ring["inside"] for ring in rings])
        # Full screen grows the canvas; the rings follow the picture.
        page = self.open_hotspot_deck("#/1", viewport={"width": 1280, "height": 1000})
        layer = "document.querySelector('#deck .hotspot-layer').style.top"
        before = page.evaluate(layer)
        page.keyboard.press("f")
        page.wait_for_function("Boolean(document.fullscreenElement)"
                               " || document.body.classList.contains('pseudo-fullscreen')")
        page.wait_for_function(
            "document.querySelector('#deck .slide-frame').style.height === '1000px'")
        # The taller canvas gives the picture a taller box: it is centred
        # lower in it, and the rings with it.
        page.wait_for_function(f"{layer} !== {json.dumps(before)}")
        self.assert_rings_on_marks(page, self.rings(page), PHOTO_MARKS)

    def test_hotspot_hint_and_popup_on_the_slide(self):
        for theme, panel in (("dark", "rgb(40, 40, 40)"), ("light", "rgb(238, 231, 216)")):
            with self.subTest(theme=theme):
                page = self.open_hotspot_deck(
                    "#/1", viewport={"width": 1280, "height": 800}, reduced_motion="reduce",
                    init=f"localStorage.setItem('lecturedeck-theme', '{theme}')")
                rings = self.rings(page)
                # Invisible until the pointer is over the photo.
                self.assertEqual(["0", "0", "0"], page.evaluate(RING_OPACITY, "slide"))
                self.assertIsNone(page.evaluate(HOTSPOT_POPUP, "slide"))
                image = page.evaluate("""() => { const r = document.querySelector(
                  '#deck .figure-card img').getBoundingClientRect();
                  return {x: r.x, y: r.y, w: r.width, h: r.height}; }""")
                page.mouse.move(image["x"] + image["w"] * 0.5, image["y"] + image["h"] * 0.12)
                # Then a faint ring on every hotspot: the presenter's hint.
                self.assertEqual(["0.7", "0.7", "0.7"], page.evaluate(RING_OPACITY, "slide"))
                self.assertIsNone(page.evaluate(HOTSPOT_POPUP, "slide"))
                # A ring under the pointer shows its popup beside it.
                page.mouse.move(rings[0]["cx"], rings[0]["cy"])
                popup = page.evaluate(HOTSPOT_POPUP, "slide")
                self.assertEqual("Left person (1858–1947)Energy quanta, 1900.", popup["text"])
                self.assertIn("<strong>Left person</strong>", popup["html"])
                self.assertEqual(("1", "hotspot-popup-slide"), (
                    popup["ring"]["opacity"], popup["ring"]["describedBy"]))
                self.assertEqual(["1", "0.7", "0.7"], page.evaluate(RING_OPACITY, "slide"))
                self.assertIn("slide-frame", popup["host"])
                self.assert_popup_beside_its_ring(popup)
                # Caption-size text on the 1280x720 stage, in the theme's colours.
                self.assertEqual(22, popup["fontSize"])
                self.assertEqual(panel, popup["background"])
                # The next ring moves it; MathML and links render.
                page.mouse.move(rings[1]["cx"], rings[1]["cy"], steps=4)
                popup = page.evaluate(HOTSPOT_POPUP, "slide")
                self.assertEqual("Right person", popup["ring"]["label"])
                self.assertEqual(1, page.locator("#hotspot-popup-slide math").count())
                self.assert_popup_beside_its_ring(popup)
                # A ring with only a label shows the label.
                page.mouse.move(rings[2]["cx"], rings[2]["cy"], steps=4)
                popup = page.evaluate(HOTSPOT_POPUP, "slide")
                self.assertEqual("Corner person", popup["text"])
                self.assert_popup_beside_its_ring(popup)
                # Off the photo, the popup and the hint go.
                page.mouse.move(60, 400, steps=4)
                page.wait_for_selector("#hotspot-popup-slide", state="hidden")
                self.assertEqual(["0", "0", "0"], page.evaluate(RING_OPACITY, "slide"))
                # The pointer can travel from a ring into its popup to click a link.
                page.mouse.move(rings[1]["cx"], rings[1]["cy"], steps=4)
                link = page.locator("#hs-link").bounding_box()
                page.mouse.move(link["x"] + link["width"] / 2, link["y"] + link["height"] / 2,
                                steps=6)
                page.mouse.click(link["x"] + link["width"] / 2, link["y"] + link["height"] / 2)
                page.wait_for_function(
                    "document.querySelector('#deck .slide-frame').dataset.index === '5'")
                self.assertFalse(self.photo(page)["open"])
                self.assertIsNone(page.evaluate(HOTSPOT_POPUP, "slide"))
        # A keyboard user: Enter on a focused ring shows its popup, and the
        # deck's paging keys still page.
        self.goto_slide(page, "#/1")
        page.mouse.move(5, 5)
        page.focus("#deck .hotspot >> nth=1")
        page.keyboard.press("Enter")
        self.assertEqual("Right person", page.evaluate(HOTSPOT_POPUP, "slide")["ring"]["label"])
        page.keyboard.press("Space")
        page.wait_for_function("location.hash === '#/2'")

    def assert_popup_beside_its_ring(self, popup: dict) -> None:
        ring = popup["ring"]
        # Inside the slide, with its margin.
        self.assertGreaterEqual(popup["left"], 7.5)
        self.assertGreaterEqual(popup["top"], 7.5)
        self.assertLessEqual(popup["right"], popup["width"] - 7.5)
        self.assertLessEqual(popup["bottom"], popup["height"] - 7.5)
        # Beside its ring, never over it.
        apart = (popup["left"] >= ring["right"] or popup["right"] <= ring["left"]
                 or popup["top"] >= ring["bottom"] or popup["bottom"] <= ring["top"])
        self.assertTrue(apart, popup)
        if popup["side"] in ("left", "right"):
            centre = (ring["top"] + ring["bottom"]) / 2
            self.assertTrue(popup["top"] - 0.5 <= centre <= popup["bottom"] + 0.5, popup)

    def test_hotspot_rings_key_toggles_the_hint_for_the_whole_deck(self):
        page = self.open_hotspot_deck("#/1", viewport={"width": 1280, "height": 800},
                                      reduced_motion="reduce")
        rings = self.rings(page)
        image = page.locator("#deck .figure-card img").bounding_box()
        page.mouse.move(image["x"] + image["width"] / 2, image["y"] + 10)
        self.assertEqual(["0.7"] * 3, page.evaluate(RING_OPACITY, "slide"))
        page.keyboard.press("h")
        self.assertEqual(["0"] * 3, page.evaluate(RING_OPACITY, "slide"))
        self.assertTrue(page.evaluate("document.body.classList.contains('hotspot-rings-off')"))
        # A hotspot under the pointer still shows its own ring and popup.
        page.mouse.move(rings[0]["cx"], rings[0]["cy"], steps=4)
        self.assertEqual(["1", "0", "0"], page.evaluate(RING_OPACITY, "slide"))
        self.assertEqual("Left person", page.evaluate(HOTSPOT_POPUP, "slide")["ring"]["label"])
        # For the whole deck: another slide, the viewer, a reload of the tab.
        page.keyboard.press("PageDown")
        self.wait_hotspots(page)
        page.mouse.move(*self.ring_centre(page, 1))
        self.assertEqual(["0", "1", "0", "0"], page.evaluate(RING_OPACITY, "slide"))
        page.reload()
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        self.wait_hotspots(page)
        self.assertEqual(["off", True], page.evaluate(
            "[sessionStorage.getItem('lecturedeck-hotspot-rings:/webdeck/:Hotspot deck'),"
            " document.body.classList.contains('hotspot-rings-off')]"))
        # Modified keys are not the switch.
        page.keyboard.press("Control+h")
        page.keyboard.press("Alt+h")
        self.assertTrue(page.evaluate("document.body.classList.contains('hotspot-rings-off')"))
        # The Appearance dialog carries the same switch.
        page.keyboard.press("t")
        page.wait_for_selector("#appearance-dialog[open]")
        checkbox = page.get_by_label("Hint rings on photo hotspots (H)", exact=True)
        self.assertFalse(checkbox.is_checked())
        checkbox.check()
        # Turned on, every ring shows a moment without the pointer.
        self.assertTrue(page.evaluate("document.body.classList.contains('hotspot-rings-flash')"))
        page.keyboard.press("Escape")
        page.wait_for_selector("#appearance-dialog", state="hidden")
        self.park_pointer(page)
        self.assertEqual(["0.7"] * 4, page.evaluate(RING_OPACITY, "slide"))
        page.wait_for_function("!document.body.classList.contains('hotspot-rings-flash')")
        self.assertEqual(["0"] * 4, page.evaluate(RING_OPACITY, "slide"))
        # H in the viewer too.
        self.goto_slide(page, "#/1")
        image = page.locator("#deck .figure-card img").bounding_box()
        page.mouse.click(image["x"] + image["width"] / 2, image["y"] + 10)
        page.wait_for_selector("#photo-viewer[open]")
        page.keyboard.press("h")
        self.assertTrue(page.evaluate("document.body.classList.contains('hotspot-rings-off')"))
        self.assertTrue(self.photo(page)["open"])
        page.keyboard.press("h")
        self.assertFalse(page.evaluate("document.body.classList.contains('hotspot-rings-off')"))
        # A deck without hotspots offers no switch.
        plain = self.open_photo_deck("#/1")
        self.assertEqual(0, plain.locator("#hotspot-rings-input").count())

    def ring_centre(self, page, n: int, viewer: bool = False) -> tuple[float, float]:
        selector = "#photo-viewer .hotspot" if viewer else "#deck .hotspot"
        box = page.locator(selector).nth(n).bounding_box()
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def test_hotspots_follow_zoom_and_pan_in_the_photo_viewer(self):
        page = self.open_hotspot_deck("#/1", viewport={"width": 1600, "height": 1000},
                                      reduced_motion="reduce")
        image = page.locator("#deck .figure-card img").bounding_box()
        # A click on the photo, or on a ring, opens it.
        page.mouse.move(*self.ring_centre(page, 0))
        page.mouse.click(*self.ring_centre(page, 0))
        page.wait_for_selector("#photo-viewer[open]")
        self.assertIsNone(page.evaluate(HOTSPOT_POPUP, "slide"))
        self.assertEqual(3, page.locator("#photo-viewer .hotspot").count())
        self.wait_drawn(page)
        self.park_pointer(page)
        self.assert_rings_on_marks(page, self.rings(page, viewer=True), PHOTO_MARKS)
        # Zoom around the cursor and pan: the rings follow exactly.
        media = self.photo(page)["media"]
        page.mouse.move(media["x"] + media["w"] * 0.55, media["y"] + media["h"] * 0.75)
        page.mouse.wheel(0, -300)
        page.wait_for_function("document.querySelector('#photo-viewer').dataset.zoomed === 'true'")
        self.park_pointer(page)
        self.assert_rings_on_marks(page, self.rings(page, viewer=True), PHOTO_MARKS)
        page.mouse.move(800, 400)
        page.mouse.down()
        page.mouse.move(700, 450, steps=4)
        page.mouse.up()
        self.assertTrue(self.photo(page)["open"])
        self.park_pointer(page)
        self.assert_rings_on_marks(page, self.rings(page, viewer=True), PHOTO_MARKS)
        page.keyboard.press("0")
        # Hover shows the popup in the stage, at the slide's text size.
        page.mouse.move(*self.ring_centre(page, 0, viewer=True), steps=4)
        popup = page.evaluate(HOTSPOT_POPUP, "viewer")
        self.assertEqual(("Left person", "photo-stage"), (popup["ring"]["label"], popup["host"]))
        self.assert_popup_beside_its_ring(popup)
        scale = min(1600 / 1280, 1000 / 720)
        self.assertAlmostEqual(22 * scale, popup["fontSize"], delta=0.05)
        self.assertEqual("rgb(235, 219, 178)", popup["color"])
        # Brightness and contrast never reach the popup or the rings.
        page.keyboard.press("b")
        page.keyboard.press("c")
        self.assertEqual("brightness(110%) contrast(110%)", self.photo(page)["filter"])
        self.assertEqual(["none"], page.evaluate("""() => { const out = new Set();
          for (let n = document.querySelector('#hotspot-popup-viewer'); n; n = n.parentElement)
            out.add(getComputedStyle(n).filter);
          for (let n = document.querySelector('#photo-viewer .hotspot'); n; n = n.parentElement)
            out.add(getComputedStyle(n).filter);
          return [...out]; }"""))
        # A popup opened from the keyboard stays, and follows its ring when
        # the photo zooms.
        self.park_pointer(page)
        page.focus("#photo-viewer .hotspot >> nth=0")
        page.keyboard.press("Enter")
        before = page.evaluate(HOTSPOT_POPUP, "viewer")
        self.assertEqual("Left person", before["ring"]["label"])
        page.keyboard.press("+")
        after = page.evaluate(HOTSPOT_POPUP, "viewer")
        self.assertEqual("Left person", after["ring"]["label"])
        self.assertNotEqual(before["ring"]["left"], after["ring"]["left"])
        self.assert_popup_beside_its_ring(after)
        self.assertTrue(self.photo(page)["open"])
        # A double-click on a ring zooms like one on the picture.
        page.keyboard.press("0")
        page.mouse.dblclick(*self.ring_centre(page, 1, viewer=True))
        self.assertEqual("Zoom 2.0×", self.photo(page)["values"][2])
        # The laser keeps pointing, and the popup still follows the pointer.
        page.keyboard.press("l")
        page.mouse.move(5, 5)
        page.mouse.move(*self.ring_centre(page, 1, viewer=True), steps=4)
        self.assertEqual("Right person", page.evaluate(HOTSPOT_POPUP, "viewer")["ring"]["label"])
        self.assertEqual("photo-viewer", page.evaluate(
            "document.querySelector('.laser-dot').parentElement.id"))
        self.assertFalse(page.evaluate("document.querySelector('.laser-dot').hidden"))
        page.keyboard.press("l")
        # Paging and clicker keys only close it, on the same slide; no ring
        # or popup outlives it.
        state = self.close_photo(page, "PageDown")
        self.assertEqual(("#/1", False), (state["hash"], state["open"]))
        self.assertEqual(0, page.locator("#photo-viewer .hotspot, #hotspot-popup-viewer").count())
        page.keyboard.press("PageDown")
        page.wait_for_function("location.hash === '#/2'")
        # A plain image opens with no rings.
        self.goto_slide(page, "#/4.1")
        page.click("#deck [data-figure-id='hs-plain'] img")
        page.wait_for_selector("#photo-viewer[open]")
        self.assertEqual(0, page.locator("#photo-viewer .hotspot").count())
        page.keyboard.press("Escape")
        self.assertTrue(image["width"] > 0)

    def wait_drawn(self, page) -> None:
        page.wait_for_function("""() => {
          const m = document.querySelector('#photo-viewer .photo-media');
          const l = document.querySelector('#photo-viewer .hotspot-layer');
          return m && m.complete && l && l.style.width === m.style.width; }""")

    def test_a_tap_on_a_ring_shows_its_popup(self):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800}, has_touch=True)
        self.addCleanup(context.close)
        page = self.open_hotspot_deck("#/1", within=context)
        if page.evaluate("matchMedia('(hover: none)').matches"):
            # No hover to wait for: the hint shows from the start.
            page.wait_for_function("getComputedStyle(document.querySelector('#deck .hotspot'))"
                                   ".opacity === '0.7'")
        page.touchscreen.tap(*self.ring_centre(page, 0))
        page.wait_for_selector("#hotspot-popup-slide:not([hidden])")
        popup = page.evaluate(HOTSPOT_POPUP, "slide")
        self.assertEqual("Left person", popup["ring"]["label"])
        self.assert_popup_beside_its_ring(popup)
        # The tap neither opened the photo nor paged.
        self.assertEqual((False, "#/1"), (self.photo(page)["open"], self.photo(page)["hash"]))
        # Another ring moves it; a second tap on the same ring closes it.
        page.touchscreen.tap(*self.ring_centre(page, 1))
        self.assertEqual("Right person", page.evaluate(HOTSPOT_POPUP, "slide")["ring"]["label"])
        page.touchscreen.tap(*self.ring_centre(page, 1))
        page.wait_for_selector("#hotspot-popup-slide", state="hidden")
        # A tap anywhere else lets it go.
        page.touchscreen.tap(*self.ring_centre(page, 0))
        page.wait_for_selector("#hotspot-popup-slide:not([hidden])")
        claim = page.locator("#deck .claim").bounding_box()
        page.touchscreen.tap(claim["x"] + 10, claim["y"] + 10)
        page.wait_for_selector("#hotspot-popup-slide", state="hidden")
        self.assertEqual("#/1", self.photo(page)["hash"])
        # A tap on the photo away from the rings opens the viewer, where a
        # tap on a ring shows its popup and a tap on the picture hides it.
        image = page.locator("#deck .figure-card img").bounding_box()
        page.touchscreen.tap(image["x"] + image["width"] / 2, image["y"] + 8)
        page.wait_for_selector("#photo-viewer[open]")
        self.wait_drawn(page)
        page.touchscreen.tap(*self.ring_centre(page, 2, viewer=True))
        page.wait_for_selector("#hotspot-popup-viewer:not([hidden])")
        self.assertEqual("Corner person", page.evaluate(HOTSPOT_POPUP, "viewer")["text"])
        media = self.photo(page)["media"]
        page.touchscreen.tap(media["x"] + media["w"] / 2, media["y"] + 8)
        page.wait_for_selector("#hotspot-popup-viewer", state="hidden")
        self.assertTrue(self.photo(page)["open"])

    def test_hotspots_never_move_anything(self):
        boxes = """() => Object.fromEntries(['#deck .page-number', '#deck .course-name',
          '#deck .source', '#deck .slide-foot', '#deck .slide-head', '#deck .slide-body',
          '#deck .copy', '#deck .claim', '#deck .figure-stack', '#deck .figure-card',
          '#deck .figure-card img', '#deck .figure-card figcaption', '#counter',
          '#controls-tools', '#appearance-button', '#presentation-controls'].map(s => {
            const r = document.querySelector(s).getBoundingClientRect();
            return [s, [r.x, r.y, r.width, r.height]]; }))"""
        bare = {**HOTSPOT_DECK, "slides": [
            {**slide, "figure": {k: v for k, v in slide["figure"].items() if k != "hotspots"}}
            if "figure" in slide else slide for slide in HOTSPOT_DECK["slides"]]}
        for size in ({"width": 1280, "height": 900}, {"width": 960, "height": 720}):
            with self.subTest(size=size):
                plain = self.open_hotspot_deck("#/1", deck=bare, viewport=size)
                plain.wait_for_function(
                    "document.querySelector('#controls-tools').getAnimations().length === 0")
                self.assertEqual(0, plain.locator(".hotspot").count())
                expected = plain.evaluate(boxes)
                page = self.open_hotspot_deck("#/1", viewport=size)
                page.wait_for_function(
                    "document.querySelector('#controls-tools').getAnimations().length === 0")
                self.assertEqual(expected, page.evaluate(boxes))
                page.mouse.move(*self.ring_centre(page, 0))
                self.assertIsNotNone(page.evaluate(HOTSPOT_POPUP, "slide"))
                self.assertEqual(expected, page.evaluate(boxes))
                page.keyboard.press("h")
                page.keyboard.press("h")
                self.assertEqual(expected, page.evaluate(boxes))
                page.mouse.click(*self.ring_centre(page, 0))
                page.wait_for_selector("#photo-viewer[open]")
                page.mouse.move(*self.ring_centre(page, 0, viewer=True))
                self.assertEqual(expected, page.evaluate(boxes))
                self.close_photo(page)
                self.assertEqual(expected, page.evaluate(boxes))

    def test_hotspots_step_print_and_overview(self):
        page = self.open_hotspot_deck("#/4", viewport={"width": 1280, "height": 800},
                                      reduced_motion="reduce")
        stepped = "#deck .hotspot-layer[data-figure-id='hs-step'] .hotspot"
        # A stepped figure's rings wait hidden with it, and are no target.
        self.assertEqual(["hidden", "hidden"], page.evaluate(
            "s => [...document.querySelectorAll(s)].map(r => getComputedStyle(r).visibility)",
            stepped))
        self.assertFalse(any(ring["hit"] for ring in self.rings(page)))
        page.keyboard.press("ArrowRight")
        self.assertEqual("#/4.1", self.photo(page)["hash"])
        rings = self.rings(page)
        self.assertTrue(all(ring["hit"] for ring in rings))
        self.assert_rings_on_marks(page, rings, PHOTO_MARKS[:2])
        page.mouse.move(rings[0]["cx"], rings[0]["cy"])
        self.assertIsNotNone(page.evaluate(HOTSPOT_POPUP, "slide"))
        # Stepped back out of view, its popup goes with it.
        page.keyboard.press("ArrowLeft")
        self.assertEqual("#/4", self.photo(page)["hash"])
        self.assertIsNone(page.evaluate(HOTSPOT_POPUP, "slide"))
        # The overview shows the photos without rings.
        page.keyboard.press("o")
        page.wait_for_selector(".overview-card")
        self.assertEqual(0, page.locator("#overview .hotspot, #overview .hotspot-layer").count())
        self.assertGreater(page.locator("#overview [data-figure-id='hs-photo'] img").count(), 0)
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#overview').hidden")
        # Printing a live slide shows the photo without rings or popup.
        self.goto_slide(page, "#/1")
        page.mouse.move(*self.ring_centre(page, 0))
        self.assertIsNotNone(page.evaluate(HOTSPOT_POPUP, "slide"))
        page.emulate_media(media="print")
        self.assertEqual(["none", "none", "block"], page.evaluate(
            "['#deck .hotspot-layer', '#hotspot-popup-slide', '#deck .figure-card img']"
            ".map(s => getComputedStyle(document.querySelector(s)).display)"))
        page.emulate_media(media="screen")
        # Print pages and PDF exports hold none of it.
        printed = self.open_photo_deck("?print=1", deck=HOTSPOT_DECK)
        printed.wait_for_function("window.LECTUREDECK_PRINT_READY === true")
        self.assertEqual(0, printed.locator(
            ".hotspot, .hotspot-layer, .hotspot-popup, .has-hotspots").count())
        self.assertGreater(printed.locator("[data-figure-id='hs-photo'] img").count(), 0)


PACING_DECK = {
    "deck": 1,
    "meta": {"title": "Pacing", "section": "PACING", "opening": "OPENING"},
    "slides": [
        {"id": "p-title", "type": "title", "title": "Pacing", "claim": "Opening slide."},
        {"id": "p-figure", "title": "Part one",
         "figure": {"id": "fig-1", "src": "assets/figure.png", "alt": "Figure"}},
        {"id": "p-middle", "type": "section", "title": "Middle"},
        {"id": "p-two", "title": "Part two", "claim": "Second part."},
        {"id": "p-three", "title": "Part three", "claim": "Third part."},
        {"id": "p-backup", "type": "section", "title": "Backup", "appendix": True},
        {"id": "p-extra", "title": "Backup extra", "claim": "Backup slide."},
    ],
}
PACING_TIME = {"start": "09:00", "end": "09:02", "timeZone": "UTC", "dates": ["2026-01-01"]}
WEBDRIVER_OFF = "Object.defineProperty(Navigator.prototype, 'webdriver', {get: () => false})"
RECORD_NAME = re.compile(r"^2026-01-01_\d{4}_pacing_[0-9a-f]{12}\.json$")

# A stand-in for the serve-only sink, for policy tests that must not depend
# on the server: it logs every save and answers what the test asks for.
STUB_SINK = """(() => {
  window.__pacingSent = [];
  window.__pacingReply = null;
  const sink = {
    version: 1, unit: "pacing", inert: null,
    probe: async () => ({ok: true, status: 200}),
    save: async (record, options) => {
      const reply = window.__pacingReply && window.__pacingReply(record);
      window.__pacingSent.push({segment: record.segment, rev: record.rev, at: Date.now(),
        keepalive: Boolean(options && options.keepalive), status: reply ? reply.status : 200});
      return reply || {ok: true, status: 200, rev: record.rev, savedAt: new Date().toISOString(),
        file: `pacing-records/${record.date}_${record.opened}_pacing_${record.segment}.json`};
    },
  };
  Object.defineProperty(window, "lecturedeckPacingSink", {value: Object.freeze(sink)});
})();"""


def build_pacing_unit(unit: Path) -> None:
    webdeck = unit / "webdeck"
    (webdeck / "assets").mkdir(parents=True)
    (webdeck / "assets" / "figure.png").write_bytes(png(320, 180, (131, 165, 152)))
    (webdeck / "deck.json").write_text(json.dumps(PACING_DECK), encoding="utf-8")
    (webdeck / "presentation-time.json").write_text(json.dumps(PACING_TIME), encoding="utf-8")


def pacing_segment(**changes) -> dict:
    """A valid live segment for 2026-01-01 on the pacing unit."""
    record = {
        "schema": 2, "kind": "lecturedeck-pacing-segment", "segment": "0123456789ab",
        "rev": 3, "unit": "pacing", "path": "/webdeck/", "deck": "Pacing", "viewer": __version__,
        "date": "2026-01-01", "opened": "0900", "timeZone": "UTC",
        "slot": {"start": "09:00", "end": "09:02", "startAt": "2026-01-01T09:00:00.000Z",
                 "endAt": "2026-01-01T09:02:00.000Z"},
        "window": {"before": 30, "after": 60, "from": "2026-01-01T08:30:00.000Z",
                   "to": "2026-01-01T10:02:00.000Z"},
        "slides": {"p-title": {"number": 1, "label": "1", "title": "Pacing", "section": "Opening"}},
        "visits": [{"slideId": "p-title", "startedAt": "2026-01-01T09:00:00.000Z",
                    "durationMs": 5000, "phase": "slot"}],
        "pauses": [],
        "fullscreenMs": 0,
    }
    record.update(changes)
    return record


def lecture_segment() -> dict:
    """A long synthetic lecture: 57 main slides in six sections, 92 backups."""
    sections = ["Opening", "Part A", "Part B", "Part C", "Part D", "Part E"]
    start = epoch_ms("2026-01-01T15:00:00.000Z")
    slides, visits, t = {}, [], start
    for n in range(1, 58):
        slides[f"m{n}"] = {"number": n, "label": str(n), "title": f"Main slide {n}",
                           "section": sections[min((n - 1) // 10, 5)]}
        visits.append({"slideId": f"m{n}", "startedAt": iso_ms(t), "durationMs": 70000,
                       "phase": "slot"})
        t += 70000
    for n in range(1, 93):
        slides[f"b{n}"] = {"number": 57 + n, "label": f"B{n}", "title": f"Backup slide {n}",
                           "section": "Backup", "backup": True}
        visits.append({"slideId": f"b{n}", "startedAt": iso_ms(t), "durationMs": 3000,
                       "phase": "slot"})
        t += 3000
    return pacing_segment(
        segment="feedc0ffee00", rev=210, opened="1500",
        slot={"start": "15:00", "end": "16:30", "startAt": "2026-01-01T15:00:00.000Z",
              "endAt": "2026-01-01T16:30:00.000Z"},
        window={"before": 30, "after": 60, "from": "2026-01-01T14:30:00.000Z",
                "to": "2026-01-01T17:30:00.000Z"},
        slides=slides, visits=visits,
    )


def seed_script(items: dict[str, object], once: str | None = None) -> str:
    """An init script writing localStorage items, optionally only once."""
    body = "".join(
        f"localStorage.setItem({json.dumps(key)}, {json.dumps(json.dumps(value))});"
        for key, value in items.items()
    )
    if once:
        flag = json.dumps(once)
        return f"if (!localStorage.getItem({flag})) {{ {body} localStorage.setItem({flag}, '1'); }}"
    return body


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright is not installed")
class PacingBrowserTest(unittest.TestCase):
    """The pacing recorder, its report, and saving through the serve-only sink.

    It has its own temporary root, so the smoke suite's selector is unchanged.
    Pages run on a paused Playwright clock: time moves only with run_for, so
    every recorded instant is exact. Contexts report navigator.webdriver as
    false unless a test is about automation, because the sink is inert under
    automation.
    """

    @classmethod
    def setUpClass(cls):
        cls._root = tempfile.TemporaryDirectory()
        root = Path(cls._root.name)
        cls.unit = root / "decks" / "pacing"
        build_pacing_unit(cls.unit)
        other = root / "other"
        other.mkdir()
        build_json_unit(other)
        cls.servers = []

        def start(server) -> str:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cls.servers.append(server)
            return f"http://127.0.0.1:{server.server_address[1]}"

        cls.origin = start(make_server(cls.unit, "127.0.0.1", 0, livereload=False, quiet=True))
        cls.url = cls.origin + "/webdeck/"
        cls.selector = start(
            make_selector_server(root / "decks", "127.0.0.1", 0, livereload=False, quiet=True)
        )
        cls.other_origin = start(make_server(other, "127.0.0.1", 0, livereload=False, quiet=True))
        original_cwd = Path.cwd()
        try:
            try:
                os.chdir(root)
                cls._playwright = sync_playwright().start()
                cls.browser = cls._playwright.chromium.launch()
            finally:
                os.chdir(original_cwd)
        except Exception as exc:  # browser binaries absent
            cls._playwright.stop()
            for server in cls.servers:
                server.shutdown()
                server.server_close()
            cls._root.cleanup()
            raise unittest.SkipTest(f"chromium is not installed ({exc})")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
            cls._playwright.stop()
            for server in cls.servers:
                server.shutdown()
                server.server_close()
            cls._root.cleanup()

    def setUp(self):
        shutil.rmtree(self.unit / "pacing-records", ignore_errors=True)

    def context(self, automation: bool = False, **options):
        context = self.browser.new_context(**options)
        self.addCleanup(context.close)
        if not automation:
            context.add_init_script(WEBDRIVER_OFF)
        return context

    def open_at(self, context, moment: datetime | None, url: str | None = None, *, sink: str = ""):
        """A page whose clock is paused at `moment` before the deck loads.

        The clock belongs to the context: a second page passes None and
        shares it, since installing it again would step the first page's
        clock backwards.
        """
        page = context.new_page()
        if sink:
            # Keep the real sink out; the stub stands in for it.
            page.route("**/__lecturedeck/pacing-sink.js",
                       lambda route: route.fulfill(body="", content_type="text/javascript"))
            page.add_init_script(sink)
        if moment is not None:
            page.clock.install(time=moment)
            page.clock.pause_at(moment)
        page.goto(url or self.url)
        page.wait_for_selector("#pacing-button", state="attached")
        return page

    def open_report(self, page) -> None:
        page.evaluate("document.querySelector('#pacing-button').click()")
        page.wait_for_selector("#pacing-dialog[open]")

    def disk(self, page) -> list[dict]:
        """Records on disk for the segments in `page`'s journal.

        A closing page from the previous test may still land a keepalive
        save after setUp cleared the folder, so tests never count files
        they did not record.
        """
        mine = {entry["record"]["segment"] for entry in journal(page)}
        folder = self.unit / "pacing-records"
        if not folder.is_dir():
            return []
        records = []
        for path in sorted(folder.glob("*.json")):
            if path.stem.rsplit("_", 1)[-1] in mine:
                records.append(json.loads(path.read_text(encoding="utf-8")) | {"_name": path.name})
        return records

    def wait_disk(self, page, predicate, timeout: float = 10.0) -> list[dict]:
        deadline = time.monotonic() + timeout
        while True:
            records = self.disk(page)
            if predicate(records):
                return records
            if time.monotonic() > deadline:
                found = [(record["segment"], record["rev"]) for record in records]
                self.fail(f"pacing-records never matched: {found}")
            time.sleep(0.1)

    def sent(self, page) -> list[dict]:
        return page.evaluate("window.__pacingSent")

    def sends(self, page, count: int) -> None:
        """Wait for exactly `count` stub saves, then confirm no more followed."""
        page.wait_for_function(f"window.__pacingSent.length >= {count}")
        self.assertEqual(count, len(self.sent(page)))

    def status(self, page) -> tuple[str, str]:
        return (page.get_attribute("#pacing-status", "data-state"),
                page.text_content("#pacing-status"))

    def test_pacer_saves_to_disk_without_a_button(self):
        page = self.open_at(self.context(), utc(8, 59, 50))
        downloads = []
        page.on("download", lambda download: downloads.append(download))
        page.clock.run_for(10_000)
        page.keyboard.press("ArrowRight")
        with page.expect_response(lambda r: r.request.method == "POST"):
            page.clock.run_for(140_000)  # 20 s past 09:02
        (record,) = self.wait_disk(
            page,
            lambda records: len(records) == 1
            and any(v["phase"] == "after" and v["durationMs"] for v in records[0]["visits"]),
        )
        self.assertTrue(record["_name"].startswith("2026-01-01_0859_pacing_"), record["_name"])
        self.assertRegex(record["_name"], RECORD_NAME)
        self.assertEqual(f"2026-01-01_0859_pacing_{record['segment']}.json", record["_name"])
        self.assertEqual(
            ("pacing", "/webdeck/", "0859"), (record["unit"], record["path"], record["opened"])
        )
        self.assertIn("savedBy", record)
        visits = record["visits"]
        self.assertEqual(
            ["before", "slot", "after"], list(dict.fromkeys(v["phase"] for v in visits))
        )
        # Unbroken: each visit ends exactly where the next one starts.
        for first, second in zip(visits, visits[1:]):
            self.assertEqual(visit_end(first), second["startedAt"])
        before = [v for v in visits if v["phase"] == "before"]
        slot = [v for v in visits if v["phase"] == "slot"]
        after = [v for v in visits if v["phase"] == "after"]
        self.assertEqual("2026-01-01T09:00:00.000Z", visit_end(before[-1]))
        self.assertEqual("2026-01-01T09:00:00.000Z", slot[0]["startedAt"])
        self.assertEqual("2026-01-01T09:02:00.000Z", visit_end(slot[-1]))
        self.assertEqual("2026-01-01T09:02:00.000Z", after[0]["startedAt"])
        span = epoch_ms(visit_end(visits[-1])) - epoch_ms(visits[0]["startedAt"])
        self.assertAlmostEqual(span, sum(v["durationMs"] for v in visits), delta=1000)
        self.assertEqual([], downloads)

    def test_pacer_window_edges(self):
        page = self.open_at(self.context(), utc(8, 29, 58))
        recording = lambda: page.get_attribute("#pacing-button", "data-recording")  # noqa: E731
        page.clock.run_for(1000)
        self.assertEqual("false", recording())  # 08:29:59
        page.clock.run_for(1000)
        self.assertEqual("true", recording())  # 08:30:00
        page.clock.pause_at(utc(10, 1, 50))
        page.clock.run_for(9000)
        self.assertEqual("true", recording())  # 10:01:59
        page.clock.run_for(1000)
        self.assertEqual("false", recording())  # 10:02:00
        (entry,) = journal(page)
        record = entry["record"]
        self.assertEqual("2026-01-01T08:30:00.000Z", record["window"]["from"])
        self.assertEqual("2026-01-01T10:02:00.000Z", record["window"]["to"])
        self.assertEqual("2026-01-01T08:30:00.000Z", record["visits"][0]["startedAt"])
        self.assertEqual(record["window"]["to"], visit_end(record["visits"][-1]))
        self.assertEqual("after", record["visits"][-1]["phase"])
        page.clock.run_for(5000)
        self.assertEqual(record["rev"], journal(page)[0]["record"]["rev"])

    def test_pacer_gaps_are_never_credited(self):
        page = self.open_at(self.context(), utc(8, 40))
        page.clock.run_for(3000)
        page.clock.fast_forward(5 * 60_000)  # a closed lid: both clocks jump
        page.clock.run_for(2000)
        page.clock.set_system_time(utc(9, 45, 5))  # a clock step: only Date jumps
        page.clock.run_for(3000)
        (entry,) = journal(page)
        record = entry["record"]
        self.assertEqual(
            [("08:40:00", 3000, "before"), ("08:45:03", 2000, "before"),
             ("09:45:06", 2000, "after")],
            [(v["startedAt"][11:19], v["durationMs"], v["phase"]) for v in record["visits"]],
        )
        self.assertEqual(
            [("08:40:03", 300_000, "suspended"), ("08:45:05", 3_601_000, "clock")],
            [(p["startedAt"][11:19], p["durationMs"], p["why"]) for p in record["pauses"]],
        )
        # A closed lid while the overview is open is still a suspension: the
        # overview pause ends at the gap and starts again on waking.
        page = self.open_at(self.context(), utc(8, 50, 10))
        page.clock.run_for(3000)
        page.keyboard.press("o")
        page.clock.run_for(1000)
        page.clock.fast_forward(5 * 60_000)
        page.clock.run_for(2000)
        (entry,) = journal(page)
        self.assertEqual(
            [("08:50:13", 1000, "overview"), ("08:50:14", 300_000, "suspended"),
             ("08:55:14", 2000, "overview")],
            [(p["startedAt"][11:19], p["durationMs"], p["why"]) for p in entry["record"]["pauses"]],
        )
        self.assertEqual([("08:50:10", 3000)], [
            (v["startedAt"][11:19], v["durationMs"]) for v in entry["record"]["visits"]])

    def test_pacer_reload_and_abrupt_close_recover(self):
        context = self.context()
        page = self.open_at(context, utc(9, 0, 10))
        page.clock.run_for(5000)
        page.reload()
        page.wait_for_selector("#pacing-button", state="attached")
        page.clock.run_for(5000)
        first, second = self.wait_disk(page, lambda records: len(records) == 2)
        self.assertNotEqual(first["segment"], second["segment"])
        # A crash: nothing reaches the server, then the tab dies without
        # running beforeunload.
        page.route("**/__lecturedeck/pacing", lambda route: route.abort())
        page.clock.run_for(20_000)
        segment = journal(page)[-1]["record"]["segment"]
        page.close()
        # The next page in the same browser uploads the journal's tail.
        recovering = self.open_at(context, utc(12, 0))
        (entry,) = [e for e in journal(recovering) if e["record"]["segment"] == segment]
        rev = entry["record"]["rev"]
        records = self.wait_disk(
            recovering,
            lambda records: any(r["segment"] == segment and r["rev"] == rev for r in records),
        )
        self.assertEqual(2, len(records))
        self.assertEqual(20_000 + 5_000, sum(v["durationMs"] for v in records[
            [r["segment"] for r in records].index(segment)]["visits"]))

    def test_pacing_headline_measures_overrun(self):
        page = self.open_at(self.context(), utc(8, 58))
        page.clock.run_for(5000)
        page.keyboard.press("ArrowRight")  # a change before the slot
        page.clock.run_for((4 * 60 + 15) * 1000)  # 09:02:20
        page.keyboard.press("ArrowRight")
        page.clock.run_for(5000)
        self.open_report(page)
        headline = page.locator("#pacing-headline")
        self.assertEqual("20000", headline.get_attribute("data-overrun-ms"))
        self.assertEqual("true", headline.get_attribute("data-over"))
        self.assertIn("+0:20 past 09:02", headline.text_content())
        self.assertEqual("120000", headline.get_attribute("data-in-slot-ms"))
        self.assertIn("Started 08:58:05 (first slide change)", headline.text_content())
        self.assertEqual("2:00", page.text_content('[data-tile="before"] .pacing-tile-value'))
        self.assertIn("1 slide change", page.text_content('[data-tile="before"]'))
        self.assertEqual("0:25", page.text_content('[data-tile="after"] .pacing-tile-value'))
        self.assertEqual("true", page.get_attribute('[data-tile="after"]', "data-over"))
        timeline = page.text_content("details.pacing-timeline")
        self.assertIn("— 09:00 scheduled start —", timeline)
        self.assertIn("— 09:02 scheduled end —", timeline)
        until = int(headline.get_attribute("data-on-screen-until"))
        page.keyboard.press("Escape")
        page.clock.run_for(5 * 60_000)
        self.open_report(page)
        self.assertEqual("20000", headline.get_attribute("data-overrun-ms"))
        grown = int(headline.get_attribute("data-on-screen-until"))
        self.assertEqual(5 * 60_000, grown - until)

    def test_pacing_report_controls_stay_reachable(self):
        record = lecture_segment()
        key = f"lecturedeck-pacing2:/webdeck/:2026-01-01:{record['segment']}"
        sync = {"rev": record["rev"], "file": "pacing-records/x.json",
                "at": "2026-01-01T16:41:07.000Z", "state": "saved", "error": None}
        for width, height in ((1280, 720), (375, 812)):
            with self.subTest(width=width, height=height):
                context = self.context(viewport={"width": width, "height": height})
                context.add_init_script(seed_script({key: {"record": record, "sync": sync}}))
                page = self.open_at(context, utc(12, 0))
                self.open_report(page)
                self.assertIsNone(page.get_attribute("details.pacing-slides", "open"))
                self.assertIsNone(page.get_attribute("details.pacing-timeline", "open"))
                self.assertEqual(
                    ["Opening", "Part A", "Part B", "Part C", "Part D", "Part E",
                     "Backup slides (B1–B92)"],
                    page.locator(".pacing-sections tbody th").all_text_contents(),
                )
                self.assertIn("Not shown: slides 1–5 (5 main slides)",
                              page.text_content(".pacing-not-shown"))
                self.assertIn("Per-slide time · 149 slides · 149 visits",
                              page.text_content("details.pacing-slides summary"))
                page.locator("details.pacing-slides summary").click()
                body = page.locator(".pacing-body")
                self.assertGreater(body.evaluate("b => b.scrollHeight - b.clientHeight"), 500)
                body.evaluate("b => { b.scrollTop = b.scrollHeight; }")
                for selector in ("#pacing-close", "#pacing-export"):
                    box = page.locator(selector).bounding_box()
                    self.assertIsNotNone(box, selector)
                    self.assertGreaterEqual(box["x"], 0, selector)
                    self.assertGreaterEqual(box["y"], 0, selector)
                    self.assertLessEqual(box["x"] + box["width"], width, selector)
                    self.assertLessEqual(box["y"] + box["height"], height, selector)
                    self.assertTrue(page.locator(selector).is_enabled(), selector)
                self.assertEqual(0, page.evaluate(
                    "document.documentElement.scrollWidth - innerWidth"))

    def test_dialogs_swallow_deck_input(self):
        page = self.open_at(self.context(viewport={"width": 1280, "height": 720}), utc(9, 0, 30))
        index = lambda: page.evaluate(  # noqa: E731
            "Number(document.querySelector('#deck .slide-frame').dataset.index)")
        page.keyboard.press("ArrowRight")
        self.assertEqual(1, index())
        page.locator("#controls-toggle").click()
        page.locator("#pacing-button").click()
        page.wait_for_selector("#pacing-dialog[open]")
        for key in ("ArrowRight", "PageDown", "Space", "ArrowLeft", "End", "o", "f"):
            page.keyboard.press(key)
        page.mouse.move(640, 360)
        for _ in range(3):
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(80)
        self.assertEqual(1, index())
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        self.assertFalse(page.evaluate("document.body.classList.contains('pseudo-fullscreen')"))
        page.keyboard.press("Escape")
        page.wait_for_selector("#pacing-dialog", state="hidden")
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        self.assertEqual("pacing-button", page.evaluate("document.activeElement.id"))
        # A click on the backdrop closes it too.
        page.locator("#pacing-button").click()
        page.wait_for_selector("#pacing-dialog[open]")
        page.mouse.click(8, 8)
        page.wait_for_selector("#pacing-dialog", state="hidden")
        self.assertEqual(1, index())
        # The Appearance dialog: the wheel and the adjust HUD's G stay out.
        page.keyboard.press("t")
        page.wait_for_selector("#appearance-dialog[open]")
        page.mouse.move(640, 360)
        page.mouse.wheel(0, 120)
        page.wait_for_timeout(80)
        page.keyboard.press("g")
        page.keyboard.press("ArrowRight")
        self.assertEqual(1, index())
        self.assertTrue(page.evaluate("document.querySelector('.lecturedeck-adjust-hud').hidden"))
        page.keyboard.press("Escape")
        page.wait_for_selector("#appearance-dialog", state="hidden")
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        page.keyboard.press("g")  # the HUD still works once the dialog is gone
        page.wait_for_selector(".lecturedeck-adjust-hud:not([hidden])")
        page.keyboard.press("g")
        # Escape that ends fullscreen behind a dialog must not open the overview.
        page.keyboard.press("f")
        page.wait_for_function(
            "Boolean(document.fullscreenElement)"
            " || document.body.classList.contains('pseudo-fullscreen')"
        )
        native = page.evaluate("Boolean(document.fullscreenElement)")
        self.open_report(page)
        if native:
            # The browser's own Escape ends native fullscreen and leaves the
            # dialog open; the exit must not open the overview behind it.
            page.evaluate("document.exitFullscreen()")
            page.wait_for_function(
                "document.querySelector('#fullscreen-button').textContent === 'Full screen'"
            )
            self.assertTrue(page.evaluate("document.querySelector('#pacing-dialog').open"))
            self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        page.keyboard.press("Escape")
        page.wait_for_selector("#pacing-dialog", state="hidden")
        if not native:
            # Escape closed the dialog and left the presentation alone.
            self.assertTrue(page.evaluate("document.body.classList.contains('pseudo-fullscreen')"))
        self.assertTrue(page.evaluate("document.querySelector('#overview').hidden"))
        self.assertEqual(1, index())

    def test_two_windows_record_separately(self):
        context = self.context()
        first = self.open_at(context, utc(9, 0, 0))
        first.clock.run_for(5_000)
        second = self.open_at(context, None)  # opens at 09:00:05 on the shared clock
        context.clock.run_for(5_000)
        records = self.wait_disk(second, lambda records: len(records) == 2)
        self.assertEqual(2, len({r["segment"] for r in records}))
        self.open_report(second)
        notes = second.text_content(".pacing-notes")
        self.assertIn("Two windows recorded at once for 0:05", notes)
        self.assertIn("2 recordings merged (1 other window).", notes)
        # 09:00:00-09:00:10 once, not the 15 s the two windows add up to.
        self.assertEqual("10000", second.get_attribute("#pacing-headline", "data-in-slot-ms"))

    def test_idle_window_does_not_take_over_at_the_boundaries(self):
        # Both windows split their visits at 09:00 and 09:02 to the same
        # millisecond. The window opened later but never touched must not win
        # those splits from the one being presented.
        context = self.context()
        presenting = self.open_at(context, utc(8, 59, 0))
        context.clock.run_for(5_000)
        self.open_at(context, None, self.url + "#/3")  # 08:59:05 on Part two, left alone
        context.clock.run_for(15_000)
        presenting.keyboard.press("ArrowRight")  # 08:59:20 Part one
        context.clock.run_for(70_000)
        presenting.keyboard.press("ArrowRight")  # 09:00:30 Middle
        context.clock.run_for(120_000)  # 09:02:30
        self.open_report(presenting)
        headline = presenting.locator("#pacing-headline")
        self.assertEqual("-90000", headline.get_attribute("data-overrun-ms"))
        self.assertIn("Last main-slide change 09:00:30 · 1:30 before 09:02",
                      headline.text_content())
        rows = {
            row.locator("th").text_content(): row.locator("td").all_text_contents()
            for row in presenting.locator(".pacing-sections tbody tr").all()
        }
        # Section | Entered | Slides shown | In slot | Outside slot
        self.assertEqual("0:30", rows["Opening"][2])  # Part one, 09:00:00-09:00:30
        self.assertEqual("1:30", rows["Middle"][2])  # Middle, 09:00:30-09:02:00
        # Opening the second window is its change: Part two holds 08:59:05-08:59:20.
        self.assertEqual("0:45 before", rows["Opening"][3])
        self.assertEqual("0:15 before · 0:30 after", rows["Middle"][3])

    def test_headline_counts_only_real_slide_changes(self):
        # One early-finish recording, closed at 09:03:10, then the deck opened
        # again after class to read the report. Neither opening a page nor
        # coming back from the backup to the closing slide is a slide change.
        def seed(last: str) -> str:
            info = {
                "p-title": (1, "1", "Pacing", "Opening"),
                "p-figure": (2, "2", "Part one", "Opening"),
                "p-two": (4, "4", "Part two", "Middle"),
                "p-three": (5, "5", "Part three", "Middle"),
                "p-extra": (7, "B2", "Backup extra", "Backup"),
            }
            slides = {slide: {"number": n, "label": label, "title": title, "section": section}
                      for slide, (n, label, title, section) in info.items()}
            slides["p-extra"]["backup"] = True
            visits = [
                ("p-title", "08:59:50.000", 10_000, "before"),
                ("p-title", "09:00:00.000", 10_000, "slot"),
                ("p-figure", "09:00:10.000", 25_150, "slot"),
                ("p-three", "09:00:35.150", 84_850, "slot"),  # the real last change
                ("p-three", "09:02:00.000", 30_000, "after"),
                ("p-extra", "09:02:30.000", 30_000, "after"),  # a question from the backup
                (last, "09:03:00.000", 10_000, "after"),
            ]
            record = pacing_segment(segment="5eed00000001", rev=7, slides=slides, visits=[
                {"slideId": slide, "startedAt": f"2026-01-01T{at}Z", "durationMs": ms,
                 "phase": phase} for slide, at, ms, phase in visits])
            sync = {"rev": 7, "file": "pacing-records/x.json", "at": "2026-01-01T09:03:10.000Z",
                    "state": "saved", "error": None}
            return seed_script({"lecturedeck-pacing2:/webdeck/:2026-01-01:5eed00000001":
                                {"record": record, "sync": sync}})

        def report(moment: datetime, script: str = ""):
            context = self.context()
            if script:
                context.add_init_script(script)
            page = self.open_at(context, moment)
            page.clock.run_for(3000)
            self.open_report(page)
            headline = page.locator("#pacing-headline")
            return (page, headline.get_attribute("data-overrun-ms"),
                    headline.get_attribute("data-over"), headline.text_content())

        page, overrun, over, text = report(utc(9, 20), seed("p-three"))
        self.assertEqual(("-84850", None), (overrun, over))
        # Whole seconds, like the wall times: 09:00:35.150 is 1:25 before 09:02.
        self.assertIn("Last main-slide change 09:00:35 · 1:25 before 09:02", text)
        self.assertIn("Started 09:00:10 (first slide change)", text)
        self.assertIn("2 recordings merged (1 page reload).", page.text_content(".pacing-notes"))
        # From the backup to another main slide is a change.
        _, overrun, over, text = report(utc(9, 20), seed("p-two"))
        self.assertEqual(("60000", "true"), (overrun, over))
        self.assertIn("Last main-slide change 09:03:00 · +1:00 past 09:02", text)
        # A deck opened after class and never paged changed nothing.
        _, overrun, over, text = report(utc(9, 5))
        self.assertEqual(("", None), (overrun, over))
        self.assertIn("No main-slide change recorded", text)
        self.assertIn("No slide change yet", text)

    def test_older_refused_entries_never_block_the_live_lecture(self):
        # On a single-unit serve every unit shares /webdeck/. An entry another
        # unit left behind, or one for a date since dropped from the schedule,
        # is refused (422) and stays pending; today's lecture still saves.
        pending = {"rev": 0, "file": None, "at": None, "state": "pending", "error": None}
        stale = [pacing_segment(segment="0000000000a1", unit="other"),
                 pacing_segment(segment="0000000000a2", date="2025-12-31")]
        context = self.context()
        context.add_init_script(seed_script({
            f"lecturedeck-pacing2:/webdeck/:{record['date']}:{record['segment']}":
                {"record": record, "sync": pending} for record in stale
        }, once="seeded"))
        page = self.open_at(context, utc(9, 0, 10))
        page.wait_for_function(
            """() => ['0000000000a1', '0000000000a2'].every(segment => Object.keys(localStorage)
              .some(key => key.endsWith(':' + segment)
                && JSON.parse(localStorage.getItem(key)).sync.error))"""
        )
        page.clock.run_for(30_000)
        errors = {e["record"]["segment"]: (e["sync"]["state"], e["sync"]["error"])
                  for e in journal(page)}
        self.assertEqual(("pending", "wrong-unit"), errors.pop("0000000000a1"))
        self.assertEqual(("pending", "not-scheduled"), errors.pop("0000000000a2"))
        ((live, _),) = errors.items()
        (entry,) = [e for e in journal(page) if e["record"]["segment"] == live]
        rev = entry["record"]["rev"]
        self.assertGreater(rev, 20)
        self.wait_disk(page, lambda records: any(
            r["segment"] == live and r["rev"] == rev for r in records))
        self.assertEqual("disk", page.get_attribute("#pacing-button", "data-saved"))
        self.open_report(page)
        self.assertEqual("ok", self.status(page)[0])

    def test_pacer_waits_for_a_v1_record_still_being_recorded(self):
        # A tab still running the old viewer writes its schema-1 record every
        # second of the slot; converting it then would freeze it half-way.
        def v1(date: str, visits: int) -> dict:
            start = epoch_ms(f"{date}T09:00:00.000Z")
            return {
                "schema": 1, "date": date, "timeZone": "UTC", "start": "09:00", "end": "09:02",
                "deck": "Pacing", "path": "/webdeck/",
                "visits": [{"slideId": "p-title", "number": 1, "title": "Pacing",
                            "section": "Opening", "startedAt": iso_ms(start + 30_000 * i),
                            "durationMs": 30_000} for i in range(visits)],
            }

        today = "lecturedeck-pacing:/webdeck/:2026-01-01"
        context = self.context()
        context.add_init_script(seed_script(
            {today: v1("2026-01-01", 1), "lecturedeck-pacing:/webdeck/:2025-12-31":
             v1("2025-12-31", 1)}, once="seeded"))
        page = self.open_at(context, utc(9, 1))

        def migrated() -> dict:
            return {e["record"]["date"]: len(e["record"]["visits"])
                    for e in journal(page) if e["record"].get("migratedFrom") == 1}

        # The ended record converts at once, so the conversion has run.
        page.wait_for_function("Object.keys(localStorage).some(key =>"
                               " key.startsWith('lecturedeck-pacing2-migrated:'))")
        self.assertEqual({"2025-12-31": 1}, migrated())
        # The old tab goes on writing until the slot ends.
        page.evaluate("([key, value]) => localStorage.setItem(key, value)",
                      [today, json.dumps(v1("2026-01-01", 3))])
        page.clock.run_for(65_000)  # 09:02:05
        page.reload()
        page.wait_for_selector("#pacing-button", state="attached")
        page.wait_for_function(
            f"Boolean(localStorage.getItem('lecturedeck-pacing2-migrated:{today}'))")
        self.assertEqual({"2025-12-31": 1, "2026-01-01": 3}, migrated())

    def test_oversized_entry_is_refused_without_blocking_newer_ones(self):
        # A long schema-1 record converts to one segment over the server's
        # 256 KiB. The sink answers 413 itself, so the entry is refused at
        # once and the newer one behind it still uploads.
        pending = {"rev": 0, "file": None, "at": None, "state": "pending", "error": None}
        big = pacing_segment(segment="0000000000b1", visits=[])
        small = pacing_segment(segment="0000000000b2")
        key = "lecturedeck-pacing2:/webdeck/:2026-01-01:"
        context = self.context()
        context.add_init_script(
            "if (!localStorage.getItem('seeded')) {"
            f" const big = {json.dumps(big)};"
            " big.visits = Array.from({length: 12000}, () => ({slideId: 'p-title',"
            " startedAt: '2026-01-01T08:30:00.000Z', durationMs: 1, phase: 'before'}));"
            f" localStorage.setItem({json.dumps(key + big['segment'])},"
            f" JSON.stringify({{record: big, sync: {json.dumps(pending)}}}));"
            f" localStorage.setItem({json.dumps(key + small['segment'])},"
            f" {json.dumps(json.dumps({'record': small, 'sync': pending}))});"
            " localStorage.setItem('seeded', '1'); }"
        )
        bodies = []
        context.on("request", lambda request: bodies.append(len(request.post_data_buffer or b""))
                   if request.method == "POST" else None)
        page = self.open_at(context, utc(12, 0))
        self.wait_disk(page, lambda records: [r["segment"] for r in records] == ["0000000000b2"])
        page.wait_for_function(
            f"JSON.parse(localStorage.getItem({json.dumps(key + big['segment'])})).sync.state"
            " === 'refused'"
        )
        (entry,) = [e for e in journal(page) if e["record"]["segment"] == "0000000000b1"]
        self.assertEqual(("refused", "too-large"), (entry["sync"]["state"], entry["sync"]["error"]))
        self.assertTrue(bodies)
        self.assertLessEqual(max(bodies), 262144)

    def test_pacer_migrates_v1_records(self):
        def v1(path: str, deck: str) -> dict:
            return {
                "schema": 1, "date": "2026-01-01", "timeZone": "UTC", "start": "09:00",
                "end": "09:02", "deck": deck, "path": path,
                "visits": [
                    {"slideId": "p-title", "number": 1, "title": "Pacing", "section": "Opening",
                     "startedAt": "2026-01-01T09:00:00.000Z", "durationMs": 30_000},
                    {"slideId": "p-extra", "number": 7, "label": "B2", "title": "Backup extra",
                     "section": "Backup", "startedAt": "2026-01-01T09:00:30.000Z",
                     "durationMs": 60_000},
                ],
            }

        seeded = {
            "lecturedeck-pacing:/webdeck/:2026-01-01": v1("/webdeck/", "Pacing"),
            "lecturedeck-pacing:/webdeck/:latest": "lecturedeck-pacing:/webdeck/:2026-01-01",
            "lecturedeck-pacing:/webdeck/index.html:2026-01-01": v1("/webdeck/index.html", "Other"),
        }
        context = self.context()
        context.add_init_script(
            seed_script(
                {k: v for k, v in seeded.items() if not k.endswith(":latest")}, once="seeded"
            )
            + "if (!localStorage.getItem('lecturedeck-pacing:/webdeck/:latest')) "
            "localStorage.setItem('lecturedeck-pacing:/webdeck/:latest', "
            "'lecturedeck-pacing:/webdeck/:2026-01-01');"
        )
        page = self.open_at(context, utc(12, 0))
        (record,) = self.wait_disk(page, lambda records: len(records) == 1)
        self.assertEqual(1, record["migratedFrom"])
        self.assertEqual(
            ("pacing", "0900", None, []),
            (record["unit"], record["opened"], record["fullscreenMs"], record["pauses"]),
        )
        self.assertEqual({"before": 0, "after": 0, "from": "2026-01-01T09:00:00.000Z",
                          "to": "2026-01-01T09:02:00.000Z"}, record["window"])
        self.assertEqual(["slot", "slot"], [v["phase"] for v in record["visits"]])
        self.assertEqual({"number": 7, "label": "B2", "title": "Backup extra", "section": "Backup",
                          "backup": True}, record["slides"]["p-extra"])
        page.reload()
        page.wait_for_selector("#pacing-button", state="attached")
        page.wait_for_timeout(500)
        self.assertEqual(1, len(self.disk(page)))
        stored = page.evaluate("Object.keys(localStorage)")
        for key in seeded:
            self.assertIn(key, stored)
        others = [e for e in journal(page) if e["record"]["deck"] == "Other"]
        self.assertEqual(1, len(others))
        self.assertEqual(
            ("pending", None), (others[0]["sync"]["state"], others[0]["record"]["unit"])
        )
        self.assertEqual(2, len(journal(page)))

    def test_static_release_records_in_browser_only(self):
        with tempfile.TemporaryDirectory() as folder:
            output = release_unit(self.unit, Path(folder) / "release")
            self.assertFalse((output / "pacing-sink.js").exists())
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), partial(QuietStaticHandler, directory=str(output))
            )
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            context = self.context()
            requests = []
            context.on("request", lambda request: requests.append(request.url))
            page = self.open_at(context, utc(9, 0, 10), f"http://127.0.0.1:{server.server_address[1]}/")
            page.clock.run_for(5000)
            self.open_report(page)
            page.wait_for_function(
                "document.querySelector('#pacing-status').textContent.includes('static copy')"
            )
            self.assertEqual("warn", page.get_attribute("#pacing-status", "data-state"))
            self.assertEqual("browser", page.get_attribute("#pacing-button", "data-saved"))
            with page.expect_download() as download:
                page.locator("#pacing-export").click()
            data = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
            self.assertEqual(f"2026-01-01_{data['segments'][0]['opened']}_pacing_export.json",
                             download.value.suggested_filename)
            self.assertEqual(2, data["schema"])
            self.assertEqual([2], [segment["schema"] for segment in data["segments"]])
            self.assertFalse([url for url in requests if "__lecturedeck/pacing" in url])

    def test_pacer_inert_under_automation(self):
        context = self.context(automation=True)
        posts = []
        context.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        page = self.open_at(context, utc(9, 0, 10))
        page.clock.run_for(20_000)
        self.assertIs(True, page.evaluate("navigator.webdriver"))
        self.assertEqual("automation", page.evaluate("window.lecturedeckPacingSink?.inert ?? null"))
        self.open_report(page)
        self.assertEqual(
            ("warn", "Saved in this browser only — automated browser"), self.status(page)
        )
        self.assertEqual("browser", page.get_attribute("#pacing-button", "data-saved"))
        self.assertEqual([], posts)
        self.assertEqual([], self.disk(page))

    def test_pacer_states_why_not_on_disk(self):
        context = self.context()
        page = context.new_page()
        page.route("**/__lecturedeck/pacing", lambda route: route.fulfill(
            status=403, json={"error": "not-same-machine"}))
        page.clock.install(time=utc(9, 0, 10))
        page.clock.pause_at(utc(9, 0, 10))
        page.goto(self.url)
        page.wait_for_function(
            "document.querySelector('#pacing-button')?.dataset.saved === 'browser'"
        )
        page.clock.run_for(5000)
        self.assertEqual("true", page.get_attribute("#pacing-button", "data-recording"))
        self.open_report(page)
        self.assertEqual(
            ("warn", "Saved in this browser only — only a browser on the computer serving the deck"
             " saves to disk"),
            self.status(page),
        )
        self.assertGreater(journal(page)[0]["record"]["rev"], 1)
        port = self.origin.rsplit(":", 1)[1]
        local = context.new_page()
        local.route(
            "**/__lecturedeck/pacing-sink.js", lambda route: route.fulfill(status=404, body="")
        )
        local.route("**/__lecturedeck/version", lambda route: route.fulfill(
            json={"version": "0", "livereload": False, "pacing": "use-local-address"}))
        local.goto(f"http://localhost:{port}/webdeck/")  # the context's clock is already paused
        local.wait_for_selector("#pacing-button", state="attached")
        self.open_report(local)
        local.wait_for_function(
            "document.querySelector('#pacing-status').textContent.includes('127.0.0.1')"
        )
        self.assertEqual(
            ("warn", f"Saved in this browser only — open the deck at http://127.0.0.1:{port}"
             " to save to disk"),
            self.status(local),
        )

    def test_cross_origin_cannot_write(self):
        page = self.context().new_page()
        page.goto(self.other_origin + "/webdeck/")
        page.wait_for_function("Boolean(window.LECTUREDECK)")
        outcome = page.evaluate(
            """async ({url, body}) => {
              const result = {};
              try {
                await fetch(url, {method: "POST", body, headers: {
                  "Content-Type": "application/json", "X-Lecturedeck-Pacing": "2"}});
                result.preflighted = "sent";
              } catch (_) { result.preflighted = "rejected"; }
              try {
                const response = await fetch(url, {method: "POST", mode: "no-cors", body,
                  headers: {"Content-Type": "text/plain"}});
                result.simple = response.type;
              } catch (_) { result.simple = "rejected"; }
              return result;
            }""",
            {"url": self.origin + "/__lecturedeck/pacing", "body": json.dumps(pacing_segment())},
        )
        self.assertEqual("rejected", outcome["preflighted"])
        self.assertIn(outcome["simple"], ("opaque", "rejected"))
        time.sleep(0.3)
        folder = self.unit / "pacing-records"
        self.assertEqual([], list(folder.glob("*_0123456789ab.json")) if folder.is_dir() else [])

    def test_sink_send_policy(self):
        page = self.open_at(self.context(), utc(9, 0, 30), sink=STUB_SINK)
        page.wait_for_function("window.__pacingSent.length === 1")  # the segment opens
        page.clock.run_for(1000)
        self.assertEqual(1, len(self.sent(page)))
        # Paging through several slides becomes one send, 2 s after the last.
        for _ in range(3):
            page.keyboard.press("ArrowRight")
        page.clock.run_for(1999)
        self.assertEqual(1, len(self.sent(page)))
        page.clock.run_for(1)
        self.assertEqual(2, len(self.sent(page)))
        # A heartbeat every 15 s while recording.
        page.clock.run_for(14_000)
        self.assertEqual(2, len(self.sent(page)))
        page.clock.run_for(1000)
        self.assertEqual(3, len(self.sent(page)))
        # Opening the report sends at once; so does closing it.
        self.open_report(page)
        self.sends(page, 4)
        self.assertEqual("ok", self.status(page)[0])
        self.assertIn("Saved to disk 09:00:48 · pacing-records/2026-01-01_0900_pacing_",
                      self.status(page)[1])
        page.keyboard.press("Escape")
        self.sends(page, 5)
        # A hidden tab saves with keepalive.
        page.clock.run_for(1000)
        set_visibility(page, "hidden")
        self.sends(page, 6)
        self.assertTrue(self.sent(page)[-1]["keepalive"])
        set_visibility(page, "visible")
        self.sends(page, 7)
        self.assertFalse(self.sent(page)[-1]["keepalive"])
        (entry,) = journal(page)
        self.assertEqual("saved", entry["sync"]["state"])
        self.assertEqual(entry["record"]["rev"], entry["sync"]["rev"])
        self.assertEqual("disk", page.get_attribute("#pacing-button", "data-saved"))
        # A stale answer counts as saved up to the server's revision.
        page.evaluate(
            "() => { window.__pacingReply = r => ({ok: false, status: 409, error: 'stale',"
            " rev: r.rev}); }"
        )
        page.clock.run_for(15_000)
        (entry,) = journal(page)
        self.assertEqual(("saved", None), (entry["sync"]["state"], entry["sync"]["error"]))
        # A refusal rolls to a new segment once; a second one stops disk saving.
        page.evaluate(
            "() => { window.__pacingReply = () => ({ok: false, status: 400, error: 'invalid'}); }"
        )
        page.clock.run_for(15_000)
        segments = list(dict.fromkeys(s["segment"] for s in self.sent(page)))
        self.assertEqual(2, len(segments))
        page.wait_for_function("new Set(window.__pacingSent.map(s => s.segment)).size === 2")
        page.clock.run_for(15_000)
        count = len(self.sent(page))
        page.clock.run_for(30_000)
        self.assertEqual(count, len(self.sent(page)))
        states = {e["record"]["segment"]: e["sync"]["state"] for e in journal(page)}
        self.assertEqual(["refused", "refused"], [states[s] for s in segments])
        self.assertEqual("true", page.get_attribute("#pacing-button", "data-recording"))
        self.assertEqual("failing", page.get_attribute("#pacing-button", "data-saved"))
        self.open_report(page)
        self.assertEqual(("error", "Disk refused this recording: invalid"), self.status(page))
        # Every second is still in the report, merged across both segments;
        # the second continues this page load, so it is no reload.
        self.assertIn("2 recordings merged (1 continued in a new file).",
                      page.text_content(".pacing-notes"))
        self.assertEqual(0, page.locator(".pacing-reload").count())

    def test_sink_failures_retry_and_explain(self):
        page = self.open_at(self.context(), utc(9, 0, 30), sink=STUB_SINK.replace(
            "window.__pacingReply = null;",
            "window.__pacingReply = () => ({ok: false, status: 503, error: 'write-failed'});"))
        page.wait_for_function("window.__pacingSent.length === 1")
        times = lambda: [s["at"] for s in self.sent(page)]  # noqa: E731
        for _ in range(40):
            page.clock.run_for(1000)
        start = epoch_ms("2026-01-01T09:00:30.000Z")
        offsets = [t - start for t in times()]
        self.assertEqual(4, len(offsets), offsets)
        # Backoff 5, 10 and 20 s, within the one-second sampling step.
        gaps = [later - earlier for earlier, later in zip(offsets, offsets[1:])]
        for expected, gap in zip((5000, 10000, 20000), gaps):
            self.assertAlmostEqual(expected, gap, delta=1000)
        self.assertEqual("failing", page.get_attribute("#pacing-button", "data-saved"))
        self.open_report(page)
        self.assertEqual(
            ("error", "Disk save failing since 09:00:30 (server could not write) — retrying;"
             " every second is kept in this browser"),
            self.status(page),
        )
        page.keyboard.press("Escape")
        page.evaluate("() => { window.__pacingReply = null; }")
        for _ in range(40):
            page.clock.run_for(1000)
        self.assertEqual("disk", page.get_attribute("#pacing-button", "data-saved"))
        (entry,) = journal(page)
        self.assertEqual("saved", entry["sync"]["state"])
        # A forbidden page stops at once and says why.
        page.evaluate(
            "() => { window.__pacingReply = () => ({ok: false, status: 403, error: 'host'}); }"
        )
        page.clock.run_for(15_000)
        count = len(self.sent(page))
        page.clock.run_for(30_000)
        self.assertEqual(count, len(self.sent(page)))
        self.assertEqual("browser", page.get_attribute("#pacing-button", "data-saved"))
        self.open_report(page)
        port = self.origin.rsplit(":", 1)[1]
        self.assertEqual(
            ("warn", f"Saved in this browser only — open the deck at http://127.0.0.1:{port}"
             " to save to disk"),
            self.status(page),
        )

    def test_sink_probe_reports_ready_before_class(self):
        page = self.open_at(self.context(), utc(7, 50), sink=STUB_SINK)
        self.assertEqual("false", page.get_attribute("#pacing-button", "data-recording"))
        self.open_report(page)
        page.wait_for_function(
            "document.querySelector('#pacing-status').textContent.startsWith('Disk saving ready')"
        )
        self.assertEqual(
            ("neutral", "Disk saving ready on this computer · records from 08:30"),
            self.status(page),
        )
        self.assertIn("No recorded lecture yet", page.text_content(".pacing-body"))
        self.assertTrue(page.locator("#pacing-export").is_disabled())
        self.assertEqual([], self.sent(page))

    def test_report_held_open_stays_saved(self):
        # Read after class inside the window: the report pause keeps growing,
        # and the heartbeat carries it to disk, so the footer stays true.
        page = self.open_at(self.context(), utc(9, 0, 30), sink=STUB_SINK)
        page.wait_for_function("window.__pacingSent.length === 1")
        self.open_report(page)
        self.sends(page, 2)
        for _ in range(4):
            page.clock.run_for(10_000)
            self.assertEqual("ok", self.status(page)[0], self.status(page))
        self.assertEqual(4, len(self.sent(page)))  # heartbeats at 09:00:45 and 09:01:00
        self.assertIn("Saved to disk 09:01:00 · pacing-records/", self.status(page)[1])
        (entry,) = journal(page)
        self.assertEqual(("09:00:30", "report"), (entry["record"]["pauses"][-1]["startedAt"][11:19],
                                                  entry["record"]["pauses"][-1]["why"]))

    def test_probe_ready_despite_entries_this_server_will_not_take(self):
        # An old record of a unit this server no longer serves gets 404 for
        # good. It stays pending for another server but must not hide the
        # pre-class check behind a "retrying" warning.
        old = {
            "schema": 1, "date": "2025-12-31", "timeZone": "UTC", "start": "09:00",
            "end": "09:02", "deck": "Lecture 2", "path": "/decks/lecture-02/webdeck/",
            "visits": [{"slideId": "s1", "number": 1, "title": "Opening", "section": "Opening",
                        "startedAt": "2025-12-31T09:00:00.000Z", "durationMs": 60_000}],
        }
        context = self.context()
        context.add_init_script(seed_script(
            {"lecturedeck-pacing:/decks/lecture-02/webdeck/:2025-12-31": old}, once="seeded"))
        page = self.open_at(context, utc(7, 50), self.selector + "/decks/pacing/webdeck/")
        page.wait_for_function(
            """() => Object.keys(localStorage).some(key => key.startsWith('lecturedeck-pacing2:')
              && JSON.parse(localStorage.getItem(key)).sync.error === 'not-found')"""
        )
        self.open_report(page)
        page.wait_for_function(
            "document.querySelector('#pacing-status').textContent.startsWith('Disk saving ready')"
        )
        self.assertEqual(
            ("neutral", "Disk saving ready on this computer · records from 08:30 · 1 older"
             " recording not accepted by this server (not-found)"),
            self.status(page),
        )
        (entry,) = journal(page)
        self.assertEqual(
            ("pending", "lecture-02"), (entry["sync"]["state"], entry["record"]["unit"])
        )


if __name__ == "__main__":
    unittest.main()
