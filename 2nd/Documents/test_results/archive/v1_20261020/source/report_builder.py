"""Render two Korean PDF reports from completed, auditable experiment evidence.

No values in the reports are fabricated. This module does not start experiments.
Usage: python report_builder.py path/to/evidence/analysis.json
The caller must mark the PDF artifact operation before the first invocation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from itertools import product
import hashlib
import json
import math
from pathlib import Path
import statistics
from xml.sax.saxutils import escape

import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


HERE = Path(__file__).resolve().parent
DEFAULT_EVIDENCE = HERE.parents[1] / "Documents/test_results/evidence"
FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"
FONT = "Korean"
ARMS = ["A", "B", "R0", "RF", "RH"]
LABELS = {
    "A": "현재 symbol_index",
    "B": "파일 간 원문 확장",
    "R0": "원문 검색만",
    "RF": "원문 + 함수 요약",
    "RH": "원문 + 계층 요약",
}
CATEGORY = {
    "single_function": "함수 하나",
    "cross_file": "파일 간 흐름",
    "boundary": "경계 조건",
    "semantic": "자연어로 찾기",
    "change_impact": "변경 영향",
    "architecture": "호출 구조",
}
PROJECTS = {
    "eval_pricing": "가격 계산",
    "eval_authorization": "접근 권한",
    "eval_routing": "요청 경로",
    "eval_inventory": "재고 예약",
    "eval_cache": "캐시 키",
    "eval_schedules": "예약 시간",
}
INK = colors.HexColor("#17303B")
MUTED = colors.HexColor("#5A7078")
TEAL = colors.HexColor("#087F8C")
PALE_TEAL = colors.HexColor("#E8F5F4")
BLUE = colors.HexColor("#4C78A8")
PALE_BLUE = colors.HexColor("#EDF3F9")
ORANGE = colors.HexColor("#C27628")
PALE_ORANGE = colors.HexColor("#FBF2E6")
RULE = colors.HexColor("#DCE5E8")
BG = colors.HexColor("#F6F8F8")
WHITE = colors.white
ARM_COLOR = {"A": BLUE, "B": colors.HexColor("#7798AD"), "R0": colors.HexColor("#9AAEAF"),
             "RF": colors.HexColor("#60AAA7"), "RH": TEAL}
W, H = A4
L, R = 43, W - 43
CW = R - L


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else ({} if default is None else default)


def read_jsonl(path):
    path = Path(path)
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else 0.0


def percentile(values, q):
    return float(np.percentile(values, q)) if values else 0.0


def fnum(value, digits=1):
    return f"{value:,.{digits}f}"


def pct(value, digits=1):
    return f"{value * 100:.{digits}f}%"


def signed(value, digits=1):
    return f"{value:+.{digits}f}"


def short_json(value, limit=110):
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= limit else text[:limit - 3] + "..."


def safe_text(value):
    return escape(str(value)).replace("\n", "<br/>")


class Evidence:
    """Use the saved raw records as the authoritative denominator."""

    def __init__(self, summary_path):
        path = Path(summary_path).resolve()
        self.root = path if path.is_dir() else path.parent
        self.analysis = read_json(path) if path.is_file() else {}
        self.protocol = read_json(self.root / "protocol.json")
        self.environment = read_json(self.root / "environment.json")
        self.qualitative_audit = read_json(self.root / "qualitative_audit.json")
        self.contrastive_cases = read_json(self.root / "contrastive_cases.json")
        self.output_diagnostics = read_json(self.root / "output_diagnostics.json")
        self.manifest = read_json(self.root / "dataset/manifest.json")
        self.tasks = read_json(self.root / "dataset/eval_tasks.json", [])
        self.task_map = {t["id"]: t for t in self.tasks}
        self.rows = read_jsonl(self.root / "results_eval_main.jsonl")
        self.sensitivity = read_jsonl(self.root / "results_eval_budget512.jsonl")
        self.calls = read_jsonl(self.root / "model_calls.jsonl")
        self.assets = [read_json(p) for p in sorted((self.root / "assets").glob("*.json"))]
        if not self.tasks or not self.rows:
            raise ValueError("Completed evaluation tasks and result records are required.")
        self.projects = sorted({t["project"] for t in self.tasks})
        self.repeats = int(self.protocol.get("repeats", 3))
        self.by_arm = {arm: [r for r in self.rows if r["arm"] == arm] for arm in ARMS}
        expected_keys = {(t["id"], arm, repeat) for t in self.tasks for arm in ARMS
                         for repeat in range(self.repeats)}
        actual_keys = [(r["task_id"], r["arm"], r["repeat"]) for r in self.rows]
        if len(actual_keys) != len(set(actual_keys)) or set(actual_keys) != expected_keys:
            raise ValueError("Main results are incomplete, duplicated, or contain unexpected records.")
        diagnostic_sets = self.output_diagnostics.get("datasets", {})
        for result_path in sorted(self.root.glob("results_eval_*.jsonl")):
            diagnostic = diagnostic_sets.get(result_path.name)
            current_rows = read_jsonl(result_path)
            if (not diagnostic
                    or diagnostic.get("summary", {}).get("rows") != len(current_rows)
                    or diagnostic.get("ignored_incomplete_final_rows", 0)
                    or diagnostic.get("snapshot_sha256") != hashlib.sha256(result_path.read_bytes()).hexdigest()):
                raise ValueError(f"Output diagnostics must be regenerated from final results: {result_path.name}")
            for arm in {row["arm"] for row in current_rows}:
                arm_rows = [row for row in current_rows if row["arm"] == arm]
                arm_diag = diagnostic.get("by_arm", {}).get(arm, {})
                if (arm_diag.get("rows") != len(arm_rows)
                        or arm_diag.get("strict_correct") != sum(bool(row["correct"]) for row in arm_rows)):
                    raise ValueError(f"Output diagnostics mismatch: {result_path.name} {arm}")
        if self.output_diagnostics.get("primary_scoring_modified") is not False:
            raise ValueError("Output diagnostic must preserve the strict primary scores.")
        self.main_diagnostics = diagnostic_sets["results_eval_main.jsonl"]["by_arm"]
        self.task_scores = {arm: {
            task["id"]: mean([float(r["correct"]) for r in self.by_arm[arm] if r["task_id"] == task["id"]])
            for task in self.tasks} for arm in ARMS}
        self.metrics = {arm: self._metrics(self.by_arm[arm]) for arm in ARMS}
        self.category = {cat: {arm: self._metrics([r for r in self.by_arm[arm] if r["category"] == cat])
                              for arm in ARMS} for cat in CATEGORY}
        self.comparisons = {f"{new}-{old}": self._compare(old, new)
                            for old, new in [("A", "RH"), ("A", "B"), ("R0", "RH"), ("RF", "RH")]}
        self.build_calls = [c for c in self.calls if c.get("purpose", "").startswith("build_")
                            and c.get("meta", {}).get("project") in self.projects]
        self.build_seconds = sum(c.get("wall_seconds", 0) for c in self.build_calls)
        self.build_input = sum(c.get("input_tokens", 0) for c in self.build_calls)
        self.build_output = sum(c.get("output_tokens") or 0 for c in self.build_calls)
        self.eval_assets = [a for a in self.assets if a.get("project") in self.projects]
        self.build_wall = sum(a.get("build_seconds", 0) for a in self.eval_assets)
        # The separately audited analysis is authoritative when supplied.
        field_map = {"mean_input_tokens": "input", "mean_output_tokens": "output",
                     "mean_query_seconds": "seconds", "median_query_seconds": "p50",
                     "p95_query_seconds": "p95", "mean_context_tokens": "context",
                     "raw_evidence_recall": "raw_recall", "all_raw_evidence": "all_raw",
                     "accuracy": "accuracy", "correct": "correct", "total": "n"}
        for arm, metric in self.analysis.get("metrics_by_arm", {}).items():
            if arm not in self.metrics:
                continue
            for source, destination in field_map.items():
                if source in metric:
                    self.metrics[arm][destination] = metric[source]
            for cat, values in metric.get("by_category", {}).items():
                if cat in self.category:
                    for source, destination in field_map.items():
                        if source in values:
                            self.category[cat][arm][destination] = values[source]
        for key, comparison in self.analysis.get("comparisons", {}).items():
            if key in self.comparisons:
                self.comparisons[key].update(comparison)
                if "relative_accuracy_change_pct" in comparison:
                    self.comparisons[key]["relative_pct"] = comparison["relative_accuracy_change_pct"]
        build = self.analysis.get("build", {})
        self.build_seconds = build.get("seconds", self.build_seconds)
        self.build_input = build.get("input_tokens", self.build_input)
        self.build_output = build.get("output_tokens", self.build_output)
        self.stable_tasks = sum(
            len({json.dumps(r["parsed_answer"], sort_keys=True, separators=(",", ":"))
                 for r in self.by_arm[arm] if r["task_id"] == task["id"]}) == 1
            for arm in ARMS for task in self.tasks
        )

    def _metrics(self, rows):
        per_task = defaultdict(list)
        for row in rows:
            per_task[row["task_id"]].append(row["query_seconds"])
        query_times = [statistics.median(values) for values in per_task.values()]
        return {
            "n": len(rows),
            "correct": sum(bool(r["correct"]) for r in rows),
            "accuracy": mean([float(r["correct"]) for r in rows]),
            "raw_recall": mean([r.get("raw_evidence_recall") for r in rows]),
            "provenance_recall": mean([r.get("provenance_recall_not_content_recall") for r in rows]),
            "all_raw": mean([float(r.get("all_raw_evidence", False)) for r in rows]),
            "input": mean([r["input_tokens"] for r in rows]),
            "output": mean([r["output_tokens"] for r in rows]),
            "context": mean([r["context_tokens"] for r in rows]),
            "seconds": mean(query_times),
            "p50": percentile(query_times, 50),
            "p95": percentile(query_times, 95),
            "model_seconds": mean([r["model_seconds"] for r in rows]),
        }

    def _compare(self, old, new):
        ds = {tid: self.task_scores[new][tid] - self.task_scores[old][tid] for tid in self.task_map}
        project_d = np.array([mean([ds[t["id"]] for t in self.tasks if t["project"] == p])
                              for p in self.projects])
        draws = np.array([mean(list(sample)) for sample in product(project_d, repeat=len(project_d))])
        ci = np.percentile(draws, [2.5, 97.5]) * 100
        delta = mean(list(ds.values())) * 100
        return {"delta_pp": delta, "ci95_pp": [float(ci[0]), float(ci[1])],
                "win": sum(d > 0 for d in ds.values()), "loss": sum(d < 0 for d in ds.values()),
                "tie": sum(d == 0 for d in ds.values()),
                "relative_pct": (self.metrics[new]["accuracy"] / self.metrics[old]["accuracy"] - 1) * 100
                if self.metrics[old]["accuracy"] else None,
                "project_deltas": project_d.tolist()}

    def headline(self):
        comp = self.comparisons["RH-A"]
        delta, ci = comp["delta_pp"], comp["ci95_pp"]
        scores = [score for arm in ("A", "RH") for score in self.task_scores[arm].values()]
        if all(score in (0, 1) for score in scores):
            counts = {arm: sum(score == 1 for score in self.task_scores[arm].values())
                      for arm in ("A", "RH")}
            return (f"서로 다른 {len(self.tasks)}문제 중 현재 방식은 {counts['A']}개, "
                    f"계층 요약 방식은 {counts['RH']}개를 맞혔습니다.")
        if delta > 0:
            return "이번 시험의 평균 정답률은 계층 요약 방식이 높았습니다."
        if delta < 0:
            return "이번 시험의 평균 정답률은 현재 방식이 높았습니다."
        return "두 방식의 평균 정답률은 같았습니다."

    def summary_verdict(self):
        comp = self.comparisons["RH-R0"]
        raw_supplement = self.main_diagnostics["R0"]["order_tolerant_accuracy"]
        hierarchy_supplement = self.main_diagnostics["RH"]["order_tolerant_accuracy"]
        diagnostic_note = (
            f" 출력 순서 오류만 제외한 사후 보조 점수는 두 방식 모두 {pct(raw_supplement)}입니다."
            if raw_supplement == hierarchy_supplement and comp["delta_pp"] != 0 else ""
        )
        if comp["delta_pp"] > 0:
            return f"같은 원문 검색에 계층 요약을 더한 주 정답률 차이는 {signed(comp['delta_pp'])}%p였습니다." + diagnostic_note
        if comp["delta_pp"] < 0:
            return f"같은 원문 검색에 계층 요약을 더하자 주 정답률이 {abs(comp['delta_pp']):.1f}%p 낮아졌습니다." + diagnostic_note
        return "같은 원문 검색에 계층 요약을 더해도 평균 정답률은 달라지지 않았습니다."

    def recommendations(self):
        a, rh, raw = (self.metrics[k] for k in ("A", "RH", "R0"))
        delta = rh["accuracy"] - a["accuracy"]
        speed = rh["seconds"] - a["seconds"]
        if delta > 0:
            quality = "RH의 정답률이 높고"
        elif delta < 0:
            quality = "RH의 정답률이 낮고"
        else:
            quality = "두 방식의 정답률이 같고"
        timing = "RH가 빨랐습니다." if speed < 0 else "A가 빨랐습니다." if speed > 0 else "시간도 같았습니다."
        comparison = f"이번 조건에서는 {quality} {timing}"
        if raw["accuracy"] > max(a["accuracy"], rh["accuracy"]):
            control = " R0의 정답률은 두 방식보다 높았습니다."
        elif rh["accuracy"] > a["accuracy"] and raw["accuracy"] >= rh["accuracy"]:
            control = " R0도 RH만큼 정확해 계층 요약의 추가 이득은 없었습니다."
        elif raw["accuracy"] > rh["accuracy"]:
            control = " R0가 RH보다 정확했습니다."
        else:
            control = ""
        build = self.analysis.get("build", {})
        raw_preparation = build.get("mean_raw_index_seconds", 0)
        preparation = {
            "A": build.get("mean_symbol_index_seconds", 0),
            "B": raw_preparation,
            "R0": raw_preparation,
            "RF": raw_preparation + sum(c.get("wall_seconds", 0) for c in self.build_calls
                                       if c.get("purpose") == "build_leaf") / len(self.projects),
            "RH": self.build_seconds / len(self.projects),
        }
        # A descriptive pilot priority, not a confirmatory winner claim:
        # quality first; tied quality -> measured query time -> preparation cost.
        candidate = min(ARMS, key=lambda arm: (-self.metrics[arm]["accuracy"],
                                               self.metrics[arm]["seconds"], preparation[arm]))
        if candidate == "B":
            b = self.metrics["B"]
            control = ""
            priority = (f" 파일 간 원문을 잇는 B는 {pct(b['accuracy'])}·{b['seconds']:.2f}초였습니다."
                        " 요약 준비비 없는 B를 실제 저장소에서 먼저 검증합니다.")
            if b["accuracy"] == raw["accuracy"] and b["seconds"] < raw["seconds"]:
                priority = (f" 요약 없이 파일 간 원문을 잇는 B도 {pct(b['accuracy'])}였고, "
                            f"{b['seconds']:.2f}초로 같은 점수인 R0의 {raw['seconds']:.2f}초보다 빨랐습니다. "
                            "B를 실제 저장소에서 먼저 검증합니다.")
        elif candidate == "R0":
            priority = " 실제 저장소의 우선 검증 후보는 요약 준비비 없는 원문 검색 R0입니다."
        else:
            priority = f" 실제 저장소의 우선 검증 후보는 {LABELS[candidate]} {candidate}입니다."
        best_accuracy = max(self.metrics[arm]["accuracy"] for arm in ARMS)
        absolute = f" 최고 정답률도 {pct(best_accuracy)}인 파일럿입니다."
        return comparison + control + absolute + priority


class Page:
    def __init__(self, path, total, short=False):
        self.path, self.total, self.short = Path(path), total, short
        self.c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
        self.c.setTitle("symbol_index와 RAPTOR 정량평가" + (" - 그림으로 이해하기" if short else " - 상세보고서"))
        self.c.setAuthor("SecureCode | 재현 가능한 실험 보고서")
        self.page = 0
        self.layout_warnings = []

    def start(self, section, title, subtitle=None):
        if self.page:
            self.c.showPage()
        self.page += 1
        self.c.setFillColor(WHITE)
        self.c.rect(0, 0, W, H, fill=1, stroke=0)
        self.text(L, H - 34, "SECURECODE  /  RESEARCH NOTE", 8.3, MUTED)
        self.text(R, H - 34, f"{self.page:02d}  /  {self.total:02d}", 8.3, MUTED, "right")
        self.c.setStrokeColor(RULE)
        self.c.line(L, H - 47, R, H - 47)
        self.text(L, H - 76, section, 9.2, TEAL)
        title_height = self.para(title, L, H - 91, CW, 24 if self.short else 21, leading=31 if self.short else 28)
        y = H - 91 - title_height - 13
        if subtitle:
            y -= self.para(subtitle, L, y, CW, 10.4, MUTED, 15)
            y -= 14
        self.c.setStrokeColor(RULE)
        self.c.line(L, 38, R, 38)
        self.text(L, 24, "2026.10.20  |  합성 Python 코드에 대한 로컬 파일럿", 7.6, MUTED)
        self.text(R, 24, "근거: 함께 저장된 evidence 원본", 7.6, MUTED, "right")
        return y

    def text(self, x, y, value, size=10, color=INK, align="left"):
        self.c.setFillColor(color)
        self.c.setFont(FONT, size)
        fn = self.c.drawRightString if align == "right" else self.c.drawCentredString if align == "center" else self.c.drawString
        fn(x, y, str(value))

    def para(self, value, x, top, width, size=10, color=INK, leading=None):
        style = ParagraphStyle("p", fontName=FONT, fontSize=size, leading=leading or size * 1.5,
                               textColor=color, wordWrap="CJK", alignment=TA_LEFT,
                               splitLongWords=True, spaceBefore=0, spaceAfter=0)
        p = Paragraph(safe_text(value), style)
        _, h = p.wrap(width, 1000)
        p.drawOn(self.c, x, top - h)
        if top > 45 and top - h < 48:
            self.layout_warnings.append((self.page, round(top - h, 1), str(value)[:65]))
        return h

    def box(self, x, top, width, height, fill=BG, stroke=None, radius=8):
        self.c.setFillColor(fill)
        self.c.setStrokeColor(stroke or fill)
        self.c.roundRect(x, top - height, width, height, radius, fill=1, stroke=bool(stroke))
        if top > 45 and top - height < 48:
            self.layout_warnings.append((self.page, round(top - height, 1), "box"))

    def note(self, title, body, top, fill=PALE_TEAL, height=None, size=10):
        body_h = self.measure(body, CW - 28, size)
        height = height or 42 + body_h
        self.box(L, top, CW, height, fill)
        self.text(L + 14, top - 22, title, 10.4, TEAL if fill == PALE_TEAL else ORANGE)
        self.para(body, L + 14, top - 32, CW - 28, size, INK)
        return top - height - 15

    def measure(self, value, width, size=10):
        style = ParagraphStyle("m", fontName=FONT, fontSize=size, leading=size * 1.5, wordWrap="CJK")
        return Paragraph(safe_text(value), style).wrap(width, 2000)[1]

    def section(self, title, top):
        self.text(L, top - 12, title, 12, INK)
        return top - 27

    def table(self, headers, rows, top, widths=None, font=9.1, row_h=32):
        widths = widths or [CW / len(headers)] * len(headers)
        self.box(L, top, CW, 29, PALE_BLUE, radius=3)
        x = L
        for heading, width in zip(headers, widths):
            self.para(heading, x + 8, top - 7, width - 16, font, INK, font * 1.25)
            x += width
        top -= 29
        for i, row in enumerate(rows):
            cell_heights = [self.measure(cell, width - 16, font) for cell, width in zip(row, widths)]
            h = max(row_h, max(cell_heights, default=0) + 14)
            if i % 2 == 0:
                self.box(L, top, CW, h, BG, radius=0)
            x = L
            for cell, width in zip(row, widths):
                self.para(cell, x + 8, top - 7, width - 16, font, INK, font * 1.5)
                x += width
            top -= h
        return top - 16

    def metric(self, x, top, width, title, value, detail, color=TEAL):
        self.box(x, top, width, 105, PALE_TEAL if color == TEAL else PALE_BLUE)
        self.text(x + 13, top - 23, title, 9.7, MUTED)
        self.text(x + 13, top - 61, value, 27, color)
        self.para(detail, x + 13, top - 75, width - 26, 8.2, MUTED, 11)

    def bars(self, values, top, maximum=100, suffix="%", labels=None, width=CW, x=L, row_h=39):
        label_w, right_w = (144 if width > 400 else 75), 52
        plot_w = width - label_w - right_w
        for arm, value in values:
            label = labels[arm] if labels else f"{arm}  {LABELS[arm]}"
            self.text(x, top - 17, label, 9.5, INK)
            by = top - 21
            self.c.setFillColor(RULE)
            self.c.roundRect(x + label_w, by, plot_w, 12, 4, fill=1, stroke=0)
            self.c.setFillColor(ARM_COLOR.get(arm, TEAL))
            bar_w = max(0, min(plot_w, plot_w * value / maximum)) if maximum else 0
            if bar_w:
                self.c.roundRect(x + label_w, by, bar_w, 12, min(4, bar_w / 2), fill=1, stroke=0)
            self.text(x + width, top - 18, f"{value:.1f}{suffix}", 10.2, INK, "right")
            top -= row_h
        return top - 8

    def arrow(self, x1, y1, x2, y2, color=MUTED):
        c = self.c
        c.setStrokeColor(color)
        c.setLineWidth(1.2)
        c.line(x1, y1, x2, y2)
        ang = math.atan2(y2 - y1, x2 - x1)
        for a in (-0.5, 0.5):
            c.line(x2, y2, x2 - 6 * math.cos(ang + a), y2 - 6 * math.sin(ang + a))

    def flow(self, labels, top, subtitle=None, color=PALE_BLUE):
        gap = 16
        bw = (CW - gap * (len(labels) - 1)) / len(labels)
        h = 65
        for idx, label in enumerate(labels):
            x = L + idx * (bw + gap)
            self.box(x, top, bw, h, color)
            self.para(label, x + 11, top - 15, bw - 22, 10.5, INK, 15)
            if idx < len(labels) - 1:
                self.arrow(x + bw + 2, top - h / 2, x + bw + gap - 2, top - h / 2)
        top -= h + 12
        if subtitle:
            top -= self.para(subtitle, L, top, CW, 9.2, MUTED)
        return top - 17

    def end(self):
        if self.page != self.total:
            raise AssertionError(f"Unexpected page count {self.page}, wanted {self.total}")
        self.c.save()
        if self.layout_warnings:
            raise ValueError(f"PDF content enters footer area: {self.path.name}: {self.layout_warnings}")


def comparison_line(e, key):
    c = e.comparisons[key]
    lo, hi = c["ci95_pp"]
    return f"{signed(c['delta_pp'])}%p  [95% 구간 {signed(lo)}, {signed(hi)}]"


def draw_category_chart(p, e, top, short=False):
    label_w, plot_w, maxv = 86, CW - 164, 100
    for category in CATEGORY:
        p.text(L, top - 17, CATEGORY[category], 9.3)
        for idx, arm in enumerate(["A", "RH"]):
            val = e.category[category][arm]["accuracy"] * 100
            by = top - 14 - idx * 11
            p.c.setFillColor(ARM_COLOR[arm])
            p.c.rect(L + label_w, by, plot_w * val / maxv, 7, fill=1, stroke=0)
            p.text(R, by - 1, f"{val:.0f}%", 8.3, ARM_COLOR[arm], "right")
        n = sum(t["category"] == category for t in e.tasks)
        p.text(L + label_w, top - 36, f"고유 문제 {n}개", 7.5, MUTED)
        top -= 48 if short else 46
    p.text(L, top + 1, "파랑 = A 현재 방식     청록 = RH 계층 요약", 8.5, MUTED)
    return top - 22


def detailed(e, output):
    p = Page(output, 10)
    main = e.comparisons["RH-A"]
    a, rh = e.metrics["A"], e.metrics["RH"]
    n, npj = len(e.tasks), len(e.projects)
    y = p.start("01  /  핵심 결과", "symbol_index와 계층 요약 RAPTOR,\n어떤 방식이 얼마나 나은가",
                "현재 구현과 확장 구현을 같은 문제·모델·근거 자료 예산에서 직접 비교한 재현 가능한 파일럿")
    y = p.note("결론부터", e.headline(), y, size=11)
    card_w = (CW - 20) / 3
    p.metric(L, y, card_w, "현재 방식 A", pct(a["accuracy"]), f"{a['correct']} / {a['n']} 응답 정답", BLUE)
    p.metric(L + card_w + 10, y, card_w, "계층 요약 RH", pct(rh["accuracy"]), f"{rh['correct']} / {rh['n']} 응답 정답")
    p.metric(L + 2 * (card_w + 10), y, card_w, "정답률 차이 RH - A", f"{signed(main['delta_pp'])}%p",
             f"고유 문제 {n}개 · 프로젝트 {npj}개")
    y -= 123
    y = p.section("다섯 가지 방식의 정답률", y)
    y = p.bars([(arm, e.metrics[arm]["accuracy"] * 100) for arm in ARMS], y, row_h=26)
    lo, hi = main["ci95_pp"]
    y -= p.para(f"RH - A의 프로젝트 단위 탐색적 95% 구간: {signed(lo)}~{signed(hi)}%p. "
                "6개 프로젝트의 효과 추정치이며, 통계적으로 우위가 확정됐다는 뜻은 아닙니다.", L, y, CW, 9.4, MUTED)
    y -= 16
    y = p.note("요약 자체의 기여를 분리", e.summary_verdict() + " 현재 방식과의 차이에는 검색 방식과 파일 간 원문 확장도 함께 작용합니다.", y, size=9.7)
    p.note("해석 범위", "알고리즘이 다른 작은 합성 Python 프로젝트 6개의 코드 이해 평가입니다. 공통 파일 구조·보조 모듈을 공유합니다. 실제 저장소·코드 수정·요약 갱신 및 원논문 RAPTOR 전체는 평가하지 않았습니다.", y, PALE_ORANGE, size=9.3)

    y = p.start("02  /  무엇을 비교했는가", "이름을 찾는 색인에서,\n원문과 여러 수준의 요약을 함께 찾는 방식으로")
    y = p.flow(["질문", "함수 이름·위치\nsymbol_index", "관련 코드 원문", "모델의 답"], y,
               "A: 후보 24개 중 모델이 심볼을 고르고 같은 파일의 원문을 묶습니다.")
    y = p.flow(["함수와 의존 코드", "함수 요약", "파일 요약", "프로젝트 요약"], y, color=PALE_TEAL,
               subtitle="RH: 함수 묶음 → 파일 → 프로젝트 순서로 요약을 만들고, 원문과 모든 수준의 요약을 함께 검색합니다.")
    rows = [
        ["A", "현재 filtered_select_bundle", "모델이 심볼 선택 + 같은 파일 확장"],
        ["B", "A의 파일 간 확장 대조군", "같은 선택·2회 확장·최대 함수 8개"],
        ["R0", "요약 없는 검색 대조군", "개별 원문 + 의존 묶음의 TF-IDF"],
        ["RF", "평면 요약", "R0 + 함수 수준 요약"],
        ["RH", "계층 요약", "RF + 파일 요약 + 프로젝트 요약"],
    ]
    y = p.table(["구분", "방법", "차이"], rows, y, [37, 167, CW - 204], font=8.8, row_h=30)
    y = p.note("공정성을 위한 고정 조건", "R0·RF·RH는 같은 원문 기반 단어 가중치·코사인 검색, 동일 원문 후보와 예산을 사용합니다. 개별 원문과 깊이 3 의존 묶음 중 이미 선택된 source URI로 완전히 덮이는 원문 노드만 건너뜁니다. 일부 중복은 가능합니다.", y, size=9)
    p.note("RAPTOR라는 이름의 범위", "원논문의 임베딩·차원 축소·확률적 군집화 대신 AST·파일별로 묶고 TF-IDF로 찾습니다. 코드용 변형의 결과이며 원논문 전체 구현의 성능으로 볼 수 없습니다. B의 import 표기도 A와는 다릅니다.", y, PALE_ORANGE, size=9)

    y = p.start("03  /  실험 설계", "정답은 실행으로 확인하고,\n문제와 정답은 검색 자료에서 분리했습니다")
    hardware = str(e.environment.get("machdep.cpu.brand_string", "장비 정보 미기록"))
    if e.environment.get("hw.memsize"):
        hardware += f" · {int(e.environment['hw.memsize']) / (1024 ** 3):.0f}GiB"
    y = p.table(["데이터와 실행 조건", "설계"], [
        ["개발 / 평가·언어", f"개발 1프로젝트 8문제 / 평가 {npj}프로젝트 {n}문제. 질문은 영어"],
        ["반복과 비교", f"문제당 {e.repeats}회 × 5방식, 총 {len(e.rows):,}개 답변"],
        ["주 실험 근거 자료 예산", f"{e.protocol.get('main_budget', 1024):,} 모델 토큰; 질문·지시문 별도. 온전한 노드만 넣음"],
        ["보조 실험", "512토큰에서 R0·RH 각 1회; 예산 민감도만 확인"],
        ["모델 / 장비", f"Qwen2.5-Coder-7B-Instruct Q5_K_M, 로컬 llama.cpp\n{hardware}"],
        ["생성 설정", "temperature 0, seed 1, context 8192, 답변 최대 128토큰"],
        ["실행 순서", "고정 난수로 문제·방식·반복 순서를 섞음; prompt cache 비활성"],
        ["채점", "주지표: 정답 내용과 요청한 출력 순서를 모두 지킨 비율. 바깥 코드펜스만 제거"],
    ], y, [124, CW - 124], font=9.2, row_h=33)
    y = p.section("프로젝트마다 같은 분포로 8문제", y)
    y = p.table(["유형", "평가 문제", "확인하는 능력"], [
        ["함수 하나 / 경계 조건", "6 + 6", "단일 함수와 임계값 처리"],
        ["파일 간 흐름 / 자연어", "12 + 12", "의존 코드 연결과 함수명이 없는 질문"],
        ["변경 영향 / 호출 구조", "6 + 6", "지정 입력의 영향과 직접 호출 목록"],
    ], y, [170, 70, CW - 240], font=9.1, row_h=33)
    y = p.note("정답 검증", "실행형 문제는 별도 Python 프로세스의 실제 반환값을 수작업 기대값과 대조했습니다. 변경 영향은 지정 입력의 변경 전후 실행, 구조 문제는 AST의 직접 호출 목록으로 확인했습니다.", y, size=9.3)
    p.para("요약에는 코드만 입력하고 질문·정답은 검색 폴더 밖에 두었습니다. 개발 단계에서 질문의 중복 JSON 지시를 제거하고 바깥 코드펜스만 허용하도록 고정한 뒤 평가했습니다. required_uris는 보수적인 참조 목록이며 최소 필요 근거는 아닙니다.", L, y, CW, 8.9, MUTED)

    y = p.start("04  /  유형별 결과", "어느 종류의 질문에서\n차이가 생겼는가")
    y = draw_category_chart(p, e, y)
    y = p.table(["방식", "주 정답률", "순서만 오류", "순서무시\n보조 정답률", "지정 원문\n회수율", "모든 지정\n원문 포함"], [
        [arm, pct(e.metrics[arm]["accuracy"]), f"{e.main_diagnostics[arm]['order_only_failure_count']}회",
         pct(e.main_diagnostics[arm]["order_tolerant_accuracy"]),
         pct(e.metrics[arm]["raw_recall"]), pct(e.metrics[arm]["all_raw"])]
        for arm in ARMS
    ], y, [40, 70, 86, 98, 107, CW - 401], font=8.6, row_h=31)
    y = p.note("정답률과 원문 회수율은 다릅니다", "정답률은 실제 답이 맞은 비율입니다. 지정 참조 원문 회수율은 검증용 심볼 중 원문이 문맥에 실린 비율입니다. 출처 URI만 있으면 원문으로 세지 않았습니다. 지정 목록은 보수적이므로 회수율을 필요·충분한 사실의 비율로 해석하지 않습니다.", y, size=9)
    p.para("순서무시 보조 정답률은 같은 문자열 목록에서 정렬만 다른 답을 인정한 사후 진단입니다. 평가 도중 발견해 추가했으며 주지표를 대체하지 않습니다. 유형별 6~12문제의 차이도 탐색적으로만 해석합니다.", L, y, CW, 9.1, MUTED)

    y = p.start("05  /  원인 분리", "개선이 보인다면,\n검색·파일 확장·요약 중 무엇의 효과인가")
    y = p.table(["비교", "정답률 차이와 95% 구간", "분리해 보는 요인"], [
        ["RH - A", comparison_line(e, "RH-A"), "현재 방식에서 전체 변경의 효과"],
        ["B - A", comparison_line(e, "B-A"), "같은 선택기에서 파일 간 원문 확장"],
        ["RH - R0", comparison_line(e, "RH-R0"), "같은 검색기에 계층 요약 추가"],
        ["RH - RF", comparison_line(e, "RH-RF"), "함수 요약 위에 상위 요약 추가"],
    ], y, [63, 250, CW - 313], font=9.1, row_h=44)
    y = p.section("문제별로 짝지어 보면", y)
    y = p.table(["비교", "새 방식 우세", "기존 방식 우세", "동률"], [
        [key, e.comparisons[key]["win"], e.comparisons[key]["loss"], e.comparisons[key]["tie"]]
        for key in ["RH-A", "B-A", "RH-R0", "RH-RF"]
    ], y, [90, 139, 139, CW - 368], font=9.3, row_h=33)
    y -= p.para("승패는 같은 문제의 3회 평균 정답 점수를 비교합니다. 144회 응답을 서로 독립인 144문제로 세지 않습니다. 모든 표의 차이는 뒤 방식 대비 앞 방식이며, 양수면 앞 방식이 우세합니다.", L, y, CW, 9.4, MUTED)
    y -= 17
    rel = main["relative_pct"]
    rel_text = f"상대 변화는 {signed(rel)}%입니다." if rel is not None else "A의 정답률이 0%이므로 상대 변화율은 정의하지 않습니다."
    y = p.note("%p와 %는 구분합니다", f"A {pct(a['accuracy'])}에서 RH {pct(rh['accuracy'])}로 바뀌면 정답률 차이는 {signed(main['delta_pp'])}%p입니다. {rel_text} 본 보고서는 차이를 %p로 우선 표시합니다.", y, size=9.6)
    p.note("해석의 중심", "RH - A만으로 요약의 독립적인 효과를 주장할 수 없습니다. 같은 검색기에 요약을 추가한 RH - R0와 상위 요약만 추가한 RH - RF를 함께 판단합니다.", y, PALE_ORANGE, size=9.4)

    y = p.start("06  /  속도와 비용", "답을 얻는 비용과,\n요약을 미리 만드는 비용을 나누어 봅니다")
    y = p.table(["방식", "평균 근거", "평균 입력", "평균 출력", "평균 지연", "중앙 / 95백분위"], [
        [arm, f"{e.metrics[arm]['context']:,.0f}",
         f"{e.metrics[arm]['input']:,.0f}", f"{e.metrics[arm]['output']:,.0f}",
         f"{e.metrics[arm]['seconds']:.2f}초",
         f"{e.metrics[arm]['p50']:.2f} / {e.metrics[arm]['p95']:.2f}초"]
        for arm in ARMS
    ], y, [34, 72, 72, 72, 84, CW - 334], font=8.7, row_h=30)
    both_n, both_ratio = main.get("both_success_n"), main.get("both_success_latency_ratio")
    if both_n is None:
        both_ids = [tid for tid in e.task_map if e.task_scores["A"][tid] == e.task_scores["RH"][tid] == 1]
        both_n = len(both_ids)
        both_ratio = (e._metrics([r for r in e.by_arm["RH"] if r["task_id"] in both_ids])["seconds"] /
                      e._metrics([r for r in e.by_arm["A"] if r["task_id"] in both_ids])["seconds"]) if both_n else None
    success_note = (f"둘 다 항상 정답인 {both_n}문제에서 RH/A 시간 비는 {both_ratio:.2f}배(1 미만이면 RH가 빠름)입니다."
                    if both_n and both_ratio is not None else "둘 다 항상 정답인 문제가 없어 성공 조건의 속도는 비교할 수 없습니다.")
    y -= p.para("입력토큰은 선택기+답변, 근거토큰은 전달된 코드·요약입니다. 1024는 상한입니다. "
                "시간은 성공·실패의 3회 중앙값을 평균해 빠른 오답도 포함합니다. "
                "A·B의 공유 선택비용은 각각 전액 합산하며 토큰화·HTTP도 포함합니다. " + success_note,
                L, y, CW, 9.1, MUTED)
    y -= 12
    y = p.section("평가 프로젝트 6개 전체의 최초 요약 구축", y)
    y = p.table(["항목", "측정값"], [
        ["요약 생성 호출", f"{len(e.build_calls):,}회"],
        ["요약 입력 / 출력 토큰", f"{e.build_input:,} / {e.build_output:,}"],
        ["원문 준비·요약 구축 경과시간 합", f"{e.build_seconds:,.1f}초 ({e.build_seconds / 60:.1f}분)"],
    ], y, [230, CW - 230], font=9.6, row_h=30)
    bs = e.analysis.get("build", {})
    break_even_keys = ("time_break_even_questions_per_project_vs_A",
                       "time_break_even_questions_per_project_vs_R0")
    if any(key not in bs for key in break_even_keys):
        raise ValueError("The audited analysis must supply per-project time break-even values.")
    save = a["seconds"] - rh["seconds"]
    breakeven = bs[break_even_keys[0]]
    if breakeven is not None:
        body = (f"평균 질의당 RH가 A보다 {save:.2f}초 적게 걸렸습니다. 측정한 구축 시간을 선투자 비용으로 놓으면 "
                f"A의 초기 색인비를 뺀 추가 비용은 프로젝트당 약 {breakeven:,}회 질의 후 회수합니다. "
                "평균 프로젝트·질문 구성을 가정한 외삽이며 실제 그 횟수만큼 실행한 결과가 아닙니다.")
    else:
        body = ("RH의 평균 온라인 질의 시간이 A보다 짧지 않았습니다. "
                "따라서 측정된 시간만으로는 요약 구축비를 회수하는 질의 수가 존재하지 않습니다.")
    raw_break = bs[break_even_keys[1]]
    if raw_break is None:
        body += " R0보다 질의가 빠르지 않아 R0 대비 시간 회수점은 없습니다."
    else:
        raw_saving = e.metrics["R0"]["seconds"] - rh["seconds"]
        body += (f" R0 대비 차이는 질의당 {raw_saving:.3f}초로 작습니다. 이를 그대로 외삽한 회수점은 "
                 f"프로젝트당 약 {raw_break:,}회이며, 실제 회수를 검증한 결과가 아닙니다.")
    y = p.note("시간 기준 손익분기점", body, y, size=9.2)
    idx = bs.get("mean_symbol_index_seconds")
    raw_idx = bs.get("mean_raw_index_seconds")
    preprocess = (f"프로젝트당 원문 준비: A {idx * 1000:.3f}ms, 검색용 {raw_idx * 1000:.3f}ms. "
                  if idx is not None and raw_idx is not None else "")
    p.para(preprocess + "A와의 시간 차이에는 선택기 호출 제거와 입력량 차이가 함께 반영됩니다. 별도 임베딩 모델은 사용하지 않았고, 서버 시작·요약 갱신·전력비는 측정하지 않았습니다. API 요금으로 환산하지 않았습니다.", L, y, CW, 9.1, MUTED)

    y = p.start("07  /  답이 달라진 실제 사례", "같은 질문에서도\n맞는 답과 틀린 답이 갈렸습니다")
    contrast_text = {
        "eval_authorization__own_write": (
            "A 오답 → RH 정답: 상수의 이름과 실제 값",
            "자신의 문서에 쓰기 권한이 있을 때 authorize가 반환하는 객체",
            "A 문맥에는 ALLOW_REASON이라는 이름만 있고 값 정의가 없습니다. RH에는 원문의 "
            "ALLOW_REASON = \"allowed\"와 파일 간 보조 함수가 있습니다. 요약 없는 R0도 정답이므로, "
            "이 개선을 요약 자체의 효과로 귀속할 수 없습니다.",
        ),
        "eval_pricing__direct_calls": (
            "R0 정답 → RH 오답: 정확한 직접 호출 관계",
            "checkout_total이 직접 호출하는 프로젝트 함수 세 개",
            "R0는 실제 함수 본문을 읽고 세 함수를 맞혔습니다. RH는 1024토큰을 모두 요약으로 채웠고 "
            "원문 노드는 0개였습니다. 함수 이름 일부는 요약에 있지만 정확한 직접 호출 관계가 약해졌습니다. "
            "이 변화가 오답의 유일한 원인이라고 확정한 것은 아닙니다.",
        ),
    }
    contrasts = {case["task_id"]: case for case in e.contrastive_cases.get("cases", [])}
    for idx, tid in enumerate(contrast_text, 1):
        if tid not in contrasts:
            raise ValueError(f"Missing audited contrasting case: {tid}")
        case = contrasts[tid]
        repeat = case["repeat_zero_based"]
        observations = dict(case["observations"])
        if case.get("additional_control"):
            observations[case["additional_control"]["arm"]] = case["additional_control"]
        for arm, observation in observations.items():
            matches = [r for r in e.by_arm[arm] if r["task_id"] == tid and r["repeat"] == repeat]
            if len(matches) != 1:
                raise ValueError(f"Contrastive record identity is not unique: {tid} {arm} {repeat}")
            record = matches[0]
            if (json.dumps(record["parsed_answer"], sort_keys=True) != json.dumps(observation["observed_answer"], sort_keys=True)
                    or json.dumps(record["expected"], sort_keys=True) != json.dumps(case["gold"], sort_keys=True)
                    or record["correct"] != observation["correct"]
                    or hashlib.sha256(record["context"].encode()).hexdigest() != observation["context_sha256"]
                    or record["answer_call"]["call_id"] != observation["answer_call_id"]):
                raise ValueError(f"Contrastive case no longer matches final evidence: {tid} {arm} {repeat}")
        title, description, interpretation = contrast_text[tid]
        p.box(L, y, CW, 230, PALE_TEAL if idx == 1 else PALE_BLUE)
        p.text(L + 13, y - 21, f"사례 {idx}  |  {title}", 10.6, TEAL)
        p.text(L + 13, y - 36, f"{tid}  ·  {repeat + 1}번째 반복 (저장값 repeat={repeat})", 7.8, MUTED)
        p.para(description, L + 13, y - 48, CW - 26, 9.3, INK, 13)
        answer_lines = [f"정답: {short_json(case['gold'], 200)}"]
        for arm in observations:
            observation = observations[arm]
            outcome = "정답" if observation["correct"] else "오답"
            answer_lines.append(f"{arm} ({outcome}): {short_json(observation['observed_answer'], 200)}")
        answer_h = p.para("\n".join(answer_lines), L + 13, y - 73, CW - 26, 9.1, INK, 14)
        p.para(interpretation, L + 13, y - 82 - answer_h, CW - 26, 9.1, MUTED, 13.5)
        y -= 244
    y = p.note("사례를 읽는 방법", "같은 문제·같은 반복의 답과 실제 문맥을 맞춰 검토한 사후 사례입니다. 상수의 원문 접근, 검색 순위, 요약 내용, 모델의 읽기 능력이 함께 달라질 수 있습니다. 전체 우열은 앞의 집계 결과로 판단해야 합니다.", y, size=9.2)
    p.para("근거: evidence/contrastive_cases.json. 답변 ID와 문맥 SHA-256을 최종 results_eval_main.jsonl에 대조해 확인합니다.", L, y, CW, 8.6, MUTED)

    y = p.start("08  /  실패와 예외", "평균 점수에 가려진 사례를\n원문 기록으로 확인합니다")
    explanations = {
        "eval_inventory__safety_buffer": (
            "안전재고: 빠진 상수와 계산 실패",
            "재고 8개, 기예약 5개에서 1개 요청. 현재 시각은 200입니다.",
            "8 - 5 - 안전재고 3 = 0이므로 예약은 거절됩니다. R0는 지정 원문을 모두 읽고도 오답입니다. "
            "RH 문맥에는 안전재고 값 3이 없어 정확한 계산 근거가 빠졌습니다. 이 누락이 특정 오답의 유일한 원인이라고 확정한 것은 아닙니다.",
        ),
        "eval_pricing__refund": (
            "환불: 올바른 공식을 보고도 틀린 답",
            "1001센트를 지불한 3개 중 2개를 환불하는 계산입니다.",
            "1001 × min(2, 3) // 3 = 667입니다. 두 조건 모두 문맥에 원문 공식이 있고 RH 요약도 정확하지만 둘 다 1001이라고 답했습니다. "
            "이 실패는 검색 누락만으로 설명할 수 없습니다. 모델 내부의 계산 과정까지 관찰한 것은 아닙니다.",
        ),
    }
    audited = e.qualitative_audit.get("scored_examples", [])
    if len(audited) < 2:
        raise ValueError("Two audited qualitative examples are required for the failure page.")
    for idx, case in enumerate(audited[:2], 1):
        tid = case["task_id"]
        title, question, interpretation = explanations[tid]
        repeat = case["repeat_zero_based"]
        # Verify the illustration against the final saved records, not a partial analysis.
        for arm in ("R0", "RH"):
            record = next(r for r in e.by_arm[arm] if r["task_id"] == tid and r["repeat"] == repeat)
            if record["parsed_answer"] != case["observed_answer"][arm] or record["expected"] != case["gold"]:
                raise ValueError(f"Audited case no longer matches final result: {tid} {arm}")
        p.box(L, y, CW, 205, BG)
        p.text(L + 13, y - 21, f"사례 {idx}  |  {title}", 10.6, TEAL)
        p.text(L + 13, y - 36, f"{tid}  ·  {repeat + 1}번째 반복 (저장값 repeat={repeat})", 7.8, MUTED)
        p.para(question, L + 13, y - 47, CW - 26, 9.2, INK, 13)
        answers = (f"정답: {short_json(case['gold'], 200)}\n"
                   f"R0: {short_json(case['observed_answer']['R0'], 200)}\n"
                   f"RH: {short_json(case['observed_answer']['RH'], 200)}")
        answer_h = p.para(answers, L + 13, y - 72, CW - 26, 9.1, INK, 14)
        p.para(interpretation, L + 13, y - 80 - answer_h, CW - 26, 9.1, MUTED, 13.5)
        y -= 217
    failures = Counter(r["failure"] for r in e.rows if not r["correct"])
    labels = {"wrong_answer": "값 오답", "abstained": "답변 보류(null)", "invalid_json": "JSON 오류",
              "invalid_schema": "형식 오류", "selector_invalid": "심볼 선택 오류", "execution_or_limit": "실행/한도 오류"}
    failure_text = " · ".join(f"{labels.get(k, k)} {v}회" for k, v in failures.most_common()) or "기록된 실패 없음"
    y = p.note("전체 방식의 실패 분포", failure_text, y, size=9.1)
    y = p.note("별도 요약 관찰 · 채점되지 않은 사례", "한 요약은 원문에 없는 URL 인코딩 동작을 덧붙였습니다. 관련 문자는 평가 질문에서 시험하지 않았으므로, 이를 측정된 오답의 원인이나 전체 요약 오류율로 계산하지 않았습니다.", y, PALE_ORANGE, size=9)
    p.para("두 사례는 설명을 위해 선택한 동반 실패이며 RH의 승패나 대표적인 오류 빈도를 뜻하지 않습니다. 근거: evidence/qualitative_audit.json 및 해당 결과의 실제 context.", L, y, CW, 8.7, MUTED)

    y = p.start("09  /  불확실성과 판단", "이번 결과로 말할 수 있는 것과,\n다음 실험이 필요한 것을 구분합니다")
    y = p.note("권고 · 5개 방식의 후속 검증 우선순위", e.recommendations(), y, size=10.2)
    y = p.table(["확인한 범위", "아직 확인하지 않은 범위"], [
        ["합성 Python 6개: 각 5파일·31~32원문 노드", "실제 대규모 저장소, 언어·프레임워크 다양성"],
        ["48문제의 정확한 반환값·호출 관계", "버그 수정 성공률, 개발자의 실제 작업 시간"],
        ["고정 모델·프롬프트·근거 자료 예산", "다른 모델·임베딩·요약 전략과의 일반화"],
        ["한 번 생성해 고정한 요약과 최초 준비 비용", "요약 생성 변동성, 오래된 요약, 부분 갱신 비용"],
        ["AST/from-import로 확인 가능한 의존관계", "동적 디스패치·상속·복잡한 상대 import"],
    ], y, [CW / 2, CW / 2], font=9, row_h=33)
    y = p.section("불확실성을 계산한 방법", y)
    holm_main = e.comparisons["RH-A"]["holm_adjusted_p_two_planned"]
    holm_summary = e.comparisons["RH-R0"]["holm_adjusted_p_two_planned"]
    y -= p.para("문제별 반복 평균을 만들고 프로젝트 단위 복원 추출의 모든 조합(6⁶ = 46,656개)을 계산해 2.5·97.5백분위수를 표시했습니다. 6개 표본의 탐색적 구간입니다. 정확 부호 전환 검정의 최소 양측 p값은 0.03125이며, 2개 주요 비교의 Holm 보정 후 5% 유의수준에서 우위 확정은 불가능합니다. "
                f"실제 보정 p값은 RH-A {holm_main:.4f}, RH-R0 {holm_summary:.4f}입니다.", L, y, CW, 9.2)
    y -= 14
    y -= p.para(f"3회 답이 같았던 조합: {e.stable_tasks}/{n * len(ARMS)}개. 반복은 독립 표본을 늘리지 않습니다. 공통 파일 구조·보조 모듈을 공유하므로 실제 저장소 6개의 다양성과 다릅니다. 후속 후보는 정답률, 동률이면 질의시간과 준비비 순으로 선택했습니다.", L, y, CW, 9.1, MUTED)
    y -= 19
    y = p.note("후속 검증의 우선순위", "실제 저장소 확대와 사전 고정 문제 → 코드 수정·오래된 요약·갱신 비용 측정 → 임베딩·군집화를 적용한 RAPTOR와 원문 검색의 재비교 순으로 진행합니다.", y, size=9.3)
    if e.sensitivity:
        sm = {arm: e._metrics([r for r in e.sensitivity if r["arm"] == arm]) for arm in ["R0", "RH"]}
        p.para(f"512토큰 보조 실험: R0 {pct(sm['R0']['accuracy'])}, RH {pct(sm['RH']['accuracy'])}, "
               f"차이 {signed((sm['RH']['accuracy'] - sm['R0']['accuracy']) * 100)}%p. "
               "각 문제 1회만 수행한 민감도 점검으로 주 실험의 독립적인 재현으로 보지 않습니다.", L, y, CW, 9.1, MUTED)
    else:
        p.para("512토큰 보조 실험 기록은 이 보고서 생성 시점에 없습니다. 예산 민감도에 관한 결론은 내리지 않습니다.", L, y, CW, 9.3, MUTED)

    y = p.start("10  /  재현과 근거", "보고서의 숫자는\n함께 저장한 원본 기록에서 다시 계산할 수 있습니다")
    y = p.table(["파일 / 폴더", "확인할 수 있는 내용"], [
        ["evidence/protocol.json", "근거 자료 예산·모델 설정·대조군·주 비교 정의"],
        ["evidence/dataset/", "소스 코드, 평가 문제, 검증된 정답, 표본 구성"],
        ["evidence/assets/", "원문 묶음, 함수·파일·프로젝트 요약, 출처 연결"],
        ["evidence/results_eval_main.jsonl", "문제·방식·반복별 답변과 문맥, 비용, 성공 여부"],
        ["evidence/results_eval_budget512.jsonl", "512토큰 민감도 실험"],
        ["evidence/analysis.json · per_question_results.csv", "집계 수치와 스프레드시트로 볼 수 있는 문제별 결과"],
        ["evidence/model_calls.jsonl", "선택·요약·답변 모델의 프롬프트와 출력"],
        ["evidence/environment.json", "모델·구현 파일 해시, 시스템·실행기 버전"],
        ["2nd/experiments/symbol_raptor/", "데이터 생성, 실험 실행, 분석 및 보고서 생성 코드"],
    ], y, [227, CW - 227], font=8.2, row_h=27)
    y = p.section("실행 재현", y)
    y -= p.para("동일 GGUF 모델·로컬 서버를 준비하고 experiment.py의 prepare → build → dev → eval → sensitivity를 실행합니다. 모델·포트는 스크립트를 참조합니다. 분석과 보고서는 저장된 결과만 읽습니다.", L, y, CW, 8.7)
    y -= 16
    env = e.environment
    runtime = str(env.get("llama_version", "")).strip().replace("\n", " / ")
    hashes = [
        ["모델 SHA-256", str(env.get("model_sha256", "미기록"))[:24] + "..."],
        ["실험 코드 SHA-256", str(env.get("experiment_sha256", "미기록"))[:24] + "..."],
        ["코퍼스 코드 SHA-256", str(env.get("corpus_builder_sha256", "미기록"))[:24] + "..."],
        ["실행 환경", str(env.get("platform", "미기록"))],
        ["llama.cpp", runtime[:90] or "environment.json 참조"],
    ]
    y = p.table(["식별 정보", "값 (전체 해시는 environment.json)"], hashes, y, [144, CW - 144], font=8, row_h=23)
    y = p.section("참고 자료", y)
    y -= p.para("[1] Sarthi et al., RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval (2024).\nhttps://arxiv.org/html/2401.18059v1\n[2] 기존 프로젝트 설계 문서: 2nd/Documents/Md_Files/2026-10-05_세_가지_포인터_방식의_정량평가_실험설계와_동작원리.md\n[3] 본 보고서 근거: test_results/evidence/ 아래 실측 기록. 원논문 수치는 본 실험 결과로 재사용하지 않았습니다.", L, y, CW, 8.6, MUTED)
    p.end()


def newcomer(e, output):
    p = Page(output, 3, short=True)
    a, rh = e.metrics["A"], e.metrics["RH"]
    cmp = e.comparisons["RH-A"]
    y = p.start("01  /  처음 보는 분을 위한 3분 설명", "코드를 잘 찾아주면,\nAI의 답도 더 정확해질까?",
                "symbol_index와 계층 요약 방식의 차이를 작은 코드 실험으로 확인했습니다.")
    concepts = [
        ("코드·함수", "작업을 수행하는 조리법", "예: 가격을 계산하는 규칙"),
        ("symbol_index", "조리법의 이름과 위치를 적은 주소록", "필요한 원문으로 빠르게 이동"),
        ("계층 요약", "조리법 → 묶음 → 전체의 요약 노트", "여러 파일의 관계를 함께 탐색"),
    ]
    bw = (CW - 20) / 3
    for idx, (title, body, foot) in enumerate(concepts):
        x = L + idx * (bw + 10)
        p.box(x, y, bw, 151, PALE_BLUE if idx < 2 else PALE_TEAL)
        # A simple vector icon: source lines, index cards, and a hierarchy.
        if idx == 0:
            p.box(x + 14, y - 14, 36, 37, WHITE, RULE, 3)
            for row in range(3):
                p.c.setStrokeColor(BLUE)
                p.c.line(x + 21, y - 24 - row * 8, x + 43, y - 24 - row * 8)
        elif idx == 1:
            for row in range(3):
                p.box(x + 14 + row * 4, y - 14 - row * 9, 41, 17, WHITE, RULE, 2)
        else:
            p.box(x + 26, y - 13, 22, 12, WHITE, TEAL, 2)
            p.c.setStrokeColor(TEAL)
            p.c.line(x + 37, y - 25, x + 37, y - 34)
            p.c.line(x + 19, y - 34, x + 55, y - 34)
            for xx in (x + 12, x + 48):
                p.box(xx, y - 35, 16, 11, WHITE, TEAL, 2)
        p.text(x + 14, y - 70, title, 12.5, TEAL if idx == 2 else BLUE)
        p.para(body, x + 14, y - 81, bw - 28, 10.7, INK, 15)
        p.para(foot, x + 14, y - 121, bw - 28, 8.2, MUTED, 11)
    y -= 173
    y = p.section("같은 질문을 했을 때의 정답률", y)
    p.metric(L, y, bw, "현재 주소록 방식", pct(a["accuracy"]), "A · 원문을 찾아 답변", BLUE)
    p.metric(L + bw + 10, y, bw, "계층 요약 방식", pct(rh["accuracy"]), "RH · 원문 + 요약에서 답변")
    p.metric(L + 2 * (bw + 10), y, bw, "차이", f"{signed(cmp['delta_pp'])}%p", "퍼센트포인트 차이")
    y -= 121
    y -= p.para(e.headline(), L, y, CW, 13, INK, 20)
    y -= 19
    lo, hi = cmp["ci95_pp"]
    y = p.note("큰 숫자 옆에 꼭 필요한 조건", f"작은 합성 Python 프로젝트 6개, 서로 다른 문제 48개, 문제당 3회 반복의 결과입니다. "
               f"탐색적 95% 구간은 {signed(lo)}~{signed(hi)}%p입니다. 통계적으로 우위가 확정된 결과는 아닙니다.", y, PALE_ORANGE, size=10.2)
    p.para("코드의 동작과 요청한 답변 순서를 모두 맞혀야 정답입니다. 실제 제품의 버그를 고치거나 개발 시간을 줄이는지까지 확인한 결과는 아닙니다.", L, y, CW, 10.2, MUTED)

    y = p.start("02  /  왜 달라지는가", "주소록만 바꾼 것이 아니어서,\n요약의 효과를 따로 확인했습니다")
    y = p.flow(["질문", "주소록에서\n함수 선택", "관련 원문", "답변"], y, "현재 방식 A", PALE_BLUE)
    y = p.flow(["질문", "원문과\n여러 수준 요약", "관련 자료\n함께 선택", "답변"], y,
               "계층 요약 RH · 요약은 원문으로 돌아갈 수 있는 출처와 연결", PALE_TEAL)
    y = p.note("요약만 추가하면?", e.summary_verdict(), y, size=12)
    labels = {"R0": "R0 · 원문 검색만", "RF": "RF · + 함수 요약", "RH": "RH · + 파일·전체 요약"}
    y = p.bars([(arm, e.metrics[arm]["accuracy"] * 100) for arm in ["R0", "RF", "RH"]],
               y, labels=labels, row_h=34)
    y -= p.para("위 세 방식은 같은 검색 방법과 최대 자료 길이를 사용합니다. 차이는 요약의 추가 여부입니다.", L, y, CW, 10.5, MUTED)
    y -= 15
    largest = max(CATEGORY, key=lambda c: abs(e.category[c]["RH"]["accuracy"] - e.category[c]["A"]["accuracy"]))
    d = (e.category[largest]["RH"]["accuracy"] - e.category[largest]["A"]["accuracy"]) * 100
    y = p.note("차이가 가장 컸던 질문", f"'{CATEGORY[largest]}'에서 RH - A는 {signed(d)}%p였습니다. "
               "유형별 6~12문제의 탐색적 결과입니다.", y, PALE_BLUE, size=10.5)
    p.para("RAPTOR의 계층 요약 아이디어를 코드에 맞게 적용했습니다. 원논문의 모든 기술을 재현한 것은 아닙니다.", L, y, CW, 10.1, MUTED)

    y = p.start("03  /  그래서 무엇을 선택할까", "정답률뿐 아니라\n준비 시간과 적용 범위를 함께 봅니다")
    card_w = (CW - 12) / 2
    p.metric(L, y, card_w, "질문 하나의 평균 시간 · A", f"{a['seconds']:.2f}초", "검색 + 모델의 선택 + 답변", BLUE)
    p.metric(L + card_w + 12, y, card_w, "질문 하나의 평균 시간 · RH", f"{rh['seconds']:.2f}초", "검색 + 답변")
    y -= 122
    y = p.note("요약 노트를 만드는 준비 시간", f"평가 코드 6개 프로젝트의 최초 요약 준비에 경과시간 합계 {e.build_seconds / 60:.1f}분이 들었습니다. "
               "코드가 바뀌면 요약을 고치는 비용도 생길 수 있지만, 이번에는 측정하지 않았습니다.", y, size=10.8)
    y = p.note("이번 결과가 제안하는 다음 행동", e.recommendations(), y, size=11.4)
    y = p.section("확실히 기억할 세 가지", y)
    items = [
        ("01", "숫자는 이 시험의 성적표", "48개 작은 코드 문제에서 얻은 결과이며 모든 프로젝트의 성능은 아닙니다."),
        ("02", "요약은 틀리거나 빠뜨릴 수 있음", "출처가 연결되어 있어도, 실제 원문 근거가 충분히 들어왔는지는 별도로 확인해야 합니다."),
        ("03", "실제 도입은 다음 검증 후", "실제 저장소·코드 수정·변경 후 요약 갱신까지 시험해야 합니다."),
    ]
    for num, title, text in items:
        p.text(L, y - 19, num, 19, TEAL)
        p.text(L + 39, y - 16, title, 11.1, INK)
        p.para(text, L + 39, y - 25, CW - 39, 10.1, MUTED, 15)
        y -= 72
    p.para("자세한 표·실패 사례·실험 설정은 함께 제공한 상세보고서에 있습니다. "
           "모든 결과의 원본은 같은 폴더의 evidence에 저장했습니다.", L, y, CW, 9.6, MUTED)
    p.end()


def build(summary_path):
    """Build both final files only after the caller marks artifact authoring."""
    if not Path(FONT_PATH).is_file():
        raise FileNotFoundError(FONT_PATH)
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, FONT_PATH))
    evidence = Evidence(summary_path)
    out = evidence.root.parent
    out.mkdir(parents=True, exist_ok=True)
    paths = [
        out / "01_symbol_index와_RAPTOR_정량평가_상세보고서.pdf",
        out / "02_그림으로_이해하는_symbol_index와_RAPTOR_비교.pdf",
    ]
    detailed(evidence, paths[0])
    newcomer(evidence, paths[1])
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_path", nargs="?", type=Path, default=DEFAULT_EVIDENCE / "analysis.json")
    args = parser.parse_args()
    for path in build(args.summary_path):
        print(path)
