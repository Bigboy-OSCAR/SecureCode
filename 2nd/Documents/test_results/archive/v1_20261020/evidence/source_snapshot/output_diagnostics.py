"""Post-hoc output diagnostics; reads frozen evaluation rows without regrading them.

The primary strict score remains unchanged. The supplementary score only forgives
ordering of duplicate-free lists containing exactly the same strings. Numeric,
boolean, string, schema, JSON, selector, execution, and generation-limit errors
remain failures. Different context budgets are summarized separately by file.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


DEFAULT_OUT = (
    Path(__file__).resolve().parent.parents[2]
    / "2nd/Documents/test_results/evidence"
)
FAILURE_CATEGORIES = (
    "json", "schema", "abstain", "limit", "wrong", "selector", "execution", "other"
)


def order_only_failure(row):
    """Require a valid, normally completed answer, not a failed prerequisite."""
    if row.get("correct") or row.get("failure") != "wrong_answer":
        return False
    if not row.get("answer_call", {}).get("ok"):
        return False
    selector = row.get("selector")
    if selector is not None and not selector.get("ok"):
        return False
    actual, expected = row.get("parsed_answer"), row.get("expected")
    if not isinstance(actual, list) or not isinstance(expected, list):
        return False
    if not all(isinstance(item, str) for item in actual + expected):
        return False
    if len(actual) != len(set(actual)) or len(expected) != len(set(expected)):
        return False
    return actual != expected and set(actual) == set(expected)


def hit_limit(call):
    return bool(call) and (
        bool(call.get("truncated"))
        or bool(call.get("stopped_limit"))
        or call.get("stop_type") == "limit"
    )


def failure_category(row):
    if row.get("correct"):
        return None
    failure = row.get("failure")
    if failure == "selector_invalid":
        return "limit" if hit_limit(row.get("selector")) else "selector"
    if failure == "execution_or_limit":
        return "limit" if hit_limit(row.get("answer_call")) else "execution"
    return {
        "invalid_json": "json",
        "invalid_schema": "schema",
        "abstained": "abstain",
        "wrong_answer": "wrong",
    }.get(failure, "other")


def read_snapshot(path):
    """Capture once; tolerate only an incomplete last row from an active writer."""
    raw_bytes = path.read_bytes()
    lines = raw_bytes.decode("utf-8").splitlines()
    rows, ignored = [], 0
    identities = set()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                ignored += 1
                continue
            raise
        identity = (row["task_id"], row["arm"], row["repeat"])
        if identity in identities:
            raise ValueError(f"Duplicate task/arm/repeat in {path.name}: {identity}")
        identities.add(identity)
        rows.append(row)
    return rows, {
        "snapshot_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "snapshot_bytes": len(raw_bytes),
        "ignored_incomplete_final_rows": ignored,
    }


def summarize_rows(rows):
    correct = sum(bool(row["correct"]) for row in rows)
    order_only = sum(order_only_failure(row) for row in rows)
    failures = Counter(failure_category(row) for row in rows if not row["correct"])
    raw_failures = Counter(str(row.get("failure")) for row in rows if not row["correct"])
    return {
        "rows": len(rows),
        "distinct_tasks": len({row["task_id"] for row in rows}),
        "strict_correct": correct,
        "strict_accuracy": correct / len(rows) if rows else None,
        "order_only_failure_count": order_only,
        "order_tolerant_correct": correct + order_only,
        "order_tolerant_accuracy": (correct + order_only) / len(rows) if rows else None,
        "failure_counts_strict": {key: failures.get(key, 0) for key in FAILURE_CATEGORIES},
        "raw_failure_labels_strict": dict(sorted(raw_failures.items())),
        "note": "Order-tolerant values are a post-hoc supplementary diagnostic, not the primary score.",
    }


def self_check():
    base = {
        "correct": False, "failure": "wrong_answer", "answer_call": {"ok": True},
        "parsed_answer": ["b", "a"], "expected": ["a", "b"], "selector": None,
    }
    assert order_only_failure(base)
    assert not order_only_failure({**base, "parsed_answer": ["a", "b"]})
    assert not order_only_failure({**base, "parsed_answer": ["b", "a", "a"]})
    assert not order_only_failure({**base, "expected": ["a", "b", "b"]})
    assert not order_only_failure({**base, "parsed_answer": ["B", "a"]})
    assert not order_only_failure({**base, "parsed_answer": ["b ", "a"]})
    assert not order_only_failure({**base, "parsed_answer": [2, 1], "expected": [1, 2]})
    assert not order_only_failure({**base, "parsed_answer": [True, 1], "expected": [1, True]})
    assert not order_only_failure({**base, "parsed_answer": {"a": 1}})
    assert not order_only_failure({**base, "answer_call": {"ok": False}})
    assert not order_only_failure({**base, "selector": {"ok": False}})
    for failure in ("invalid_json", "invalid_schema", "selector_invalid", "execution_or_limit", "abstained"):
        assert not order_only_failure({**base, "failure": failure})
    assert failure_category({**base, "failure": "execution_or_limit",
                             "answer_call": {"ok": False, "stop_type": "limit"}}) == "limit"
    assert failure_category({**base, "failure": "selector_invalid",
                             "selector": {"ok": False, "stopped_limit": True}}) == "limit"
    assert failure_category({**base, "failure": "execution_or_limit",
                             "answer_call": {"ok": False, "error": "timeout"}}) == "execution"


def generate(out):
    self_check()
    datasets = {}
    all_rows, order_rows = [], []
    for path in sorted(out.glob("results_eval_*.jsonl")):
        rows, snapshot = read_snapshot(path)
        arms = sorted({row["arm"] for row in rows})
        datasets[path.name] = {
            **snapshot,
            "budgets": sorted({row["budget"] for row in rows}),
            "summary": summarize_rows(rows),
            "by_arm": {
                arm: summarize_rows([row for row in rows if row["arm"] == arm])
                for arm in arms
            },
        }
        for row in rows:
            if order_only_failure(row):
                order_rows.append({
                    "result_file": path.name,
                    "task_id": row["task_id"],
                    "category": row["category"],
                    "arm": row["arm"],
                    "repeat_zero_based": row["repeat"],
                    "budget": row["budget"],
                    "actual": row["parsed_answer"],
                    "expected": row["expected"],
                    "answer_call_id": row["answer_call"].get("call_id"),
                })
        all_rows.extend(rows)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "snapshot_complete" if datasets else "no_evaluation_rows_found",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Only results_eval_*.jsonl; excludes development and calibration records.",
        "primary_scoring_modified": False,
        "supplementary_rule": (
            "Only normally completed, schema-valid wrong answers whose actual and expected values "
            "are duplicate-free lists of exactly the same case-sensitive strings are credited "
            "after ignoring order. All other strict failures are retained."
        ),
        "interpretation": (
            "The strict primary score measures answer correctness plus compliance with requested "
            "output order. The order-tolerant score is an explicitly post-hoc diagnostic of "
            "whether ordering alone explains the failure; it is not a replacement experiment."
        ),
        "datasets": datasets,
        "order_only_failures": order_rows,
        "totals_for_audit_only": {
            "rows": len(all_rows),
            "order_only_failure_count": len(order_rows),
            "warning": "Files may use different budgets/repetition counts. Do not use this pooled total to rank arms.",
        },
        "limitations": [
            "A snapshot can be incomplete while evaluation is running; rerun after completion.",
            "Repeated rows are repeated measurements, not independent questions.",
            "No recomputation, model calls, prompt edits, or primary-score changes are performed.",
        ],
    }
    output = out / "output_diagnostics.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    report = generate(args.out.resolve())
    print(json.dumps({
        "status": report["status"],
        **report["totals_for_audit_only"],
        "files": {
            name: {
                "rows": dataset["summary"]["rows"],
                "order_only_failures": dataset["summary"]["order_only_failure_count"],
            }
            for name, dataset in report["datasets"].items()
        },
    }, ensure_ascii=False, indent=2))
