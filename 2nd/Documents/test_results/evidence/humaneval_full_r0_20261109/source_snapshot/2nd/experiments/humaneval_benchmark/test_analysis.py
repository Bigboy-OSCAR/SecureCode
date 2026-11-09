"""Known-answer aggregation checks, isolated from real benchmark artifacts."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import analyze_and_report as analysis


class KnownOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="securecode-he-analysis-test-")
        self.previous_out, self.previous_report = analysis.OUT, analysis.REPORT
        analysis.OUT = Path(self.tmp.name)
        analysis.REPORT = analysis.OUT / "synthetic_fixture_report.md"

    def tearDown(self):
        analysis.OUT, analysis.REPORT = self.previous_out, self.previous_report
        self.tmp.cleanup()

    def fixture(self, equal_quality=False):
        rows, scores = [], []
        for i in range(164):
            # 100 both, 20 FULL-only, 30 R0-only, 14 neither.
            full_pass = i < 120
            r0_pass = i < 100 or 120 <= i < 150
            if equal_quality:
                r0_pass = full_pass
            for arm, passed in [("FULL", full_pass), ("R0", r0_pass)]:
                row = {"task_id": f"HumanEval/{i}", "arm": arm, "index": len(rows),
                       "solution": "def fixture_only():\n    return 1\n",
                       "input_tokens": 100 if arm == "FULL" else 25,
                       "context_tokens": 90 if arm == "FULL" else 15,
                       "output_tokens": 10, "query_seconds": 10 if arm == "FULL" else 2,
                       "preparation_seconds": 0.1, "generation_seconds": 9.9 if arm == "FULL" else 1.9,
                       "first_token_seconds": 8 if arm == "FULL" else 1,
                       "peak_memory_gb": 20, "source_count": 169 if arm == "FULL" else 4,
                       "target_included": True, "syntax_ok": True, "has_entry_point": True,
                       "finish_reason": "stop", "session": "SYNTHETIC_TEST_ONLY",
                       "started_at_utc": "2026-11-09T00:00:00+00:00",
                       "ended_at_utc": "2026-11-09T00:00:10+00:00"}
                rows.append(row)
                scores.append({"task_id": row["task_id"], "arm": arm, "base_pass": passed, "plus_pass": passed})
        return rows, scores

    def test_known_paired_counts_and_reductions(self):
        summary, _ = analysis.summarize(*self.fixture())
        self.assertEqual(summary["arms"]["FULL"]["plus_correct"], 120)
        self.assertEqual(summary["arms"]["R0"]["plus_correct"], 130)
        self.assertEqual({k: v["count"] for k, v in summary["paired"].items()},
                         {"both_pass": 100, "full_only": 20, "r0_only": 30, "neither_pass": 14})
        self.assertAlmostEqual(summary["contrasts"]["plus_pass_difference_pp"]["estimate"], 1000 / 164)
        self.assertEqual(summary["contrasts"]["input_token_reduction_percent"]["estimate"], 75)
        self.assertEqual(summary["contrasts"]["query_time_reduction_percent"]["estimate"], 80)
        self.assertEqual(summary["contrasts"]["query_seconds_difference"]["estimate"], -8)
        self.assertEqual(summary["mean_query_speedup"], 5)
        self.assertEqual(summary["arms"]["FULL"]["input_tokens"]["sum"], 16400)
        self.assertEqual(len((analysis.OUT / "per_task_results.jsonl").read_text().splitlines()), 164)

    def test_identical_pairs_have_zero_quality_difference_interval(self):
        summary, _ = analysis.summarize(*self.fixture(equal_quality=True))
        self.assertEqual(summary["contrasts"]["plus_pass_difference_pp"],
                         {"estimate": 0.0, "ci95": [0.0, 0.0]})
        self.assertEqual(summary["paired"]["full_only"]["count"], 0)
        self.assertEqual(summary["paired"]["r0_only"]["count"], 0)

    def test_report_uses_the_computed_counts_and_explains_metrics(self):
        summary, keyed = analysis.summarize(*self.fixture())
        analysis.run.dump(analysis.OUT / "preflight.json", {
            "base_tests": 1570, "extra_tests": 122683, "source_nodes": 169,
            "dependency_edges": 0, "index_build_seconds": 0.02,
        })
        analysis.run.dump(analysis.OUT / "verification.json", {"fixture": "SYNTHETIC_TEST_ONLY"})
        problems = {f"HumanEval/{i}": {"entry_point": f"fixture_{i}"} for i in range(164)}
        analysis.report(summary, keyed, problems)
        text = analysis.REPORT.read_text()
        for expected in ["120/164", "130/164", "75.00%", "80.00%", "5.00배", "+6.10%p",
                         "한 번 생성한 코드", "기다리는 시간", "읽히는지 측정", "표준 HumanEval+"]:
            self.assertIn(expected, text)
        manifest = json.loads((analysis.OUT / "report_manifest.json").read_text())
        self.assertEqual(manifest["report_sha256"], analysis.run.sha(analysis.REPORT))


if __name__ == "__main__":
    unittest.main()
