"""Render audited v1 + separately measured v2 reports after results are complete.

This renderer never mutates old evidence and never calls a model. Its numerical
inputs are checked against the saved result rows before any PDF is opened.
The caller marks the PDF edit operation before authoring or rendering.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

import numpy as np
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import report_builder as old


HERE = Path(__file__).resolve().parent
DEFAULT = old.DEFAULT_EVIDENCE / "revision_v2/summary_v2.json"
ARMS = ("A", "RH", "C")
NAMES = {"A": "현재 색인 A", "RH": "계층 요약 RH", "C": "본문 보존 압축 C"}
PALETTE = {"A": old.BLUE, "RH": old.TEAL, "C": colors.HexColor("#7662AA")}
PURPLE = PALETTE["C"]
PALE_PURPLE = colors.HexColor("#F0ECF7")
L, R, CW, H = old.L, old.R, old.CW, old.H


def read(path):
    return json.loads(Path(path).read_text())


def records(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def mean(values):
    values = list(values)
    return statistics.mean(values) if values else None


def metric_text(value, suffix="", decimals=1):
    return "미산출" if value is None else f"{value:,.{decimals}f}{suffix}"


def percentage(value):
    return metric_text(None if value is None else value * 100, "%")


def signed(value, unit="%p"):
    return "미산출" if value is None else f"{value:+.1f}{unit}"


def interval(value, unit="%p", decimals=1):
    if value is None:
        return "구간 미산출"
    return f"[{value[0]:+.{decimals}f}, {value[1]:+.{decimals}f}]{unit}"


def order_only(row):
    a, b = row.get("parsed_answer"), row.get("expected")
    if row["correct"] or row.get("failure") != "wrong_answer" or not row.get("answer_call", {}).get("ok"):
        return False
    if row.get("selector") is not None and not row["selector"].get("ok"):
        return False
    return (isinstance(a, list) and isinstance(b, list)
            and all(isinstance(x, str) for x in a + b)
            and len(a) == len(set(a)) and len(b) == len(set(b))
            and a != b and set(a) == set(b))


def derive(rows):
    times = defaultdict(list)
    for row in rows:
        times[row["task_id"]].append(row["query_seconds"])
    query_medians = [statistics.median(v) for v in times.values()]
    request_times = [r["query_seconds"] for r in rows]
    order_count = sum(order_only(r) for r in rows)
    correct = sum(bool(r["correct"]) for r in rows)
    stage = {"prefill": [], "decode": []}
    for row in rows:
        calls = [row["answer_call"]] + ([row["selector"]] if row.get("selector") else [])
        stage["prefill"].append(sum(c.get("timings", {}).get("prompt_ms", 0) / 1000 for c in calls))
        stage["decode"].append(sum(c.get("timings", {}).get("predicted_ms", 0) / 1000 for c in calls))
    return {
        "correct": correct, "total": len(rows), "accuracy": correct / len(rows),
        "order_only_count": order_count, "order_tolerant_accuracy": (correct + order_count) / len(rows),
        "mean_context_tokens": mean(r["context_tokens"] for r in rows),
        "mean_input_tokens": mean(r["input_tokens"] for r in rows),
        "mean_output_tokens": mean(r["output_tokens"] for r in rows),
        "mean_query_seconds": mean(query_medians),
        "request_mean_seconds": mean(request_times),
        "request_p50_seconds": float(np.percentile(request_times, 50)),
        "request_p95_seconds": float(np.percentile(request_times, 95)),
        "mean_prefill_seconds": mean(stage["prefill"]),
        "mean_decode_seconds": mean(stage["decode"]),
        "mean_tokenize_seconds": mean(r.get("tokenize_seconds", 0) for r in rows),
        "mean_compaction_seconds": mean(r.get("compaction_seconds", 0) for r in rows),
        "raw_evidence_recall": mean(r["raw_evidence_recall"] for r in rows),
        "mean_tokenize_http_calls": mean(r.get("tokenize_http_calls", 0) for r in rows),
    }


class Evidence:
    def __init__(self, summary_path):
        self.path = Path(summary_path).resolve()
        self.root = self.path.parent
        self.base = self.root.parent
        self.summary = read(self.path)
        if self.summary.get("status") != "complete":
            raise ValueError("Only a complete final v2 summary can be rendered.")
        validation = self.summary.get("validation", {})
        if (validation.get("independent_integrity", {}).get("status") != "PASS"
                or not validation.get("all_payload_preserved")
                or not validation.get("paired_selection_equal")
                or validation.get("actual_rows") != validation.get("expected_rows")):
            raise ValueError("Final independent validation must pass before rendering.")
        self.audit = read(self.root / "audit.json")
        self.statistical_review = read(self.root / "statistical_review_v2.json")
        if (self.statistical_review["status"] != "PASS"
                or self.statistical_review["comparison_to_analysis"]["mismatches"]
                or self.statistical_review["comparison_to_analysis"]["summary_sha256"] != sha(self.path)):
            raise ValueError("Independent statistical review must match this final summary.")
        self.protocol = read(self.root / "protocol.json")
        self.environment = read(self.root / "environment.json")
        self.v1_environment = read(self.base / "environment.json")
        self.v1 = read(self.base / "analysis.json")
        self.v1_diagnostics = read(self.base / "output_diagnostics.json")
        self.holdout = read(self.root / "holdout/manifest.json")
        self.dev_rows = records(self.root / "results_dev.jsonl")
        self.data, self.tasks, self.metrics = {}, {}, {}
        self.by_split = self.summary["by_split"]
        self.costs = self.summary.get("costs", {})
        self.date = self.summary.get("report_date")
        if not self.date:
            self.date = datetime.fromisoformat(self.summary["created_at_utc"].replace("Z", "+00:00")).astimezone(
                ZoneInfo("Asia/Seoul")).date().isoformat()
        for rel, expected in self.summary.get("source_hashes", {}).items():
            if sha(self.root / rel) != expected:
                raise ValueError(f"Summary source hash mismatch: {rel}")
        for split, task_path, expected_repeats in [
            ("new", self.root / "holdout/eval_tasks.json", 3),
            ("old", self.base / "dataset/eval_tasks.json", 1),
        ]:
            tasks = read(task_path)
            self.tasks[split] = {t["id"]: t for t in tasks}
            if len(self.tasks[split]) != len(tasks):
                raise ValueError(f"Duplicate task identity in {split}")
            rows = records(self.root / f"results_{split}.jsonl")
            expected = {(t["id"], repeat, arm) for t in tasks
                        for repeat in range(expected_repeats) for arm in ARMS}
            keys = [(r["task_id"], r["repeat"], r["arm"]) for r in rows]
            if len(keys) != len(set(keys)) or set(keys) != expected:
                raise ValueError(f"Incomplete or duplicated {split} evaluation.")
            section = self.by_split[split]
            if section["rows"] != len(rows) or section["unique_questions"] != len(tasks):
                raise ValueError(f"Summary counts differ from {split} records.")
            self.data[split], self.metrics[split] = rows, {}
            for arm in ARMS:
                selected = [r for r in rows if r["arm"] == arm]
                raw = derive(selected)
                reported = section["metrics_by_arm"][arm]
                for field, observed in raw.items():
                    if field in reported and reported[field] is not None:
                        tolerance = 1e-7 * max(1.0, abs(observed))
                        if abs(reported[field] - observed) > tolerance:
                            raise ValueError(f"{split}/{arm}/{field}: summary does not match raw results.")
                self.metrics[split][arm] = {**raw, **{k: v for k, v in reported.items() if v is not None}}
            self._validate_pairs(split)
            for key, comp in section["comparisons"].items():
                first, second = key.split("-")
                observed = 100 * (self.metrics[split][first]["accuracy"] - self.metrics[split][second]["accuracy"])
                if abs(observed - comp["delta_pp"]) > 1e-8:
                    raise ValueError(f"Accuracy contrast mismatch: {split}/{key}")
        self._validate_v1()
        self.example_cases = self._examples()

    def _validate_v1(self):
        rows = records(self.base / "results_eval_main.jsonl")
        for arm in old.ARMS:
            sample = [r for r in rows if r["arm"] == arm]
            value = self.v1["metrics_by_arm"][arm]
            if len(sample) != value["total"] or sum(r["correct"] for r in sample) != value["correct"]:
                raise ValueError(f"Original v1 metric mismatch: {arm}")
        originals = self.audit.get("original_hashes_before_and_after", {})
        for rel in ("analysis.json", "results_eval_main.jsonl", "output_diagnostics.json",
                    "dataset/eval_tasks.json", "environment.json"):
            if rel in originals and sha(self.base / rel) != originals[rel]:
                raise ValueError(f"Audited v1 evidence changed: {rel}")

    def _validate_pairs(self, split):
        index = {(r["task_id"], r["repeat"], r["arm"]): r for r in self.data[split]}
        for key, record in index.items():
            task_id, repeat, arm = key
            task = self.tasks[split][task_id]
            if canon(record["expected"]) != canon(task["expected"]):
                raise ValueError(f"Saved gold differs from frozen task: {split}/{key}")
            if arm != "C":
                continue
            rh = index[(task_id, repeat, "RH")]
            compaction = record.get("compaction") or {}
            if (canon(record["chosen"]) != canon(rh["chosen"])
                    or record["selected_context_sha256"] != hashlib.sha256(rh["context"].encode()).hexdigest()
                    or not compaction.get("payload_preserved")
                    or compaction.get("selected_payload_sha256") != compaction.get("emitted_payload_sha256")):
                raise ValueError(f"Compaction pairing/payload verification failed: {split}/{key}")

    def comparison(self, split, key):
        return self.by_split[split]["comparisons"][key]

    def category(self, split, category, arm):
        return derive([r for r in self.data[split] if r["arm"] == arm and r["category"] == category])

    def _examples(self):
        explicit = self.summary.get("examples", [])
        if explicit:
            return explicit[:2]
        index = {(r["task_id"], r["repeat"], r["arm"]): r for r in self.data["new"]}
        pairs = []
        for key, record in index.items():
            if key[2] == "C":
                rh = index[(key[0], key[1], "RH")]
                pairs.append((int(record["correct"]) - int(rh["correct"]),
                              rh["context_tokens"] - record["context_tokens"], record))
        candidates = []
        for direction in (1, -1):
            group = [p for p in pairs if p[0] == direction]
            if group:
                candidates.append(max(group, key=lambda p: p[1])[2])
        for _, _, record in sorted(pairs, key=lambda p: -p[1]):
            if len(candidates) >= 2:
                break
            if all(record["task_id"] != r["task_id"] for r in candidates):
                candidates.append(record)
        return [{"split": "new", "task_id": r["task_id"], "repeat": r["repeat"],
                 "arms": ["RH", "C"]} for r in candidates]

    def recommendation(self):
        rh, compact = self.metrics["new"]["RH"], self.metrics["new"]["C"]
        quality_delta = 100 * (compact["accuracy"] - rh["accuracy"])
        time_delta = compact["mean_query_seconds"] - rh["mean_query_seconds"]
        if time_delta < 0 and quality_delta > 0:
            first = "새 질문에서 C는 RH보다 빠르고 주 정답률도 높았습니다."
        elif time_delta < 0 and quality_delta == 0:
            first = "새 질문에서 C는 RH보다 빨랐고 주 정답률은 같았습니다."
        elif time_delta < 0:
            first = "새 질문에서 C는 RH보다 빨랐지만 주 정답률은 낮았습니다."
        elif time_delta >= 0 and quality_delta > 0:
            first = "새 질문에서 C의 주 정답률은 높았지만 속도 개선은 없었습니다."
        elif time_delta >= 0 and quality_delta == 0:
            first = "새 질문에서 C의 주 정답률은 같고 속도 개선도 없었습니다."
        else:
            first = "새 질문에서 C는 RH 대비 정확도와 속도의 개선을 보이지 않았습니다."
        best = max(ARMS, key=lambda arm: (self.metrics["new"][arm]["accuracy"],
                                         -self.metrics["new"][arm]["mean_query_seconds"]))
        fastest = min(ARMS, key=lambda arm: self.metrics["new"][arm]["mean_query_seconds"])
        return (f"가장 빠른 방식은 {NAMES[fastest]}입니다. " + first +
                f" 관찰 정답률이 가장 높은 {best}는 후속 검증 후보입니다. 정확도 우위는 입증되지 않았습니다.")


class Folio(old.Page):
    def __init__(self, path, total, evidence, short=False):
        super().__init__(path, total, short)
        self.evidence = evidence
        self.c.setTitle("symbol_index와 RAPTOR - 신뢰 감사와 지연 개선 " + ("쉬운 설명" if short else "상세보고서"))

    def start(self, section, title, subtitle=None):
        if self.page:
            self.c.showPage()
        self.page += 1
        self.c.setFillColor(old.WHITE)
        self.c.rect(0, 0, old.W, H, fill=1, stroke=0)
        self.text(L, H - 34, "SECURECODE  /  AUDIT & OPTIMIZATION", 8.3, old.MUTED)
        self.text(R, H - 34, f"{self.page:02d} / {self.total:02d}", 8.3, old.MUTED, "right")
        self.c.setStrokeColor(old.RULE)
        self.c.line(L, H - 47, R, H - 47)
        self.text(L, H - 76, section, 9.2, old.TEAL)
        height = self.para(title, L, H - 91, CW, 23 if self.short else 21,
                           leading=30 if self.short else 28)
        y = H - 91 - height - 13
        if subtitle:
            y -= self.para(subtitle, L, y, CW, 10.1, old.MUTED, 15) + 14
        self.c.setStrokeColor(old.RULE)
        self.c.line(L, 38, R, 38)
        self.text(L, 24, f"{self.evidence.date}  |  기존 기록 감사 + 같은 코드의 추가 질문", 7.4, old.MUTED)
        self.text(R, 24, "원자료: evidence / revision_v2", 7.4, old.MUTED, "right")
        return y

    def paragraph(self, text, y, size=9.7, color=old.INK, gap=14):
        return y - self.para(text, L, y, CW, size, color) - gap

    def cards(self, values, top, height=105):
        width = (CW - 10 * (len(values) - 1)) / len(values)
        for index, (label, number, detail, color) in enumerate(values):
            x = L + index * (width + 10)
            self.box(x, top, width, height, PALE_PURPLE if color == PURPLE else old.PALE_TEAL if color == old.TEAL else old.PALE_BLUE)
            self.para(label, x + 12, top - 15, width - 24, 9.5, old.MUTED, 12)
            self.text(x + 12, top - 61, number, 26, color)
            self.para(detail, x + 12, top - 76, width - 24, 8.2, old.MUTED, 11)
        return top - height - 18

    def bars2(self, entries, top, maximum=None, suffix="%", height=36):
        """Entries are label, numeric value, color; numeric axis is shared."""
        maximum = maximum or max(v for _, v, _ in entries) or 1
        label_width, value_width = 164, 62
        plot_width = CW - label_width - value_width
        for label, value, color in entries:
            self.text(L, top - 16, label, 9.5)
            self.c.setFillColor(old.RULE)
            self.c.roundRect(L + label_width, top - 21, plot_width, 12, 3, fill=1, stroke=0)
            w = max(0, plot_width * value / maximum)
            if w:
                self.c.setFillColor(color)
                self.c.roundRect(L + label_width, top - 21, w, 12, min(3, w / 2), fill=1, stroke=0)
            self.text(R, top - 17, f"{value:.1f}{suffix}", 10, color, "right")
            top -= height
        return top - 11


def compaction_visual(p, y, short=False):
    half = (CW - 30) / 2
    labels = [("RH가 선택한 자료", old.PALE_TEAL),
              ("C가 정리한 자료", PALE_PURPLE)]
    for index, (title, color) in enumerate(labels):
        x = L + index * (half + 30)
        p.box(x, y, half, 159, color)
        p.text(x + 13, y - 22, title, 11.1, old.TEAL if index == 0 else PURPLE)
        link_label = "연결 정보" if short else "import"
        texts = ([f"긴 출처 표시 + {link_label} + 함수 A", f"긴 출처 표시 + {link_label} + 함수 A", "원문 함수 B + 요약 본문"]
                 if index == 0 else [f"짧은 출처 + {link_label} + 함수 A", "원문 함수 B", "같은 요약 본문"])
        for j, text in enumerate(texts):
            p.box(x + 12, y - 36 - j * 34, half - 24, 27, old.WHITE, radius=3)
            p.para(text, x + 20, y - 44 - j * 34, half - 40, 8.5, old.INK, 11)
    p.arrow(L + half + 4, y - 84, L + half + 26, y - 84)
    y -= 179
    sentence = ("겹친 코드와 반복된 출처 표시를 정리합니다. 원문·연결 정보·요약 본문은 그대로 두고, 빈자리에 다른 내용을 채우지 않습니다."
                if short else "겹친 코드와 반복된 출처 표시를 정리합니다. 고유 원문·import·요약 본문은 그대로 두고, 빈자리에 다른 내용을 채우지 않습니다.")
    return p.paragraph(sentence, y, 10.5 if short else 9.7, old.MUTED)


def confidence_text(comp):
    return f"정답률 차이 {signed(comp['delta_pp'])}, 탐색적 95% 구간 {interval(comp.get('ci95_pp'))}"


def speed_text(comp):
    value = comp.get("latency_reduction_pct")
    if value is None:
        return "속도 차이의 요약 통계가 없습니다."
    if value >= 0:
        text = f"C가 RH보다 {value:.1f}% 짧은 시간이 걸렸습니다."
    else:
        text = f"C가 RH보다 {abs(value):.1f}% 긴 시간이 걸렸습니다."
    ci = comp.get("latency_reduction_ci95_pct")
    return text + (f" 감소율의 탐색적 95% 구간은 {interval(ci, '%')}입니다." if ci else "")


def detailed(e, path):
    p = Folio(path, 12, e)
    m = e.metrics["new"]
    crh = e.comparison("new", "C-RH")
    y = p.start("01  /  갱신된 결론", "결과를 다시 검증하고,\n근거를 덜 반복하는 방식을 시험했습니다",
                "원래 실험의 신뢰 감사와 별도 v2 실험을 함께 기록한 개정판")
    y = p.note("판단", e.recommendation(), y, size=10.5)
    y = p.cards([(NAMES[a], percentage(m[a]["accuracy"]),
                  f"{m[a]['correct']}/{m[a]['total']}응답 · {m[a]['mean_query_seconds']:.2f}초", PALETTE[a])
                 for a in ARMS], y)
    y = p.note("속도 개선의 주 비교: C - RH", speed_text(crh), y, size=10.2)
    y = p.note("정확도도 함께 봅니다", confidence_text(crh) +
               ". 차이가 작거나 유의하지 않다는 것만으로 정확도가 동등하게 유지됐다고 증명한 것은 아닙니다.", y, old.PALE_ORANGE, size=9.7)
    y = p.section("같은 숫자처럼 섞으면 안 되는 세 묶음", y)
    y = p.table(["구분", "표본", "역할"], [
        ["v1", "원래 48문제 × 5방식 × 3회", "기존 결론·집계·근거의 감사"],
        ["v2 새 질문", "새 48문제 × A/RH/C × 3회", "주 품질·지연 비교"],
        ["v2 기존 질문", "기존 48문제 × A/RH/C × 1회", "별도 탐색적 회귀 점검"],
    ], y, [94, 198, CW - 292], font=9.0, row_h=32)
    p.paragraph("새 질문도 같은 6개 합성 프로젝트의 코드·알고리즘을 사용합니다. 프로젝트끼리 파일 골격과 보조 코드도 공유합니다. "
                "새 저장소로 일반화한 결과는 아닙니다. 표의 시간은 문제별 반복 중앙값을 평균한 값입니다.", y, 9.3, old.MUTED)

    y = p.start("02  /  기존 결과의 신뢰 감사", "계산은 재구성할 수 있었습니다.\n검증하지 못한 영역도 남아 있습니다.")
    checks = e.audit.get("summary", {})
    failed = len(e.audit.get("failed_checks", []))
    audit_text = (f"기록된 {checks.get('checks_total', len(e.audit.get('checks', [])))}개 점검 중 "
                  f"{checks.get('checks_passed', len(e.audit.get('checks', [])) - failed)}개를 통과했습니다. "
                  "점검 개수는 신뢰도 확률이나 전체 요약의 정확도를 뜻하지 않습니다.")
    y = p.note("감사 결과의 정확한 의미", audit_text, y, size=10.2)
    y = p.table(["영역", "확인한 사실", "남는 한계"], [
        ["원자료·집계", "파일 해시, 정답 수, 비교 통계를 재구성", "사후 해시가 사전 등록 시점을 증명하지 않음"],
        ["정답·참조", "실행 결과와 별도 AST 호출 관계 확인", "질문 해석 일부는 수동 판단"],
        ["토큰·검색", "별도 토큰 계산, 선택·적재 결과 대조", "실제 업무의 검색 적합성을 보장하지 않음"],
        ["요약", "코드→요약→상위 요약의 계보 확인", "모든 요약의 의미 정확성을 검증하지 않음"],
        ["시간·환경", "기록된 시간과 계산 방식 확인", "당시 실제 서버 설정·순수 콜드 지연은 증명 불가"],
    ], y, [70, 209, CW - 279], font=9.0, row_h=54)
    y = p.note("실제로 확인된 요약 문제", "한 요약은 원문에 없는 URL 인코딩 동작을 덧붙였습니다. 이는 요약이 틀릴 수 있음을 보여 주지만, 기존 채점 문제의 실패 원인이나 전체 요약 오류율로 계산하지 않았습니다.", y, old.PALE_ORANGE, size=9.6)
    y = p.paragraph("추가로 141개 중 5개 요약(평가 자료 4개)이 요청한 100단어를 넘었지만 256토큰 출력 상한은 지켰습니다. 기존 요약 캐시는 모델·프롬프트 변경을 감지하지 않으며, "
                    "전처리 비용 측정의 일부 경계도 기록이 부족했습니다. 현재의 연결 검증과 향후 운영상의 안전성은 구분합니다.", y, 9.4, old.MUTED)
    p.paragraph("따라서 기존 정확도는 내부적으로 재현 가능한 소규모 관찰로 유지합니다. 당시 실행 환경의 외부 인증이나 실제 저장소에서의 성능 인증으로 격상하지 않습니다.", y, 9.7, old.MUTED)

    y = p.start("03  /  원래 다섯 방식의 결과", "기존 점수는 보존하고,\n시간에 붙였던 의미를 더 정확히 고쳤습니다")
    original = e.v1["metrics_by_arm"]
    diag = e.v1_diagnostics["datasets"]["results_eval_main.jsonl"]["by_arm"]
    y = p.table(["방식", "주 정답률", "순서무시 보조", "평균 근거토큰", "당시 귀속시간"], [
        [f"{a} {old.LABELS[a]}", percentage(original[a]["accuracy"]),
         percentage(diag[a]["order_tolerant_accuracy"]),
         f"{original[a]['mean_context_tokens']:.0f}", f"{original[a]['mean_query_seconds']:.2f}초"]
        for a in old.ARMS
    ], y, [161, 76, 91, 90, CW - 418], font=8.8, row_h=38)
    y = p.note("정확도 해석", "원래 A는 48문제 중 8개, RH는 9개를 맞혔습니다. RH - A의 +2.1%p는 한 문제 차이입니다. "
               "R0 대비 RH의 주 점수는 낮았지만, 출력 순서만 허용한 사후 보조 점수는 같았습니다.", y, size=10.1)
    y = p.paragraph("A/B는 모델 선택기와 원문 확장을 사용하고, R0/RF/RH는 같은 원문 기반 단어 가중치·코사인 검색을 사용합니다. "
                    "RH - A에는 선택기·파일 범위·후보와 실제 근거량의 변화가 함께 섞입니다. 요약 추가의 효과는 RH - R0가 더 직접적인 대조입니다.", y, 9.4)
    y = p.note("시간 해석의 정정", "v1의 query_seconds는 방식별 비용을 재구성한 귀속시간입니다. A·B가 선택 결과를 공유하면서 "
               "각각 전체 선택비용을 부담했고, 토큰 수 계산 캐시는 실행 전체에서 공유했습니다. 독립적인 콜드 시작 실측 지연으로 읽으면 안 됩니다.", y, old.PALE_ORANGE, size=9.7)
    y = p.paragraph("기존 표의 95백분위수는 요청 144개의 p95가 아니라 문제별 3회 중앙값 48개의 p95였습니다. "
                    "v2에서는 요청 지연의 p50/p95와 문제별 중앙값의 평균을 구분합니다.", y, 9.8)
    p.paragraph("주 점수는 정답 내용과 요청한 목록 순서를 모두 지켜야 정답입니다. 순서무시 보조 점수는 같은 문자열 목록의 "
                "정렬 오류만 허용하며, 기존에는 사후 진단으로 추가됐습니다.", y, 9.4, old.MUTED)

    y = p.start("04  /  다시 측정한 실험", "같은 시기에 대조군을 함께 실행하고,\n새 질문과 기존 질문을 분리했습니다")
    y = p.flow(["원래 코드·요약 고정", "새 질문·규칙 고정", "A / RH / C\n순서 균형 실행", "품질·지연\n함께 채점"], y)
    y = p.table(["항목", "v2 설계"], [
        ["비교 조건", "A: 기존 선택·원문 확장 / RH: 원문+계층 요약 / C: RH의 선택 자료를 압축"],
        ["공통 조건", "같은 로컬 모델, 질문, 답변 지시, 1024토큰 근거 상한, 128토큰 출력 상한"],
        ["새 질문", "같은 6프로젝트의 새 입력·영어 질문 48개, 각각 3회"],
        ["기존 질문", "이미 검토한 48개, 각각 1회. 주 실험과 합산하지 않음"],
        ["캐시·선택기", "질의마다 토큰 수 캐시 초기화. A의 선택기는 매 질의 실제 호출"],
        ["실행 순서", "문제·반복 블록을 섞고 A/RH/C 여섯 순열을 균형 배치"],
        ["기록", "실제 요청, UTC 시각, 실행 세션, 환경 fingerprint, 자료·코드 해시"],
        ["C의 근거", "RH와 같은 선택 결과. 고유 본문을 보존하며 여유 공간을 다시 채우지 않음"],
    ], y, [103, CW - 103], font=9.1, row_h=39)
    y = p.note("새 질문은 새 프로젝트가 아닙니다", "기존 결과를 아는 상태에서 만든 추가 질문입니다. 코드·알고리즘·문제 계열은 이미 본 것입니다. "
               "특히 구조 문제는 기존 직접 호출에서 전이적 호출 관계로 바뀌므로, v1과 v2 점수 차이를 개선 효과로 계산하지 않습니다.", y, old.PALE_ORANGE, size=9.5)
    p.paragraph("질의 시간에는 토큰화·선택·적재·압축·모델 요청·호출 기록이 포함되고, 벡터 준비·워밍업·채점·결과 저장은 빠집니다. "
                "워밍업된 서버의 지연입니다. A도 공통 답변기·1024토큰 상한을 적용한 현재 알고리즘이며 실제 제품 전체 과정의 복제는 아닙니다.", y, 9.1, old.MUTED)

    y = p.start("05  /  무엇을 줄였는가", "내용을 새로 요약하지 않고,\n같은 내용이 반복되는 부분을 줄였습니다")
    y = compaction_visual(p, y)
    y = p.table(["보존", "변경"], [
        ["RH가 고른 자료와 순서", "중복 원문·파일별 import의 반복 횟수"],
        ["고유한 원문 소스·상수·import 본문", "긴 URI·줄 번호 등의 출처 표시"],
        ["함수·파일·프로젝트 요약의 본문", "짧은 출처 제목과 문맥 안의 배치"],
        ["근거를 고르는 검색 방법", "모델에 실제 전달되는 토큰 수"],
    ], y, [CW / 2, CW / 2], font=9.8, row_h=39)
    pairs = sum(r["arm"] == "C" for rows in e.data.values() for r in rows)
    y = p.note("본문 보존의 검증", f"C의 {pairs}개 기록 모두에서 RH와 선택 자료를 대조하고, 선택 전후 고유 본문 해시를 확인했습니다. "
               "문자열 보존은 정보 표시의 동일성이나 모델 정답의 보존까지 보장하지 않습니다.", y, size=9.7)
    p.paragraph("C는 추가 요약 모델을 호출하지 않습니다. 이미 만든 요약을 재사용합니다. 중복이나 위치 정보가 모델의 읽기에 영향을 줄 수 있으므로 "
                "속도만 비교하지 않고 정답 차이와 실제 답변 사례를 함께 평가합니다.", y, 9.6, old.MUTED)

    y = p.start("06  /  새 질문의 품질", "새 질문에서의 성적은\n정확한 값과 출력 순서로 채점했습니다")
    y = p.bars2([(NAMES[a], m[a]["accuracy"] * 100, PALETTE[a]) for a in ARMS], y, maximum=100)
    y = p.table(["유형", "고유 문제", "A", "RH", "C"], [
        [old.CATEGORY[cat], sum(t["category"] == cat for t in e.tasks["new"].values()),
         *[percentage(e.category("new", cat, a)["accuracy"]) for a in ARMS]]
        for cat in old.CATEGORY
    ], y, [139, 82, 96, 96, CW - 413], font=9.2, row_h=31)
    y = p.table(["비교", "차이와 탐색적 95% 구간", "문제별 승 / 패 / 동률"], [
        [key, f"{signed(e.comparison('new', key)['delta_pp'])}  {interval(e.comparison('new', key).get('ci95_pp'))}",
         " / ".join(str(e.comparison("new", key).get(k, "미산출")) for k in ("win", "loss", "tie"))]
        for key in ("C-RH", "C-A")
    ], y, [65, 280, CW - 345], font=9, row_h=36)
    y = p.table(["출력 순서 보조 진단", "A", "RH", "C"], [
        ["정렬만 틀린 응답", *[f"{m[a]['order_only_count']}회" for a in ARMS]],
        ["순서무시 보조 정답률", *[percentage(m[a]["order_tolerant_accuracy"]) for a in ARMS]],
    ], y, [208, 100, 100, CW - 408], font=9.0, row_h=29)
    p.paragraph("채점은 바깥 JSON 코드펜스 하나만 제거한 뒤 값·형식·목록 순서를 비교합니다. 3회 반복은 독립된 144문제가 아닙니다. "
                "유형별 6~12문제와 순서 보조 점수는 제한된 진단이며 주 점수나 정확도 동등성 검증을 대체하지 않습니다.", y, 9.0, old.MUTED)

    y = p.start("07  /  새 질문의 지연", "질의마다 실제 시간을 재고,\n응답 속도의 분포도 함께 확인했습니다")
    y = p.bars2([(NAMES[a], m[a]["mean_query_seconds"], PALETTE[a]) for a in ARMS], y,
                suffix="초", height=39)
    y = p.table(["방식", "문제별 중앙값\n평균", "요청 평균", "요청 p50", "요청 p95"], [
        [a, metric_text(m[a]["mean_query_seconds"], "초", 3),
         metric_text(m[a]["request_mean_seconds"], "초", 3),
         metric_text(m[a]["request_p50_seconds"], "초", 3),
         metric_text(m[a]["request_p95_seconds"], "초", 3)] for a in ARMS
    ], y, [46, 134, 110, 110, CW - 400], font=9.1, row_h=34)
    p95_reduction = 100 * (1 - m["C"]["request_p95_seconds"] / m["RH"]["request_p95_seconds"])
    y = p.note("주 속도 비교: 같은 v2 실행의 C - RH", speed_text(crh) +
               f" 시간 차이는 {metric_text(crh.get('latency_delta_seconds'), '초', 3)}, "
               f"구간은 {interval(crh.get('latency_ci95_seconds'), '초', 3)}입니다. "
               f"요청 p95는 {m['RH']['request_p95_seconds']:.3f}→{m['C']['request_p95_seconds']:.3f}초로 {p95_reduction:.1f}% 감소했습니다.", y, size=10)
    y = p.table(["방식", "평균 근거 토큰", "평균 입력 토큰", "평균 출력 토큰"], [
        [a, f"{m[a]['mean_context_tokens']:.0f}", f"{m[a]['mean_input_tokens']:.0f}", f"{m[a]['mean_output_tokens']:.0f}"]
        for a in ARMS
    ], y, [48, 150, 150, CW - 348], font=9.3, row_h=33)
    both_n = crh.get("both_success_n", 0)
    both = (f"두 방식이 모두 항상 정답인 {both_n}문제의 C/RH 시간 비는 "
            f"{metric_text(crh.get('both_success_latency_ratio'), '배', 3)}입니다."
            if both_n else "두 방식이 모두 항상 정답인 문제의 속도 비교는 산출하지 못했습니다.")
    p.paragraph("속도에는 오답도 포함됩니다. " + both + " 평균 입력은 A의 선택기와 답변을 합친 값이며, 근거 토큰은 답변에 전달한 코드·요약입니다.", y, 9.5, old.MUTED)

    y = p.start("08  /  병목과 비용", "모델이 입력을 읽는 시간과\n그 밖의 준비 비용을 구분합니다")
    y = p.section("새 질문의 평균 물리적 요청시간 분해", y)
    max_time = max(m[a]["request_mean_seconds"] for a in ARMS)
    label_w, plot_w = 39, CW - 100
    stage_colors = [old.TEAL, PURPLE, colors.HexColor("#B8C7CD")]
    for arm in ARMS:
        duration = m[arm]["request_mean_seconds"]
        prefill, decode = m[arm]["mean_prefill_seconds"], m[arm]["mean_decode_seconds"]
        remainder = duration - prefill - decode
        if remainder < -0.02:
            raise ValueError(f"Server phase sums exceed physical request time for {arm}")
        x = L + label_w
        p.text(L, y - 16, arm, 11)
        for value, color in zip((prefill, decode, max(0, remainder)), stage_colors):
            width = plot_w * value / max_time
            p.c.setFillColor(color)
            p.c.rect(x, y - 22, width, 15, fill=1, stroke=0)
            x += width
        p.text(R, y - 18, f"{duration:.2f}초", 10, old.INK, "right")
        y -= 38
    y = p.paragraph("청록: 입력 처리(prefill)   보라: 답변 생성(decode)   회색: 나머지 경과시간\n"
                    "합계는 요청 144회의 평균입니다. 주 속도 지표인 문제별 중앙값의 평균과 다릅니다.", y, 8.9, old.MUTED)
    y = p.table(["방식", "입력 처리", "답변 생성", "토큰화*", "압축 단계*"], [
        [a, metric_text(m[a]["mean_prefill_seconds"], "초", 3),
         metric_text(m[a]["mean_decode_seconds"], "초", 3),
         metric_text(m[a]["mean_tokenize_seconds"], "초", 3),
         metric_text(m[a]["mean_compaction_seconds"], "초", 3)] for a in ARMS
    ], y, [46, 116, 116, 116, CW - 394], font=9.0, row_h=30)
    y = p.note("시간을 중복해서 더하지 않습니다", "토큰화는 선택·적재·모델 요청 시간 안에 포함되며, C의 압축 단계에도 토큰화가 포함됩니다. "
               "별표 항목은 위 막대에 추가로 더하는 시간이 아닙니다. A의 입력 처리·생성에는 선택기와 답변 호출을 모두 포함했습니다.", y, old.PALE_ORANGE, size=9.5)
    original_build = e.costs.get("original_summary_build_seconds", e.v1["build"]["seconds"])
    vector_build = e.costs.get("mean_vector_build_seconds")
    y = p.table(["준비 비용", "해석"], [
        ["새 요약 모델 호출", f"{e.costs.get('new_summary_calls', 0)}회. 기존 요약 그대로 재사용"],
        ["기존 요약 준비 기록", f"{original_build / 60:.1f}분 / 6프로젝트. v1 경과시간이며 콜드 실행 인증값 아님"],
        ["문서 벡터 준비", f"프로젝트당 평균 {metric_text(vector_build, '초', 4)}. RH와 C가 공유하는 단계"],
    ], y, [140, CW - 140], font=9.2, row_h=32)
    historical_share = (100 * e.costs["v1_rh_mean_prefill_seconds"] / e.costs["v1_rh_request_mean_seconds"])
    p.paragraph(f"v1 RH의 저장된 입력 처리 시간은 당시 요청 평균의 {historical_share:.1f}%였습니다. 입력량을 줄이는 개선의 단서이며 "
                "당시 실제 런타임을 인증한 비율은 아닙니다. 미세한 차이로 계산한 v1 손익분기점도 회수 시점으로 확정하지 않습니다. "
                "콜드 시작·전력·요약 갱신·동시 사용자 비용은 별도입니다.", y, 9.1, old.MUTED)

    y = p.start("09  /  기존 질문의 별도 점검", "이미 본 48문제는\n회귀 점검으로 따로 남겼습니다")
    regression = e.metrics["old"]
    y = p.cards([(NAMES[a], percentage(regression[a]["accuracy"]),
                  f"{regression[a]['correct']}/{regression[a]['total']}응답 · 1회 실행", PALETTE[a])
                 for a in ARMS], y)
    y = p.table(["비교", "주 정답률 차이", "문제별 승 / 패 / 동률", "질의시간 차이"], [
        [key, signed(e.comparison("old", key)["delta_pp"]),
         " / ".join(str(e.comparison("old", key).get(k, "미산출")) for k in ("win", "loss", "tie")),
         metric_text(e.comparison("old", key).get("latency_delta_seconds"), "초", 3)]
        for key in ("C-RH", "C-A", "RH-A")
    ], y, [73, 111, 190, CW - 374], font=9.0, row_h=38)
    y = p.table(["방식", "순서무시 보조", "평균 실제 요청시간", "평균 근거 토큰"], [
        [a, percentage(regression[a]["order_tolerant_accuracy"]),
         metric_text(regression[a]["request_mean_seconds"], "초", 3),
         f"{regression[a]['mean_context_tokens']:.0f}"] for a in ARMS
    ], y, [50, 140, 190, CW - 380], font=9.2, row_h=35)
    y = p.paragraph(f"목록 순서를 허용한 보조 정답률은 RH {percentage(regression['RH']['order_tolerant_accuracy'])}, "
                    f"C {percentage(regression['C']['order_tolerant_accuracy'])}입니다. 주 점수 차이만으로 의미 이해의 개선이 증명된 것은 아닙니다.", y, 9.4)
    y = p.note("합치지 않는 이유", "기존 질문은 이미 결과를 검토한 자료입니다. 새 질문 48개와 합쳐 96개의 독립 표본처럼 주장하지 않습니다. "
               "새 질문의 구조 문제도 전이적 호출로 달라졌으므로 점수의 단순 전후 차이는 동일 난이도의 개선량이 아닙니다.", y, old.PALE_ORANGE, size=9.8)
    p.paragraph("같은 시기의 A/RH/C 비교를 유지한 회귀 점검입니다. 최초 v1 실행과 이번 실행 사이에는 시간 정책과 환경 기록 방식이 달라졌으므로 "
                "과거 실행과의 속도비를 압축 효과로 해석하지 않습니다.", y, 9.6, old.MUTED)

    y = p.start("10  /  같은 질문의 실제 답", "본문이 보존되어도\n모델의 답은 달라질 수 있습니다")
    for number, example in enumerate(e.example_cases, 1):
        split, tid = example["split"], example["task_id"]
        repeat = example.get("repeat", example.get("repeat_zero_based", 0))
        supplied_arms = example.get("arms", ["RH", "C"])
        arms = [arm for arm in ARMS if arm in supplied_arms]
        task = e.tasks[split][tid]
        selected = {a: next(r for r in e.data[split] if r["task_id"] == tid and r["repeat"] == repeat and r["arm"] == a)
                    for a in arms}
        p.box(L, y, CW, 231, old.BG)
        p.text(L + 13, y - 22, f"사례 {number} · {'새 질문' if split == 'new' else '기존 질문'} · {old.CATEGORY[task['category']]}", 11, old.TEAL)
        p.text(L + 13, y - 37, f"{tid} / 반복 {repeat + 1}", 7.8, old.MUTED)
        description = example.get("question_ko") or example.get("description_ko") or task["question"]
        dh = p.para(description, L + 13, y - 49, CW - 26, 9.5, old.INK, 13)
        answer_lines = [f"정답: {old.short_json(task['expected'], 160)}"]
        for arm, row in selected.items():
            answer_lines.append(f"{arm}: {old.short_json(row['parsed_answer'], 160)}  ({'정답' if row['correct'] else '오답'})")
        ah = p.para("\n".join(answer_lines), L + 13, y - 58 - dh, CW - 26, 8.8, old.INK, 13)
        counts = " · ".join(f"{a} 근거 {r['context_tokens']}토큰" for a, r in selected.items())
        obs = counts + "\n" + (example.get("observation_ko") or "같은 질문·반복의 실제 결과입니다.")
        caution = example.get("caution_ko") or "선택된 사례는 대표적인 성공률이 아닙니다. 특정 오답의 원인을 단일 요소로 확정하지 않습니다."
        p.para(obs + "\n" + caution, L + 13, y - 68 - dh - ah, CW - 26, 9.0, old.MUTED, 13)
        y -= 244
    y = p.note("검증 범위", "표시한 답은 원자료의 task ID·반복·방식으로 찾은 실제 출력입니다. C와 RH의 선택 문맥 및 본문 해시도 대조했습니다. "
               "본문 보존과 정답 보존을 같은 의미로 사용하지 않습니다.", y, size=9.7)
    p.paragraph("사례는 첫 반복에서 C의 개선·악화 등 정오 유형별 task ID 사전순으로 고른 사후 사례입니다. "
                "전체 빈도를 대표하지 않으며, 추가 개입 없이는 특정 원인의 인과 효과로 단정하지 않습니다.", y, 9.1, old.MUTED)

    y = p.start("11  /  판단의 범위", "작은 파일럿의 개선 후보와\n실제 도입의 증거는 구분합니다")
    y = p.note("이번 결과가 제안하는 행동", e.recommendation(), y, size=10.4)
    y = p.table(["현재 확인한 것", "아직 확인하지 않은 것"], [
        ["기존 기록·정답·토큰·집계의 내부 일치", "최초 실행 당시의 모든 서버 설정"],
        ["같은 6개 코드의 새 입력·질문", "새 저장소·실제 개발 업무에서의 일반화"],
        ["고유 원문·요약 본문 보존", "요약의 완전한 사실 정확성"],
        ["동일 시기 A/RH/C의 물리적 질의 시간", "다중 사용자 처리량·장기 운영비"],
        ["엄격 점수 및 목록 순서 보조 점수", "버그 수정 성공률·개발자 작업 시간"],
    ], y, [CW / 2, CW / 2], font=9.2, row_h=42)
    y = p.note("통계적 주의", "같은 프로젝트의 문제는 서로 연관됩니다. 구간은 프로젝트 6개를 묶어 계산한 탐색적 결과이며, "
               "공통 파일 골격·보조 코드 때문에 6개 군집도 완전히 독립적이지 않습니다. 반복이나 새 질문이 프로젝트 수를 늘려 주지 않으며 우위를 확정하지 않습니다.", y, old.PALE_ORANGE, size=9.7)
    y = p.paragraph("정확도 비열등성·동등성을 미리 정한 허용 오차와 충분한 표본으로 검증한 실험이 아닙니다. "
                    "같은 평균 정답률이나 0을 포함하는 신뢰구간만으로 “성능 손실 없음”을 주장하지 않습니다.", y, 9.7)
    y = p.paragraph("후속 실험은 실제 저장소를 늘리고, 기존에 유망했던 파일 간 원문 확장 B도 같은 새 조건에서 함께 비교해야 합니다. "
                    "이번 v2에 없는 B/R0/RF를 새 질문의 승자로 선정하지 않습니다.", y, 9.6, old.MUTED)
    dev_correct = sum(row["correct"] for row in e.dev_rows)
    dev_questions = len({row["task_id"] for row in e.dev_rows})
    p.paragraph(f"개발용 {dev_questions}문제 × 3방식의 {len(e.dev_rows)}응답 중 정답은 {dev_correct}개였습니다. "
                "연결·기록·실행 확인용으로 사용했고 이 결과에 맞춘 정확도 조정은 하지 않았습니다. 현재 검색·답변 조합의 낮은 절대 성능도 함께 드러납니다.", y, 9.1, old.MUTED)

    y = p.start("12  /  근거와 재현", "원래 기록을 보존한 채\n추가 실험을 별도 경로에 기록했습니다")
    hardware = e.v1_environment.get("machdep.cpu.brand_string", "장비 기록 참조")
    ram_gib = int(e.v1_environment["hw.memsize"]) / 2**30
    build_info = e.environment["fingerprint"]["server_properties"]["build_info"]
    y = p.paragraph(f"장비: {hardware}, 메모리 {ram_gib:.0f}GiB. 모델: Qwen2.5-Coder-7B-Instruct Q5_K_M. "
                    f"v2 서버: llama.cpp {build_info}, 문맥 8192, temperature 0, seed 1, 단일 슬롯. "
                    "모델·서버 파일 해시와 실제 요청 설정은 환경 기록에 남겼습니다.", y, 9.1)
    y = p.table(["근거 파일 / 위치", "역할"], [
        ["evidence/analysis.json", "원래 다섯 방식의 집계"],
        ["evidence/results_eval_main.jsonl", "원래 720개 채점 기록"],
        ["evidence/revision_v2/audit.json", "독립 재구성 감사와 남은 한계"],
        ["evidence/revision_v2/holdout/", "새 질문·검증된 정답·소스 해시"],
        ["evidence/revision_v2/protocol.json", "새 실험의 동결 규칙"],
        ["evidence/revision_v2/environment.json", "서버·모델·실행 환경 식별"],
        ["evidence/revision_v2/results_new.jsonl", "새 질문의 A/RH/C 결과"],
        ["evidence/revision_v2/results_old.jsonl", "기존 질문의 별도 회귀 결과"],
        ["evidence/revision_v2/summary_v2.json", "보고서의 최종 집계와 입력 해시"],
        ["2nd/experiments/symbol_raptor/ (저장소 기준)", "감사·실행·분석·보고서 코드"],
    ], y, [273, CW - 273], font=8.6, row_h=29)
    integrity_checks = e.summary["validation"]["independent_integrity"]["checks"]
    verified_values = e.statistical_review["comparison_to_analysis"]["checked_scalar_values"]
    y = p.note("이 보고서의 생성 전 검사", "행·정답·집계를 원자료와 재대조하고 C/RH 본문·v1 해시를 확인합니다. "
               f"integrity_v2.json의 {sum(c['passed'] for c in integrity_checks)}/{len(integrity_checks)}개 점검, "
               f"statistical_review_v2.json의 {verified_values}개 집계값 비교가 모두 일치했습니다. "
               "누락되거나 맞지 않는 최종 자료로는 생성하지 않습니다.", y, size=9.2)
    y = p.paragraph("원래 PDF와 핵심 원자료는 보관본으로 남겼습니다. 개정 PDF의 v1 점수와 v2 점수는 별도의 표본으로 표시하며, "
                    "현재 경로의 PDF만 갱신합니다.", y, 9.5)
    y = p.section("개념의 출처와 적용 범위", y)
    p.paragraph("Sarthi et al., RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval (2024).\n"
                "https://arxiv.org/abs/2401.18059\n"
                "여기서는 원논문의 임베딩·차원 축소·확률적 군집화 대신 AST·파일 계층과 TF-IDF를 사용합니다. "
                "이 코드용 변형의 결과를 RAPTOR 일반의 우열로 확대하지 않습니다.", y, 8.9, old.MUTED)
    p.end()


def newcomer(e, path):
    p = Folio(path, 4, e, short=True)
    m = e.metrics["new"]
    comp = e.comparison("new", "C-RH")
    y = p.start("01  /  어떤 실험인가", "코드를 찾는 방법을 비교하고,\n같은 자료를 더 짧게 전달해 봤습니다",
                "모델이 질문에 답할 때 어떤 코드와 설명을 근거로 함께 줄지 비교하는 실험입니다.")
    boxes = [
        ("A · symbol_index", "주소록처럼 이름과 위치를\n찾아 관련 코드를 읽습니다.", old.PALE_BLUE),
        ("RH · RAPTOR 변형", "여러 층의 노트처럼\n함수·파일·전체 요약과\n원문을 함께 찾습니다.", old.PALE_TEAL),
        ("C · 겹친 부분 정리", "RH가 고른 자료에서\n중복과 긴 표시를 줄입니다.", PALE_PURPLE),
    ]
    width = (CW - 20) / 3
    for index, (title, text, fill) in enumerate(boxes):
        x = L + index * (width + 10)
        p.box(x, y, width, 116, fill)
        p.para(title, x + 13, y - 18, width - 26, 11.2, old.INK, 16)
        p.para(text, x + 13, y - 53, width - 26, 10.0, old.MUTED, 15)
    y -= 139
    y = p.section("이번에 추가한 48문제의 성적표", y)
    y = p.cards([(NAMES[a], percentage(m[a]["accuracy"]),
                  "내용과 요청한 순서 모두 정확", PALETTE[a]) for a in ARMS], y)
    y = p.note("이번에 관찰한 결과", e.recommendation(), y, size=11)
    y = p.note("숫자의 범위", "개인 컴퓨터에서 실행한 모델 한 종류가 실험용으로 만든 작은 프로그램 6개의 새 영어 질문 48개를 세 번씩 풀었습니다. "
               "이미 본 코드이며 일부 구조와 코드도 공유합니다. 실제 업무나 버그 수정 능력을 검증한 결과는 아닙니다.", y, old.PALE_ORANGE, size=10.5)
    p.paragraph("코드는 작업을 수행하는 조리법, 함수는 그중 한 작업의 조리법이라고 생각하면 됩니다. "
                "보고서의 정답률은 그 조리법이 정확히 무엇을 하는지 맞힌 비율입니다.", y, 10.3, old.MUTED)

    y = p.start("02  /  무엇을 다시 확인했나", "기록과 계산은 확인했습니다.\n모든 요약이 맞다는 뜻은 아닙니다.")
    y = p.flow(["실제 코드와 정답", "저장된 질문·답변", "입력 길이·선택 자료", "표의 점수"], y,
               "원자료를 따라 결과를 다시 계산하는 감사를 진행했습니다.", old.PALE_TEAL)
    y = p.note("확인한 것", "기존 정답 수와 점수 계산, 선택된 자료, 요약의 출처 연결을 원기록과 대조했습니다. "
               "원래 기록을 고쳐 더 좋은 결과로 만들지 않았습니다.", y, size=11)
    y = p.note("확인하지 못한 것", "원래 실행 당시의 모든 서버 설정은 기록이 부족했습니다. "
               "또한 출처가 연결된 요약도 사실을 빠뜨리거나 덧붙일 수 있습니다.", y, old.PALE_ORANGE, size=11)
    original = e.v1["metrics_by_arm"]
    y = p.section("원래 비교는 이 정도 차이였습니다", y)
    y = p.bars2([("현재 방식 A", original["A"]["accuracy"] * 100, old.BLUE),
                 ("계층 요약 RH", original["RH"]["accuracy"] * 100, old.TEAL)], y, maximum=100, height=42)
    y = p.paragraph("동일한 48개 문제에서 A는 8개, RH는 9개를 맞혔습니다. 한 문제 차이로 일반적인 우위를 확정할 수 없습니다. "
                    "이번 새 질문 결과와도 직접 합산하지 않습니다.", y, 11.1)
    p.paragraph("신뢰 감사는 “기록에 근거가 있는지”를 확인합니다. 실제 업무에서 충분히 좋은 성능인지는 별도로 확인해야 합니다.", y, 10.6, old.MUTED)

    y = p.start("03  /  속도는 어떻게 달라졌나", "같은 본문을 남기고\n겹친 부분을 정리했습니다")
    y = compaction_visual(p, y, short=True)
    y = p.section("새 질문의 실측 시간", y)
    y = p.bars2([("A · 현재 방식", m["A"]["mean_query_seconds"], old.BLUE),
                 ("RH · 정리 전", m["RH"]["mean_query_seconds"], old.TEAL),
                 ("C · 정리 후", m["C"]["mean_query_seconds"], PURPLE)], y, suffix="초", height=34)
    c_vs_a = e.comparison("new", "C-A")["latency_reduction_pct"]
    current_comparison = (f"C는 A보다 {abs(c_vs_a):.1f}% {'느렸습니다' if c_vs_a < 0 else '빨랐습니다'}.")
    y = p.note("속도와 정답을 함께 봅니다", speed_text(comp) + "\n" +
               current_comparison + f" C - RH 주 정답률 차이는 {signed(comp['delta_pp'])}이며 우위는 입증되지 않았습니다.", y, size=10.4)
    y = p.note("왜 더 짧게 보내는가", "모델은 답하기 전에 입력 자료를 읽습니다. 반복된 코드와 긴 표시에 쓰는 토큰(모델이 글을 읽는 작은 단위)을 "
               "줄여 봤습니다. 다른 자료로 바꾸거나 빈자리를 새 자료로 채우지는 않았습니다.", y, old.PALE_BLUE, size=10.5)
    p.paragraph("워밍업된 서버에서 같은 시기에 RH와 C를 번갈아 비교했습니다. 처음 켜는 비용은 빠져 있으며, 빠르게 틀린 답도 평균에는 포함됩니다.", y, 10.1, old.MUTED)

    y = p.start("04  /  어떻게 판단할까", "가장 빠른 답보다\n쓸 수 있는 답을 먼저 확인합니다")
    y = p.note("후속 검증의 후보", e.recommendation(), y, size=11.2)
    y = p.cards([
        ("RH 주 정답률", percentage(m["RH"]["accuracy"]), "새 48문제 · 반복 3회", old.TEAL),
        ("C 주 정답률", percentage(m["C"]["accuracy"]), "같은 질문·선택 자료", PURPLE),
    ], y)
    items = [
        ("01", "실제 코드에서도 확인", "같은 실험용 프로그램을 재사용했습니다. 실제 업무의 새로운 코드에서도 효과를 다시 봐야 합니다."),
        ("02", "정확도 손실 여부 확인", "평균 점수가 같거나 차이가 작다고 해서 성능이 동등하다고 증명한 것은 아닙니다."),
        ("03", "준비 비용도 계산", "기존 요약을 재사용했습니다. 처음 만들거나 코드 변경 뒤 고치는 비용은 별도로 듭니다."),
    ]
    for number, title, text in items:
        p.text(L, y - 19, number, 19, PURPLE)
        p.text(L + 39, y - 16, title, 11.3)
        p.para(text, L + 39, y - 27, CW - 39, 10.5, old.MUTED, 15)
        y -= 81
    y = p.note("짧게 기억하면", "기존 숫자는 재구성할 수 있었고, 시간 해석에는 보완이 필요했습니다. "
               "추가 실험은 본문을 보존하는 압축의 후보 성능을 보여 줍니다. 실제 도입의 증명은 아닙니다.", y, old.PALE_ORANGE, size=10.4)
    p.paragraph("상세판에는 전체 결과, 시간 분해, 실제 답변 사례와 재현 경로가 있습니다. 원자료는 같은 폴더의 evidence에 보존했습니다.", y, 9.8, old.MUTED)
    p.end()


def build(summary_path, output_dir=None):
    evidence = Evidence(summary_path)
    if old.FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(old.FONT, old.FONT_PATH))
    destination = Path(output_dir).resolve() if output_dir else evidence.base.parent
    destination.mkdir(parents=True, exist_ok=True)
    paths = [
        destination / "01_symbol_index와_RAPTOR_정량평가_상세보고서.pdf",
        destination / "02_그림으로_이해하는_symbol_index와_RAPTOR_비교.pdf",
    ]
    detailed(evidence, paths[0])
    newcomer(evidence, paths[1])
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_path", nargs="?", type=Path, default=DEFAULT)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    for output in build(args.summary_path, args.output_dir):
        print(output)
