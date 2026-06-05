from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas


OUT_DIR = Path(__file__).resolve().parent / "Images"
PAGE_W = 960
PAGE_H = 620
CROP_BOTTOMS = {
    "fig01_cloud_vs_local_pointer_architecture.pdf": 105,
    "fig02_system_architecture_overview.pdf": 120,
    "fig05_symbol_index_bundle_pipeline.pdf": 145,
    "fig06_source_pointer_pipeline.pdf": 200,
    "fig07_runtime_pointer_pipeline.pdf": 70,
}

INK = HexColor("#20242c")
MUTED = HexColor("#46515f")
GRID = HexColor("#d5dbe5")
BLUE = HexColor("#376fc8")
BLUE_LIGHT = HexColor("#eaf2ff")
TEAL = HexColor("#1c8b8b")
TEAL_LIGHT = HexColor("#e5f7f6")
GREEN = HexColor("#3a8f50")
GREEN_LIGHT = HexColor("#eaf7ec")
AMBER = HexColor("#b8741a")
AMBER_LIGHT = HexColor("#fff3df")
RED = HexColor("#c44d4d")
RED_LIGHT = HexColor("#fff0ef")
PURPLE = HexColor("#7250b8")
PURPLE_LIGHT = HexColor("#f1ecff")
GRAY_FILL = HexColor("#f6f8fb")
WHITE = colors.white


def wrap_text(text: str, font: str, size: float, max_width: float) -> list[str]:
    result: list[str] = []
    for raw in text.split("\n"):
        if not raw:
            result.append("")
            continue
        words = raw.split(" ")
        line = ""
        for word in words:
            test = word if not line else f"{line} {word}"
            if pdfmetrics.stringWidth(test, font, size) <= max_width:
                line = test
            else:
                if line:
                    result.append(line)
                if pdfmetrics.stringWidth(word, font, size) <= max_width:
                    line = word
                else:
                    current = ""
                    for ch in word:
                        test_ch = current + ch
                        if pdfmetrics.stringWidth(test_ch, font, size) <= max_width:
                            current = test_ch
                        else:
                            if current:
                                result.append(current)
                            current = ch
                    line = current
        if line:
            result.append(line)
    return result


def set_color(c: canvas.Canvas, fill=None, stroke=None):
    if fill is not None:
        c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)


def multiline(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    font: str = "Helvetica",
    size: float = 9,
    color=INK,
    leading: float | None = None,
    align: str = "center",
):
    lines = wrap_text(text, font, size, width)
    if leading is None:
        leading = size + 3
    c.setFont(font, size)
    c.setFillColor(color)
    for i, line in enumerate(lines):
        yy = y - i * leading
        if align == "center":
            c.drawCentredString(x + width / 2, yy, line)
        elif align == "right":
            c.drawRightString(x + width, yy, line)
        else:
            c.drawString(x, yy, line)


def text_height(text: str, font: str, size: float, width: float, leading: float | None = None) -> float:
    if leading is None:
        leading = size + 3
    return max(1, len(wrap_text(text, font, size, width))) * leading


def centered_text(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    font: str = "Helvetica",
    size: float = 9,
    color=INK,
    leading: float | None = None,
    align: str = "center",
):
    if leading is None:
        leading = size + 3
    lines = wrap_text(text, font, size, w)
    if not lines:
        return
    ascent = pdfmetrics.getAscent(font, size)
    descent = pdfmetrics.getDescent(font, size)
    center_y = y + h / 2
    first_baseline = center_y + ((len(lines) - 1) * leading) / 2 - (ascent + descent) / 2
    c.setFont(font, size)
    c.setFillColor(color)
    for i, line in enumerate(lines):
        yy = first_baseline - i * leading
        if align == "center":
            c.drawCentredString(x + w / 2, yy, line)
        elif align == "right":
            c.drawRightString(x + w, yy, line)
        else:
            c.drawString(x, yy, line)


def title(c: canvas.Canvas, name: str, subtitle: str | None = None):
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(INK)
    c.drawString(36, PAGE_H - 38, name)
    c.setStrokeColor(GRID)
    c.setLineWidth(1.2)
    c.line(36, PAGE_H - 50, PAGE_W - 36, PAGE_H - 50)
    if subtitle:
        c.setFont("Helvetica", 10.2)
        c.setFillColor(MUTED)
        c.drawRightString(PAGE_W - 36, PAGE_H - 36, subtitle)


def footer(c: canvas.Canvas, note: str):
    c.setFont("Helvetica", 8.5)
    c.setFillColor(MUTED)
    c.drawCentredString(PAGE_W / 2, 18, note)


