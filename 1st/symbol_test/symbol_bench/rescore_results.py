"""Regrade saved model outputs without rerunning or changing their timing data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run_benchmark import _answer_is_correct, _read_json


def rescore_row(row: dict, tasks: dict[str, dict]) -> dict:
    task = tasks.get(row["task_id"], row)
    calls = row.get("calls", [])
    execution_ok = bool(calls) and all(call.get("returncode") == 0 for call in calls)
    answer_correct = bool(calls) and _answer_is_correct(calls[-1], task)
    correct = execution_ok and answer_correct
    if row["mode"] == "symbol_select":
        correct = correct and row.get("selection_correct") is True
    return {
        **row,
        "previous_correct": row["correct"],
        "correct": correct,
        "execution_ok": execution_ok,
        "grading_task": task if row["task_id"] in tasks else None,
        "rescore_policy": "successful_execution_and_exact_cache_key_v2",
        "evaluation_kind": "stored_output_rescore",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--tasks-file", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.results.resolve() == args.out.resolve():
        parser.error("--out must differ from the original result file")
    tasks = {task["id"]: task for task in _read_json(args.tasks_file)} if args.tasks_file else {}
    rows = [rescore_row(json.loads(line), tasks) for line in args.results.read_text().splitlines() if line.strip()]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    changed = sum(row["correct"] != row["previous_correct"] for row in rows)
    print(f"Rescored {len(rows)} stored outputs; changed {changed} decisions -> {args.out}")


if __name__ == "__main__":
    main()
