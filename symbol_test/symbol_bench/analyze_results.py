from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def _load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize symbol selector benchmark JSONL results.")
    parser.add_argument("results", type=Path)
    args = parser.parse_args()

    rows = _load_rows(args.results)
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_mode[row["mode"]].append(row)

    print("mode,cases,accuracy,mean_wall_s,mean_prompt_chars,mean_prompt_tokens,mean_prompt_eval_ms")
    for mode, group in sorted(by_mode.items()):
        accuracy = sum(1 for row in group if row["correct"]) / len(group)
        token_values = [row.get("prompt_tokens") or row["estimated_prompt_tokens"] for row in group]
        eval_values = [row["prompt_eval_ms"] for row in group if row.get("prompt_eval_ms") is not None]
        print(
            f"{mode},{len(group)},{accuracy:.3f},"
            f"{mean(row['wall_seconds'] for row in group):.3f},"
            f"{mean(row['prompt_chars'] for row in group):.0f},"
            f"{mean(token_values):.0f},"
            f"{mean(eval_values) if eval_values else 0:.2f}"
        )

    baseline = by_mode.get("full_repo")
    if baseline:
        base_chars = mean(row["prompt_chars"] for row in baseline)
        base_wall = mean(row["wall_seconds"] for row in baseline)
        print()
        for mode in ["full_file", "line_span", "symbol_oracle", "symbol_select"]:
            group = by_mode.get(mode)
            if not group:
                continue
            chars = mean(row["prompt_chars"] for row in group)
            wall = mean(row["wall_seconds"] for row in group)
            print(f"{mode}_prompt_char_reduction_vs_full_repo={(1 - chars / base_chars) * 100:.1f}%")
            if base_wall:
                print(f"{mode}_wall_time_change_vs_full_repo={(1 - wall / base_wall) * 100:.1f}%")


if __name__ == "__main__":
    main()