def box(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    heading: str,
    body: str = "",
    fill=GRAY_FILL,
    stroke=GRID,
    radius: float = 10,
    heading_color=INK,
    body_color=MUTED,
    heading_size: float = 10,
    body_size: float = 8.8,
    heading_font: str = "Helvetica-Bold",
    body_font: str = "Helvetica",
):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(1.2)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)
    multiline(c, heading, x + 10, y + h - 18, w - 20, heading_font, heading_size, heading_color, align="center")
    if body:
        centered_text(c, body, x + 12, y + 8, w - 24, h - 40, body_font, body_size, body_color)


def centered_box(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    fill=WHITE,
    stroke=GRID,
    radius: float = 8,
    color=INK,
    font: str = "Helvetica-Bold",
    size: float = 8.5,
    pad: float = 8,
):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(1.1)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)
    centered_text(c, text, x + pad, y, w - pad * 2, h, font=font, size=size, color=color)


def box_with_centered_body(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    heading: str,
    body: str,
    fill=WHITE,
    stroke=GRID,
    radius: float = 10,
    heading_size: float = 10,
    body_size: float = 8.8,
):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(1.2)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)
    multiline(c, heading, x + 10, y + h - 18, w - 20, "Helvetica-Bold", heading_size, INK, align="center")
    centered_text(c, body, x + 12, y + 8, w - 24, h - 38, "Helvetica", body_size, MUTED)


def label_box(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
    fill=WHITE,
    stroke=GRID,
    color=INK,
    font="Helvetica",
    size=8.8,
):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.9)
    c.roundRect(x, y, w, h, 7, fill=1, stroke=1)
    centered_text(c, label, x + 6, y, w - 12, h, font, size, color)


def cylinder(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    heading: str,
    body: str = "",
    fill=WHITE,
    stroke=GRID,
):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(1.2)
    c.ellipse(x, y, x + w, y + 20, fill=1, stroke=0)
    c.rect(x, y + 10, w, h - 20, fill=1, stroke=0)
    c.ellipse(x, y + h - 18, x + w, y + h, fill=1, stroke=0)
    c.setStrokeColor(stroke)
    c.ellipse(x, y + h - 18, x + w, y + h, fill=0, stroke=1)
    c.line(x, y + 10, x, y + h - 9)
    c.line(x + w, y + 10, x + w, y + h - 9)
    c.arc(x, y, x + w, y + 20, 180, 180)
    multiline(c, heading, x + 10, y + h - 30, w - 20, "Helvetica-Bold", 9.5, INK, align="center")
    if body:
        multiline(c, body, x + 10, y + h - 52, w - 20, "Helvetica", 8.5, MUTED, align="center")


def arrow(c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float, color=INK, width: float = 1.4, label: str | None = None):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 8
    p1 = (x2, y2)
    p2 = (x2 - size * math.cos(angle - math.pi / 6), y2 - size * math.sin(angle - math.pi / 6))
    p3 = (x2 - size * math.cos(angle + math.pi / 6), y2 - size * math.sin(angle + math.pi / 6))
    path = c.beginPath()
    path.moveTo(*p1)
    path.lineTo(*p2)
    path.lineTo(*p3)
    path.close()
    c.drawPath(path, fill=1, stroke=0)
    if label:
        lx = (x1 + x2) / 2
        ly = (y1 + y2) / 2 + 9
        c.setFont("Helvetica", 8.0)
        c.setFillColor(MUTED)
        c.drawCentredString(lx, ly, label)


def dashed_arrow(c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float, color=INK, label: str | None = None):
    c.saveState()
    c.setDash(5, 4)
    arrow(c, x1, y1, x2, y2, color=color, width=1.2, label=label)
    c.restoreState()


def poly_arrow(
    c: canvas.Canvas,
    points: list[tuple[float, float]],
    color=INK,
    width: float = 1.3,
    dashed: bool = False,
    label: str | None = None,
):
    if len(points) < 2:
        return
    c.saveState()
    if dashed:
        c.setDash(5, 4)
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(width)
    for (x1, y1), (x2, y2) in zip(points[:-2], points[1:-1]):
        c.line(x1, y1, x2, y2)
    arrow(c, points[-2][0], points[-2][1], points[-1][0], points[-1][1], color=color, width=width, label=None)
    c.restoreState()
    if label:
        lx = sum(p[0] for p in points) / len(points)
        ly = sum(p[1] for p in points) / len(points)
        c.setFont("Helvetica", 8.0)
        c.setFillColor(MUTED)
        c.drawCentredString(lx, ly + 8, label)


