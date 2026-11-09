"""Wait for this exact generation run, then grade, verify, and save the report.

This is a local continuation of one benchmark, not a recurring automation.
It never starts, retries, repairs, or changes a model generation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[2] / "2nd/Documents/test_results/evidence/humaneval_full_r0_20261109"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def status(stage, **values):
    dest = OUT / "completion_status.json"
    temp = dest.with_suffix(".json.part")
    temp.write_text(json.dumps({"stage": stage, "at_utc": now(), "pid": os.getpid(), **values}, indent=2) + "\n")
    os.replace(temp, dest)
    print(stage, values, flush=True)


def main():
    pipeline = json.loads((OUT / "completion_pipeline.json").read_text())
    for name, expected in pipeline["sources_sha256"].items():
        assert sha(Path(name)) == expected, name
    status("waiting_for_generation")
    start = last_change = time.monotonic()
    count = -1
    while not (OUT / "generation_complete.json").exists():
        current = len(list((OUT / "calls").glob("*.json.gz")))
        if current != count:
            count = current
            last_change = time.monotonic()
            status("waiting_for_generation", completed_calls=count, planned_calls=328)
        if time.monotonic() - last_change > 3 * 3600:
            status("needs_attention", reason="No new completed call for three hours; no restart attempted", completed_calls=count)
            return 2
        if time.monotonic() - start > 72 * 3600:
            status("needs_attention", reason="Observation deadline reached; no restart attempted", completed_calls=count)
            return 2
        time.sleep(30)
    assert len(list((OUT / "calls").glob("*.json.gz"))) == 328
    for stage, script, args, log_name in [
        ("grading", "evaluate_solutions.py", ["grade"], "grading.log"),
        ("verifying_and_reporting", "analyze_and_report.py", [], "analysis.log"),
    ]:
        assert sha(HERE / script) == pipeline["sources_sha256"][str(HERE / script)]
        status(stage)
        with (OUT / log_name).open("a") as log:
            result = subprocess.run([sys.executable, str(HERE / script), *args], stdout=log, stderr=subprocess.STDOUT, cwd=HERE.parents[2])
        if result.returncode:
            status("needs_attention", failed_stage=stage, returncode=result.returncode, log=log_name)
            return result.returncode
    manifest = json.loads((OUT / "report_manifest.json").read_text())
    assert sha(Path(manifest["report"])) == manifest["report_sha256"]
    status("report_ready_for_final_review", report=manifest["report"], report_sha256=manifest["report_sha256"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        status("needs_attention", exception=repr(exc))
        raise
