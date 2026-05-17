from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from .llama2_selfextend_common import MODELS, RESULTS, WORK, ensure_dirs, require_models, write_csv, write_json


def parse_ppl(text: str) -> dict:
    final = re.search(r"Final estimate: PPL =\s*([0-9.]+)(?: \+/- ([0-9.]+))?", text)
    indexed = re.findall(r"\[(\d+)\]([0-9.]+),", text)
    chunk_ppl = [float(value) for _, value in indexed]
    prompt = re.search(
        r"prompt eval time =\s*([0-9.]+) ms /\s*(\d+) tokens .*?([0-9.]+) tokens per second",
        text,
    )
    return {
        "ppl": float(final.group(1)) if final else (chunk_ppl[0] if len(chunk_ppl) == 1 else None),
        "ppl_stderr": float(final.group(2)) if final and final.group(2) else None,
        "chunk_ppl": chunk_ppl,
        "prompt_eval_ms": float(prompt.group(1)) if prompt else None,
        "prompt_tokens": int(prompt.group(2)) if prompt else None,
        "prompt_tps": float(prompt.group(3)) if prompt else None,
    }


def run_case(model_key: str, data_file: Path, ctx_size: int, chunks: int, timeout: int) -> dict:
    command = [
        "llama-perplexity",
        "-m",
        str(MODELS[model_key]),
        "-f",
        str(data_file),
        "-c",
        str(ctx_size),
        "--chunks",
        str(chunks),
        "--ppl-stride",
        str(ctx_size),
        "--device",
        "none",
        "-ngl",
        "0",
        "--fit",
        "off",
        "--no-warmup",
    ]
    name = f"{model_key}_ctx{ctx_size}_chunks{chunks}"
    start = time.monotonic()
    proc = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    elapsed = time.monotonic() - start
    output = proc.stdout + "\n" + proc.stderr
    log_path = RESULTS / "pg19_ppl_logs" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    return {
        "case": name,
        "model": model_key,
        "ctx_size": ctx_size,
        "chunks": chunks,
        "data_file": str(data_file),
        "returncode": proc.returncode,
        "elapsed_sec": round(elapsed, 3),
        "log": str(log_path),
        **parse_ppl(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PG-19 test-split perplexity with llama-perplexity.")
    parser.add_argument("--models", nargs="+", default=["q4_k_m", "q5_k_m"], choices=sorted(MODELS))
    parser.add_argument("--data-file", type=Path, default=WORK / "pg19_test_sample.txt")
    parser.add_argument("--ctx-sizes", nargs="+", type=int, default=[2048, 4096])
    parser.add_argument("--chunks", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--out-prefix", default="llama2_pg19_ppl")
    args = parser.parse_args()

    ensure_dirs()
    require_models(args.models)
    if not args.data_file.exists():
        raise SystemExit(f"missing PG-19 data file: {args.data_file}")

    rows = []
    for model_key in args.models:
        for ctx_size in args.ctx_sizes:
            row = run_case(model_key, args.data_file, ctx_size, args.chunks, args.timeout)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)

    write_json(RESULTS / f"{args.out_prefix}.json", rows)
    write_csv(RESULTS / f"{args.out_prefix}.csv", rows)


if __name__ == "__main__":
    main()