def diamond(c: canvas.Canvas, cx: float, cy: float, w: float, h: float, label: str, fill=WHITE, stroke=GRID):
    path = c.beginPath()
    path.moveTo(cx, cy + h / 2)
    path.lineTo(cx + w / 2, cy)
    path.lineTo(cx, cy - h / 2)
    path.lineTo(cx - w / 2, cy)
    path.close()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(1.2)
    c.drawPath(path, fill=1, stroke=1)
    centered_text(c, label, cx - w * 0.34, cy - h * 0.28, w * 0.68, h * 0.56, "Helvetica-Bold", 8.0, INK)


@dataclass
class FigureSpec:
    filename: str
    draw: callable


def new_canvas(path: Path) -> canvas.Canvas:
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(path.stem)
    c.setAuthor("SecureCode report figure generator")
    return c


def save(c: canvas.Canvas):
    c.showPage()
    c.save()


def crop_pdf_bottom(path: Path):
    bottom = CROP_BOTTOMS.get(path.name)
    if bottom is None:
        return
    reader = PdfReader(str(path))
    writer = PdfWriter()
    page = reader.pages[0]
    box = (0, bottom, PAGE_W, PAGE_H)
    page.mediabox.lower_left = box[:2]
    page.mediabox.upper_right = box[2:]
    page.cropbox.lower_left = box[:2]
    page.cropbox.upper_right = box[2:]
    page.trimbox.lower_left = box[:2]
    page.trimbox.upper_right = box[2:]
    writer.add_page(page)
    with path.open("wb") as f:
        writer.write(f)


def fig01_cloud_vs_local(path: Path):
    c = new_canvas(path)
    title(c, "Cloud Assistant vs Local Pointer-First Assistant", "Introductory comparison")

    box(c, 52, 476, 360, 52, "Conventional cloud code assistant", "Large context is commonly sent to an external model API", RED_LIGHT, RED)
    box(c, 548, 476, 360, 52, "Proposed local pointer-first assistant", "Raw internal data stays on local disk, store, and index", GREEN_LIGHT, GREEN)

    box(c, 55, 350, 120, 70, "Developer", "natural-language request", WHITE, GRID)
    box(c, 210, 342, 155, 86, "Raw prompt", "repository files\nlogs, JSON snapshots\ntest output", RED_LIGHT, RED)
    box(c, 500, 342, 150, 86, "Local catalogs", "symbol index\nsource manifest\nruntime store", BLUE_LIGHT, BLUE)
    box(c, 695, 342, 165, 86, "Small evidence", "selected symbols\nextracted fields\nfailure blocks", GREEN_LIGHT, GREEN)
    box(c, 210, 224, 155, 76, "Cloud model API", "external inference\nboundary crossing", WHITE, RED)
    box(c, 695, 224, 165, 76, "Local LLM", "local inference\nno external transfer", WHITE, GREEN)

    arrow(c, 175, 385, 210, 385, RED)
    arrow(c, 287, 342, 287, 300, RED)
    arrow(c, 650, 385, 695, 385, GREEN)
    arrow(c, 780, 342, 780, 300, GREEN)

    c.setStrokeColor(RED)
    c.setLineWidth(1.1)
    c.roundRect(197, 205, 180, 245, 14, fill=0, stroke=1)
    multiline(c, "Privacy risk:\ninternal code and operational data\nare embedded in the model context.", 205, 190, 166, "Helvetica", 8.5, RED, align="center")

    c.setStrokeColor(GREEN)
    c.roundRect(487, 205, 385, 245, 14, fill=0, stroke=1)
    multiline(c, "Design constraint:\nLLM context is treated as evidence for current reasoning,\nnot as a raw data warehouse.", 508, 190, 340, "Helvetica", 8.5, GREEN, align="center")

    save(c)


