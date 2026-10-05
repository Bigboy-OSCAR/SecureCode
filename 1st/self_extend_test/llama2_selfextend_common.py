from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
WORK = ROOT / "work"

LLAMA2_CACHE = Path(
    "/Users/oscar/.cache/huggingface/hub/models--TheBloke--Llama-2-7B-Chat-GGUF/"
    "snapshots/191239b3e26b2882fb562ffccdd1cf0f65402adb"
)

MODELS = {
    "q4_k_m": LLAMA2_CACHE / "llama-2-7b-chat.Q4_K_M.gguf",
    "q5_k_m": LLAMA2_CACHE / "llama-2-7b-chat.Q5_K_M.gguf",
}


def ensure_dirs() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)


def require_models(model_keys: list[str]) -> None:
    missing = [str(MODELS[key]) for key in model_keys if not MODELS[key].exists()]
    if missing:
        joined = "\n".join(missing)
        raise SystemExit(f"missing model file(s):\n{joined}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_perf(text: str) -> dict[str, float | int | None]:
    perf: dict[str, float | int | None] = {
        "prompt_eval_ms": None,
        "prompt_tokens": None,
        "eval_ms": None,
        "eval_tokens": None,
        "total_ms": None,
        "prompt_tps": None,
        "generation_tps": None,
    }
    prompt_match = re.search(
        r"prompt eval time =\s*([0-9.]+) ms /\s*(\d+) tokens .*?([0-9.]+) tokens per second",
        text,
    )
    if prompt_match:
        perf["prompt_eval_ms"] = float(prompt_match.group(1))
        perf["prompt_tokens"] = int(prompt_match.group(2))
        perf["prompt_tps"] = float(prompt_match.group(3))
    eval_match = re.search(
        r"eval time =\s*([0-9.]+) ms /\s*(\d+) runs .*?([0-9.]+) tokens per second",
        text,
    )
    if eval_match:
        perf["eval_ms"] = float(eval_match.group(1))
        perf["eval_tokens"] = int(eval_match.group(2))
        perf["generation_tps"] = float(eval_match.group(3))
    total_match = re.search(r"total time =\s*([0-9.]+) ms /", text)
    if total_match:
        perf["total_ms"] = float(total_match.group(1))
    compact_match = re.search(r"\[ Prompt:\s*([0-9.]+) t/s \| Generation:\s*([0-9.]+) t/s \]", text)
    if compact_match:
        perf["prompt_tps"] = float(compact_match.group(1))
        perf["generation_tps"] = float(compact_match.group(2))
    return perf


def clean_generation(text: str) -> str:
    text = text.replace("\b", "")
    if "generate:" in text:
        text = text.split("generate:", 1)[1]
        text = text.split("\n\n", 1)[-1]
    for marker in ["common_perf_print:", "llama_perf_context_print:", "llama_memory_breakdown_print:", "[ Prompt:"]:
        if marker in text:
            text = text.split(marker, 1)[0]
    text = text.replace("[end of text]", "")
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    return " ".join(text.split())

