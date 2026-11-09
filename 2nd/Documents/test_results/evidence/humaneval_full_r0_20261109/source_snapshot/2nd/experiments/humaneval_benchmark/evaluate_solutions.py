"""Execute HumanEval+ tests with EvalPlus core checks, separately from generation.

Using the core API avoids importing unused GPU/API provider dependencies. The
timeouts, numeric tolerances, special oracles and subprocess checks are EvalPlus.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import inspect
import json
import multiprocessing
import os
from pathlib import Path
import pickle
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[2] / "2nd/Documents/test_results/evidence/humaneval_full_r0_20261109"

# EvalPlus documents -1 as disabling its optional address-space memory limit.
# Darwin raises ValueError for the Linux-oriented RLIMIT_AS/RLIMIT_DATA setting.
# Keep the official timeouts and reliability guard; the execution environment
# continues to restrict network and writes independently of this setting.
os.environ["EVALPLUS_MAX_MEMORY_BYTES"] = "-1"


def install_oracle_bookkeeping_fix():
    """Keep the official root oracle but record successful checks before return.

    v0.3.1's `continue` skips the shared success/progress bookkeeping for
    HumanEval/32. Its own canonical solution consequently fails. Setting the
    already-asserted comparison to True reaches the common bookkeeping while
    retaining exactly the same polynomial-residual acceptance criterion.
    Apply the same bookkeeping correction present in upstream master, verified
    2026-11-09. This runs on import so subprocess spawn installs the same fix.
    """
    import evalplus.eval as official
    source = inspect.getsource(official.unsafe_execute)
    before = 'assert abs(_poly(*inp, out)) <= atol\n                            continue'
    after = ('assert abs(_poly(*inp, out)) <= atol\n'
             '                            details[i] = True\n'
             '                            progress.value += 1\n'
             '                            continue')
    assert source.count(before) == 1
    fixed = source.replace(before, after)
    exec(compile(fixed, "<evalplus-find-zero-bookkeeping-fix>", "exec"), official.__dict__)
    return {"official_module_sha256": hashlib.sha256(Path(official.__file__).read_bytes()).hexdigest(),
            "before": before, "after": after,
            "patched_function_sha256": hashlib.sha256(fixed.encode()).hexdigest()}


EVALUATOR_ADAPTATION = install_oracle_bookkeeping_fix()


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temp, path)


def problems():
    with gzip.open(OUT / "HumanEvalPlus-v0.1.10.jsonl.gz", "rt") as f:
        return {p["task_id"]: p for p in map(json.loads, f)}


def groundtruth():
    from evalplus.gen.util import trusted_exec
    dest = OUT / "grading" / "groundtruth.pkl"
    if dest.exists():
        meta = json.loads(dest.with_suffix(".json").read_text())
        assert sha(dest) == meta["sha256"]
        assert meta["dataset_sha256"] == sha(OUT / "HumanEvalPlus-v0.1.10.jsonl.gz")
        with dest.open("rb") as f:
            return pickle.load(f)
    outputs = {}
    start = time.perf_counter()
    for task_id, p in problems().items():
        outputs[task_id] = {}
        for group in ["base", "plus"]:
            answer, times = trusted_exec(p["prompt"] + p["canonical_solution"],
                                         p[group + "_input"], p["entry_point"], record_time=True)
            outputs[task_id][group] = {"expected": answer, "reference_seconds": times}
        print("oracle", task_id, flush=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        pickle.dump(outputs, f)
    dump(dest.with_suffix(".json"), {"created_at_utc": now(), "sha256": sha(dest),
         "dataset_sha256": sha(OUT / "HumanEvalPlus-v0.1.10.jsonl.gz"),
         "seconds": time.perf_counter() - start, "tasks": len(outputs)})
    return outputs


def check(p, solution, expected):
    from evalplus.eval import untrusted_check
    statuses = {}
    for group in ["base", "plus"]:
        status, details = untrusted_check(
            "humaneval", solution, copy.deepcopy(p[group + "_input"]), p["entry_point"],
            expected=expected[group]["expected"], atol=p["atol"],
            ref_time=expected[group]["reference_seconds"], fast_check=True,
            min_time_limit=1.0, gt_time_limit_factor=4.0,
        )
        statuses[group] = {"status": status, "checked": len(details), "tests": len(p[group + "_input"]),
                           "first_failure": next((i for i, ok in enumerate(details) if not ok), None)}
    statuses["base_pass"] = statuses["base"]["status"] == "pass"
    statuses["plus_pass"] = statuses["base_pass"] and statuses["plus"]["status"] == "pass"
    return statuses


def controls(task_ids=None):
    expected = groundtruth()
    records = []
    for tid, p in problems().items():
        if task_ids and tid not in task_ids:
            continue
        record = {"task_id": tid, **check(p, p["prompt"] + p["canonical_solution"], expected[tid])}
        records.append(record)
        print("canonical", tid, record["base"]["status"], record["plus"]["status"], flush=True)
    suffix = "controls_subset.json" if task_ids else "controls.json"
    unexpected = [r for r in records if not r["plus_pass"] and r["task_id"] != "HumanEval/32"]
    assert not unexpected, unexpected
    # HumanEval/32 has a special residual oracle independent of reference outputs.
    # Its distributed Newton-method reference fails to converge on six inputs.
    # Preserve those tests and the oracle; do not loosen tolerance or drop a task.
    from evalplus.eval._special_oracle import _poly
    root_problem = problems()["HumanEval/32"]
    bad_reference_roots = [{"input_index": i, "input": inp, "reference_output": value,
                            "polynomial_residual": _poly(*inp, value)}
                           for i, (inp, value) in enumerate(zip(root_problem["plus_input"], expected["HumanEval/32"]["plus"]["expected"]))
                           if abs(_poly(*inp, value)) > root_problem["atol"]]
    assert len(bad_reference_roots) == 6
    dump(OUT / "grading" / suffix, {"at_utc": now(), "all_pass": all(r["plus_pass"] for r in records),
         "unexpected_failures": unexpected, "verified": not unexpected,
         "known_reference_solver_failure": {"task_id": "HumanEval/32", "atol": root_problem["atol"],
             "invalid_roots": bad_reference_roots, "scoring": "Official polynomial-residual oracle retained; canonical outputs are not the comparison target for this task; no test/task excluded."},
         "records": records})
    if not task_ids:
        # Incorrect ordinary and special-oracle solutions must both be rejected.
        p = problems()["HumanEval/0"]
        bad = check(p, "def has_close_elements(numbers, threshold):\n    return False\n", expected[p["task_id"]])
        assert not bad["plus_pass"]
        bad_root = check(root_problem, "def find_zero(xs):\n    return 0.0\n", expected[root_problem["task_id"]])
        assert not bad_root["plus_pass"]
        simple_root = {**root_problem, "base_input": [[[-1, 1]]], "plus_input": [[[2, -2]]], "atol": 0.0001}
        simple_expected = {group: {"expected": [1.0], "reference_seconds": [0.00001]} for group in ["base", "plus"]}
        valid_root = check(simple_root, "def find_zero(xs):\n    return 1.0\n", simple_expected)
        assert valid_root["plus_pass"]
        dump(OUT / "grading" / "negative_control.json", {"HumanEval/0": bad, "HumanEval/32": bad_root,
             "known_valid_root_positive_control": valid_root})
        dump(OUT / "grading" / "evaluator_adaptation.json", {
            "at_utc": now(), "driver_sha256": sha(__file__),
            "evalplus_version": "0.3.1", "memory_limit_env": "EVALPLUS_MAX_MEMORY_BYTES=-1",
            "find_zero_bookkeeping_fix": EVALUATOR_ADAPTATION,
            "upstream_fix_source": "https://github.com/evalplus/evalplus/blob/master/evalplus/eval/__init__.py",
            "reason": "Before any model generation, canonical controls failed: Darwin resource.setrlimit ValueError; then HumanEval/32 success records missing. No acceptance criterion changed.",
        })


def grade():
    assert json.loads((OUT / "grading/controls.json").read_text())["verified"]
    assert (OUT / "generation_complete.json").exists()
    expected = groundtruth()
    data = problems()
    records = []
    for path in sorted((OUT / "calls").glob("*.json.gz")):
        with gzip.open(path, "rt") as f:
            sample = json.load(f)
        dest = OUT / "grading" / "cases" / (path.name.removesuffix(".json.gz") + ".json")
        if dest.exists():
            row = json.loads(dest.read_text())
            assert row["call_sha256"] == sha(path)
        else:
            started = time.perf_counter()
            row = {"index": sample["index"], "task_id": sample["task_id"], "arm": sample["arm"],
                   "call_sha256": sha(path), "solution_sha256": sample["solution_sha256"],
                   **check(data[sample["task_id"]], sample["solution"], expected[sample["task_id"]]),
                   "graded_at_utc": now(), "grading_seconds": time.perf_counter() - started}
            dump(dest, row)
        records.append(row)
        print("graded", row["index"] + 1, row["task_id"], row["arm"], row["base_pass"], row["plus_pass"], flush=True)
    assert len(records) == 328
    dump(OUT / "grading" / "results.json", records)
    dump(OUT / "grading" / "complete.json", {"at_utc": now(), "samples": 328,
         "results_sha256": sha(OUT / "grading/results.json"), "driver_sha256": sha(__file__)})


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["controls", "grade", "oracle"])
    parser.add_argument("--tasks", help="Comma separated task numbers for evaluator smoke test")
    args = parser.parse_args()
    if args.phase == "controls":
        controls({f"HumanEval/{x}" for x in args.tasks.split(",")} if args.tasks else None)
    elif args.phase == "grade":
        grade()
    else:
        groundtruth()