def fig02_system_architecture(path: Path):
    c = new_canvas(path)
    title(c, "Proposed Local LLM Code Assistance Architecture", "End-to-end workflow")

    box_with_centered_body(c, 40, 430, 120, 74, "User request", "bug report\ntest failure\nfile path\nquestion", WHITE, GRID)
    box(c, 205, 420, 135, 94, "Request analyzer", "extracts error messages,\nfile names, symbols,\nsource hints, test names", BLUE_LIGHT, BLUE)

    box(c, 390, 460, 180, 70, "Code structure layer", "AST index -> symbol URI\nmemory://symbol/...", BLUE_LIGHT, BLUE)
    box(c, 390, 350, 180, 70, "External evidence layer", "manifest -> source URI\nsource://kind/path", TEAL_LIGHT, TEAL)
    box(c, 390, 240, 180, 70, "Runtime evidence layer", "tool output -> store URI\nruntime://kind/id", GREEN_LIGHT, GREEN)

    box(c, 625, 350, 150, 124, "Resolver / extractor", "resolve_symbol\nexpand_symbol_context\ngrep/extract JSON\ntest failure slicing", AMBER_LIGHT, AMBER)
    box(c, 810, 350, 112, 124, "Evidence bundle", "line-numbered code\nlog blocks\nJSON fields\nprovenance", WHITE, GRID)
    box(c, 625, 205, 150, 82, "Local LLM", "reason over small,\nvalidated evidence", PURPLE_LIGHT, PURPLE)
    box(c, 810, 200, 112, 92, "Validation + execution", "schema checks\npath allowlist\nsmall evaluator\ntests", GREEN_LIGHT, GREEN)

    arrow(c, 160, 467, 205, 467, BLUE)
    arrow(c, 340, 470, 390, 495, BLUE)
    arrow(c, 340, 467, 390, 385, TEAL)
    arrow(c, 340, 455, 390, 275, GREEN)
    arrow(c, 570, 495, 625, 435, BLUE)
    arrow(c, 570, 385, 625, 405, TEAL)
    arrow(c, 570, 275, 625, 375, GREEN)
    arrow(c, 775, 412, 810, 412, AMBER)
    poly_arrow(c, [(866, 350), (866, 318), (700, 287)], PURPLE)
    arrow(c, 775, 246, 810, 246, GREEN)
    poly_arrow(c, [(866, 200), (866, 175), (520, 175), (520, 240)], GREEN, dashed=True)

    save(c)


def fig03_pointer_lifecycle(path: Path):
    c = new_canvas(path)
    title(c, "Pointer Types and Lifecycle", "memory://, source://, runtime://")

    headers = ["Data class", "Creation trigger", "Stored metadata", "Pointer form", "Resolver / extractor", "Lifetime"]
    xs = [36, 158, 314, 470, 620, 780]
    ws = [110, 142, 142, 136, 154, 140]
    for x, w, h in zip(xs, ws, headers):
        label_box(c, x, 512, w, 34, h, fill=HexColor("#eef1f6"), stroke=GRID, color=INK, font="Helvetica-Bold", size=8.5)

    rows = [
        (
            "Repository\ncode symbol",
            "workspace open\nfirst question\nfile save or patch",
            "path, kind,\nqualname,\nline range,\nfile hash",
            "memory://symbol/\nservices/a.py::f",
            "resolve_symbol\nexpand_symbol_context",
            "cache-valid until\nfile hash, branch,\nor parser version changes",
            BLUE_LIGHT,
            BLUE,
        ),
        (
            "Disk source\nlog, doc, JSON",
            "user mentions path\nallowlisted root scan\nsaved report artifact",
            "kind, rel_path,\nbytes, tools,\nhints, mtime/hash",
            "source://json/\njson/tenant.json",
            "resolve_pointer\nformat-specific extractor",
            "disk-backed until\nmtime/hash changes",
            TEAL_LIGHT,
            TEAL,
        ),
        (
            "Runtime object\ntool output",
            "tool returns large,\nstructured, reusable,\nor sensitive output",
            "producer, kind,\nbytes, tools,\nhints, object id",
            "runtime://log/\nrun_tests/0001",
            "RuntimeStore.resolve\nruntime extractor",
            "session scope\nTTL + LRU cleanup",
            GREEN_LIGHT,
            GREEN,
        ),
    ]

    y0 = 387
    for r, row in enumerate(rows):
        y = y0 - r * 132
        for i in range(6):
            fill = row[6] if i == 0 else WHITE
            stroke = row[7] if i == 0 else GRID
            centered_box(c, xs[i], y, ws[i], 92, row[i], fill, stroke, radius=8, font="Helvetica-Bold", size=8.8)
        for i in range(5):
            arrow(c, xs[i] + ws[i], y + 46, xs[i + 1] - 4, y + 46, row[7], width=1.0)

    box(c, 95, 42, 770, 72, "Prompt-facing invariant", "The model sees compact catalogs, pointer URIs, selected snippets, and provenance. It does not receive the complete repository, complete external file, or complete runtime object unless a validated fallback explicitly requires it.", AMBER_LIGHT, AMBER, heading_size=10.5, body_size=8.5)

    save(c)


def fig04_component_timing(path: Path):
    c = new_canvas(path)
    title(c, "When Each Component Operates", "Operational timing across an assistant session")

    cols = [
        ("Workspace open\nor first question", 220),
        ("File save,\nagent patch,\nbranch change", 350),
        ("User references\nsource file", 480),
        ("Tool execution\nreturns output", 610),
        ("LLM reasoning\ncall", 740),
        ("Validation or\nfallback", 860),
    ]
    for label, x in cols:
        label_box(c, x - 56, 505, 112, 42, label, fill=HexColor("#eef1f6"), stroke=GRID, font="Helvetica-Bold", size=8.3)

    lane_names = [
        ("symbol_index", BLUE, BLUE_LIGHT),
        ("source_pointer", TEAL, TEAL_LIGHT),
        ("runtime_pointer", GREEN, GREEN_LIGHT),
        ("self_extend", PURPLE, PURPLE_LIGHT),
    ]
    y_lanes = [406, 304, 202, 100]
    for (name, color, fill), y in zip(lane_names, y_lanes):
        label_box(c, 35, y, 115, 58, name, fill=fill, stroke=color, font="Helvetica-Bold", size=9.5)
        c.setStrokeColor(HexColor("#edf0f5"))
        c.line(160, y + 29, 905, y + 29)

    events = {
        "symbol_index": [
            (220, "initial build\nor lazy build", BLUE_LIGHT, BLUE),
            (350, "dirty-file\nincremental\nreparse", BLUE_LIGHT, BLUE),
            (740, "candidate\nfilter +\nresolve bundle", BLUE_LIGHT, BLUE),
            (860, "freshness\ncheck", WHITE, BLUE),
        ],
        "source_pointer": [
            (480, "allowlist\nmanifest entry\nmtime/hash", TEAL_LIGHT, TEAL),
            (740, "tool-call\nselection +\nextraction", TEAL_LIGHT, TEAL),
            (860, "path/schema\nvalidation", WHITE, TEAL),
        ],
        "runtime_pointer": [
            (610, "RuntimeStore.put\nif large or\nstructured", GREEN_LIGHT, GREEN),
            (740, "runtime\nextractor", GREEN_LIGHT, GREEN),
            (860, "TTL / LRU\ncleanup", WHITE, GREEN),
        ],
        "self_extend": [
            (740, "OFF by default", WHITE, PURPLE),
            (860, "per-call\nfallback only\nthen validate", PURPLE_LIGHT, PURPLE),
        ],
    }

    for lane, event_list in events.items():
        y = y_lanes[[name for name, _, _ in lane_names].index(lane)]
        for x, label, fill, stroke in event_list:
            centered_box(c, x - 52, y + 4, 104, 50, label, fill, stroke, radius=8, font="Helvetica-Bold", size=8.1)

    for y in y_lanes:
        for i in range(len(cols) - 1):
            c.saveState()
            c.setDash(3, 5)
            c.setStrokeColor(GRID)
            c.line(cols[i][1] + 58, y + 29, cols[i + 1][1] - 58, y + 29)
            c.restoreState()

    box(c, 230, 34, 500, 54, "Design implication", "Index/catalog/storage are maintained by system lifecycle events; LLM calls consume small, current evidence bundles.", AMBER_LIGHT, AMBER, heading_size=9.5, body_size=8.8)
    save(c)


def fig05_symbol_pipeline(path: Path):
    c = new_canvas(path)
    title(c, "Symbol Index and Symbol Bundle Pipeline", "Repository code access through memory:// pointers")

    y = 410
    boxes = [
        (45, 100, "Repository files", "Python source\n27 files in medium corpus", WHITE, GRID),
        (170, 118, "AST parser", "ClassDef, FunctionDef,\nAsyncFunctionDef", BLUE_LIGHT, BLUE),
        (315, 125, "symbol_index.json", "path, kind, qualname,\nstart/end line, URI", BLUE_LIGHT, BLUE),
        (470, 118, "Candidate outline", "question-based filter\ncompact metadata", WHITE, BLUE),
        (615, 110, "Selector", "choose memory://\nsymbol URI", PURPLE_LIGHT, PURPLE),
        (750, 110, "Resolver", "read exact line span\nwith provenance", AMBER_LIGHT, AMBER),
    ]
    last_x = None
    for x, w, h, b, fill, stroke in [(b[0], b[1], 78, b[2] + "\n" + b[3], b[4], b[5]) for b in []]:
        pass

    for x, w, head, body, fill, stroke in boxes:
        box(c, x, y, w, 86, head, body, fill, stroke)
        if last_x is not None:
            arrow(c, last_x, y + 43, x - 2, y + 43, BLUE)
        last_x = x + w

    box(c, 326, 270, 210, 92, "expand_symbol_context", "adds module constants,\nsame-file helper/callee,\nand question-mentioned symbols", GREEN_LIGHT, GREEN)
    box(c, 590, 270, 190, 92, "Evidence bundle", "line-numbered fragments\nprimary symbol + context\nreason for inclusion", WHITE, GRID)
    box(c, 805, 270, 120, 92, "Local LLM", "answers or\nplans patch", PURPLE_LIGHT, PURPLE)

    poly_arrow(c, [(805, y), (805, 378), (536, 378), (536, 362)], AMBER)
    arrow(c, 536, 316, 590, 316, GREEN)
    arrow(c, 780, 316, 805, 316, PURPLE)

    cylinder(c, 68, 210, 160, 88, "memory:// symbol store", "URI -> file span\nindex version + provenance", BLUE_LIGHT, BLUE)
    dashed_arrow(c, 377, 410, 180, 298, BLUE, "cache")

    save(c)


def fig06_source_pipeline(path: Path):
    c = new_canvas(path)
    title(c, "Source Pointer Pipeline", "Disk-backed evidence access through source:// pointers")

    box(c, 45, 410, 130, 86, "Allowed source roots", "logs/\ndocs/\nreports/\njson/", WHITE, GRID)
    box(c, 220, 410, 138, 86, "Manifest", "kind, rel_path,\nbytes, tools,\nhints, hash", TEAL_LIGHT, TEAL)
    box(c, 395, 410, 135, 86, "Compact catalog", "pointer + hints\nwithout raw file", WHITE, TEAL)
    box(c, 565, 410, 150, 86, "Selector tool call", "{tool, args}\ngrep_log or\nextract_json_field", PURPLE_LIGHT, PURPLE)
    box(c, 760, 410, 150, 86, "Resolver", "normalize path\ncheck allowlist\nload file", AMBER_LIGHT, AMBER)

    arrow(c, 175, 453, 220, 453, TEAL)
    arrow(c, 358, 453, 395, 453, TEAL)
    arrow(c, 530, 453, 565, 453, PURPLE)
    arrow(c, 715, 453, 760, 453, AMBER)

    box(c, 255, 270, 170, 82, "Format-specific extractor", "grep_log\nextract_doc_section\nextract_json_field", GREEN_LIGHT, GREEN)
    box(c, 515, 270, 170, 82, "Small evidence", "matching log lines\nselected doc section\nspecific JSON fields", WHITE, GRID)
    box(c, 760, 270, 150, 82, "Local LLM", "answer from\nextracted evidence", BLUE_LIGHT, BLUE)

    poly_arrow(c, [(835, 410), (835, 374), (340, 374), (340, 352)], AMBER)
    arrow(c, 425, 311, 515, 311, GREEN)
    arrow(c, 685, 311, 760, 311, BLUE)

    save(c)


def fig07_runtime_pipeline(path: Path):
    c = new_canvas(path)
    title(c, "Runtime Pointer Pipeline", "Session-local evidence access through runtime:// pointers")

    box(c, 45, 405, 130, 82, "Tool execution", "run tests\nbuild project\nAPI call\nstatic analysis", WHITE, GRID)
    diamond(c, 260, 446, 150, 96, "large,\nstructured,\nreusable,\nor sensitive?")
    box(c, 430, 455, 155, 70, "Direct message", "short safe output\nis passed as text", WHITE, GRID)
    box(c, 430, 333, 155, 90, "RuntimeStore.put", "store raw object\nissue runtime:// pointer\nemit compact catalog", GREEN_LIGHT, GREEN)

    arrow(c, 175, 446, 185, 446, GREEN)
    arrow(c, 335, 446, 430, 490, GREEN)
    label_box(c, 374, 475, 26, 16, "no", fill=WHITE, stroke=WHITE, color=MUTED, size=8.0)
    arrow(c, 260, 398, 430, 378, GREEN)
    label_box(c, 343, 392, 30, 16, "yes", fill=WHITE, stroke=WHITE, color=MUTED, size=8.0)

    box(c, 630, 333, 145, 90, "Runtime selector", "choose extractor\nfrom pointer catalog", PURPLE_LIGHT, PURPLE)
    box(c, 630, 455, 145, 70, "Next LLM call", "small output can be\nused immediately", BLUE_LIGHT, BLUE)
    box(c, 805, 333, 120, 90, "Extractor", "grep_runtime_log\nextract_runtime_\njson_path", AMBER_LIGHT, AMBER)
    box(c, 805, 205, 120, 76, "Evidence", "failure block\nJSON field\ndoc section", WHITE, GRID)
    box(c, 630, 205, 145, 76, "Symbol/source follow-up", "failure text can guide\nsymbol selection", BLUE_LIGHT, BLUE)

    arrow(c, 585, 490, 630, 490, BLUE)
    arrow(c, 585, 378, 630, 378, GREEN)
    arrow(c, 775, 378, 805, 378, AMBER)
    arrow(c, 865, 333, 865, 281, AMBER)
    arrow(c, 805, 243, 775, 243, BLUE)
    dashed_arrow(c, 630, 243, 325, 140, BLUE)
    label_box(c, 438, 198, 100, 18, "feedback to retrieval", fill=WHITE, stroke=WHITE, color=MUTED, size=8.2)

    cylinder(c, 100, 122, 165, 85, "RuntimeStore", "session scope\nTTL + LRU cleanup\nnot a disk manifest", GREEN_LIGHT, GREEN)
    dashed_arrow(c, 505, 333, 182, 207, GREEN)
    label_box(c, 304, 282, 102, 18, "raw object stays here", fill=WHITE, stroke=WHITE, color=MUTED, size=8.2)

    save(c)


def fig08_self_extend_fallback(path: Path):
    c = new_canvas(path)
    title(c, "Self-Extend as a Validated Fallback", "Not a default retrieval layer")

    box(c, 55, 420, 145, 84, "Pointer-first path", "symbol/source/runtime\nretrieval and extraction", GREEN_LIGHT, GREEN)
    diamond(c, 300, 462, 150, 96, "evidence still\ntoo broad or\ncomparison needed?")
    box(c, 460, 420, 145, 84, "Self-Extend call", "per-call option\nG=2 or G=4\nlarger n_ctx", PURPLE_LIGHT, PURPLE)
    box(c, 660, 420, 145, 84, "Model output", "summary, guess,\nor proposed cause", WHITE, GRID)
    diamond(c, 800, 330, 150, 96, "validated\nfile/symbol/line/\ntest evidence?")
    box(c, 560, 214, 160, 76, "Accept as patch plan", "only after concrete\nlocal evidence checks", GREEN_LIGHT, GREEN)
    box(c, 785, 120, 150, 76, "Return to pointer search", "narrow catalog,\nextract smaller evidence,\nor run tools", RED_LIGHT, RED)

    arrow(c, 200, 462, 225, 462, GREEN)
    arrow(c, 375, 462, 460, 462, PURPLE)
    label_box(c, 410, 472, 30, 16, "yes", fill=WHITE, stroke=WHITE, color=MUTED, size=8.0)
    arrow(c, 605, 462, 660, 462, PURPLE)
    arrow(c, 732, 420, 786, 376, PURPLE)
    arrow(c, 760, 308, 720, 252, GREEN)
    label_box(c, 727, 284, 30, 16, "yes", fill=WHITE, stroke=WHITE, color=MUTED, size=8.0)
    arrow(c, 830, 286, 858, 196, RED)
    label_box(c, 850, 245, 26, 16, "no", fill=WHITE, stroke=WHITE, color=MUTED, size=8.0)
    poly_arrow(c, [(785, 158), (340, 158), (340, 398), (200, 438)], RED, dashed=True, label="retry pointer-based narrowing")

    box(c, 68, 246, 250, 82, "Observed limitation", "Group attention increased context capacity, but passkey retrieval and code-assistance retrieval still failed in this setup.", RED_LIGHT, RED, body_size=8.8)
    box(c, 350, 74, 280, 82, "Operational rule", "Self-Extend produces no index, no catalog, and no persistent pointer. It is only an execution option for one LLM call.", AMBER_LIGHT, AMBER, body_size=8.8)

    save(c)


def bar(c: canvas.Canvas, x: float, y: float, w: float, h: float, value: float, fill, label: str):
    c.setFillColor(HexColor("#eef1f6"))
    c.setStrokeColor(GRID)
    c.rect(x, y, w, h, fill=1, stroke=1)
    c.setFillColor(fill)
    c.rect(x, y, w * value / 100.0, h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(INK)
    c.drawRightString(x + w - 6, y + h / 2 - 3, f"{value:.1f}%")
    c.setFont("Helvetica", 8.2)
    c.setFillColor(MUTED)
    c.drawString(x, y + h + 5, label)


def fig09_evaluation_summary(path: Path):
    c = new_canvas(path)
    title(c, "Evaluation Summary: Baseline, Oracle, and Selected Workflows", "Absolute cost comparison")

    headers = ["Experiment", "Inefficient baseline", "Oracle / ideal", "Selected workflow", "Takeaway"]
    xs = [38, 188, 382, 552, 728]
    ws = [135, 176, 150, 158, 194]
    for x, w, header in zip(xs, ws, headers):
        centered_box(c, x, 494, w, 34, header, fill=HexColor("#eef1f6"), stroke=GRID, radius=7, font="Helvetica-Bold", size=11.2, pad=5)

    rows = [
        (
            "Symbol\nmedium",
            "naive select\n33,871 tok\n181.191s",
            "bundle oracle\n305 tok\n2.600s",
            "filtered bundle\n824 tok\n6.262s",
            "Oracle is fastest;\nfiltered selector adds\nplanning cost but stays\nfar below naive select.",
            BLUE_LIGHT,
            BLUE,
        ),
        (
            "Symbol\nhard",
            "naive select\n33,922 tok\n172.170s",
            "bundle oracle\n369 tok\n2.298s",
            "filtered bundle\n587 tok\n4.588s",
            "Bundle solves context\nsize; remaining errors\ncome from execution\nreasoning.",
            BLUE_LIGHT,
            BLUE,
        ),
        (
            "Source\nmedium",
            "full_source\n120,208 tok\n22.117s",
            "pointer oracle\n286 tok\n2.443s",
            "pointer select\n780 tok\n6.423s",
            "Pointer extraction\nseparates disk data\nsize from prompt size.",
            TEAL_LIGHT,
            TEAL,
        ),
        (
            "Runtime\nmedium",
            "full_runtime\n131,136 tok\n26.270s",
            "runtime oracle\n311 tok\n2.610s",
            "runtime select\n757 tok\n6.891s",
            "Tool output remains\nsession-local instead\nof becoming message\nhistory baggage.",
            GREEN_LIGHT,
            GREEN,
        ),
    ]

    y = 398
    for name, baseline, oracle, selected, takeaway, fill, stroke in rows:
        centered_box(c, xs[0], y, ws[0], 76, name, fill, stroke, radius=7, font="Helvetica-Bold", size=10.8, pad=5)
        centered_box(c, xs[1], y, ws[1], 76, baseline, RED_LIGHT, RED, radius=7, font="Helvetica-Bold", size=9.8, pad=5)
        centered_box(c, xs[2], y, ws[2], 76, oracle, GREEN_LIGHT, GREEN, radius=7, font="Helvetica-Bold", size=9.8, pad=5)
        centered_box(c, xs[3], y, ws[3], 76, selected, WHITE, GRID, radius=7, font="Helvetica-Bold", size=9.8, pad=5)
        centered_box(c, xs[4], y, ws[4], 76, takeaway, WHITE, GRID, radius=7, font="Helvetica", size=8.6, pad=6)
        arrow(c, xs[1] + ws[1], y + 38, xs[2] - 4, y + 38, GREEN, width=1.0)
        arrow(c, xs[2] + ws[2], y + 38, xs[3] - 4, y + 38, BLUE, width=1.0)
        y -= 92

    centered_box(c, 94, 42, 340, 58, "How to read this table\nOracle rows skip selection and should be faster than selected workflows.", WHITE, GRID, radius=7, font="Helvetica-Bold", size=8.8, pad=8)
    centered_box(c, 520, 42, 340, 58, "Core conclusion\nSelected workflows add overhead, but remain far below full or naive context.", GREEN_LIGHT, GREEN, radius=7, font="Helvetica-Bold", size=8.8, pad=8)

    save(c)


def generate_all() -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    specs = [
        FigureSpec("fig01_cloud_vs_local_pointer_architecture.pdf", fig01_cloud_vs_local),
        FigureSpec("fig02_system_architecture_overview.pdf", fig02_system_architecture),
        FigureSpec("fig03_pointer_types_lifecycle.pdf", fig03_pointer_lifecycle),
        FigureSpec("fig04_component_operation_timing.pdf", fig04_component_timing),
        FigureSpec("fig05_symbol_index_bundle_pipeline.pdf", fig05_symbol_pipeline),
        FigureSpec("fig06_source_pointer_pipeline.pdf", fig06_source_pipeline),
        FigureSpec("fig07_runtime_pointer_pipeline.pdf", fig07_runtime_pipeline),
        FigureSpec("fig08_self_extend_fallback_validation.pdf", fig08_self_extend_fallback),
        FigureSpec("fig09_evaluation_token_time_reduction_summary.pdf", fig09_evaluation_summary),
    ]
    paths: list[Path] = []
    for spec in specs:
        pdf_path = OUT_DIR / spec.filename
        spec.draw(pdf_path)
        crop_pdf_bottom(pdf_path)
        paths.append(pdf_path)
    return paths


def find_pdftoppm() -> str | None:
    candidates = [
        Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pdftoppm",
        Path("/usr/local/bin/pdftoppm"),
        Path("/opt/homebrew/bin/pdftoppm"),
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "pdftoppm"


def render_pngs(pdf_paths: list[Path]):
    pdftoppm = find_pdftoppm()
    font_cache = Path("/private/tmp/codex-fontconfig-cache")
    font_cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("XDG_CACHE_HOME", str(font_cache))
    for pdf_path in pdf_paths:
        outbase = pdf_path.with_suffix("")
        subprocess.run(
            [pdftoppm, "-singlefile", "-cropbox", "-png", "-r", "180", str(pdf_path), str(outbase)],
            check=True,
            stderr=subprocess.DEVNULL,
            env=env,
        )


if __name__ == "__main__":
    pdfs = generate_all()
    render_pngs(pdfs)
    for pdf in pdfs:
        print(pdf.name)
