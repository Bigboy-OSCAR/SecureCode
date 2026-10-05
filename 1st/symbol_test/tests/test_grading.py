from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symbol_test.symbol_bench import run_benchmark as bench
from symbol_test.symbol_bench.indexer import compact_outline
from symbol_test.symbol_bench.make_corpus import generate_corpus
from symbol_test.symbol_bench.rescore_results import rescore_row


class GradingRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temporary.name)
        cls.manifest = generate_corpus(cls.work, "small", noise_files=0, noise_functions=0)
        cls.root = Path(cls.manifest["corpus_root"])
        cls.index = json.loads((cls.work / "symbol_index.json").read_text())
        cls.outline = compact_outline(cls.index)
        tasks = json.loads((cls.work / "tasks.json").read_text())
        cls.billing = next(task for task in tasks if task["id"] == "billing_late_fee_grace")
        hard_path = Path(__file__).resolve().parents[1] / "tasks" / "medium_hard_tasks.json"
        cls.hard = next(
            task for task in json.loads(hard_path.read_text())
            if task["id"] == "hard_report_cache_key_composed_result"
        )
        cls.args = argparse.Namespace(selector_candidates=24, bundle_depth=1, bundle_max_symbols=8)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @staticmethod
    def call(answer: str, returncode: int = 0) -> dict:
        return {
            "answer": answer, "returncode": returncode, "prompt_chars": 20,
            "estimated_prompt_tokens": 5, "prompt_tokens": 5 if returncode == 0 else None,
            "prompt_eval_ms": 1.0 if returncode == 0 else None, "wall_seconds": 0.01,
        }

    def run_mode(self, mode: str, calls: list[dict]) -> dict:
        with patch.object(bench, "_run_llama", side_effect=calls):
            return bench._run_case_mode(self.args, self.root, self.index, self.outline, self.billing, mode)

    def test_error_log_containing_expected_number_never_passes(self) -> None:
        error = "main: prompt is too long (67191 tokens, max 65532)"
        for mode in bench.ALL_MODES:
            if mode in {"symbol_select", "symbol_filtered_select_bundle"}:
                continue
            with self.subTest(mode=mode):
                result = self.run_mode(mode, [self.call(error, 1)])
                self.assertFalse(result["correct"])
                self.assertFalse(result["execution_ok"])

    def test_failed_selector_cannot_pass_even_with_valid_uri_and_answer(self) -> None:
        for mode in ["symbol_select", "symbol_filtered_select_bundle"]:
            with self.subTest(mode=mode):
                result = self.run_mode(mode, [self.call(self.billing["target_uri"], 1), self.call("3")])
                self.assertFalse(result["correct"])
                self.assertFalse(result["execution_ok"])
                self.assertFalse(result["selection_correct"])
                self.assertIsNone(result["selected_uri"])

    def test_failed_final_call_cannot_pass_after_successful_selection(self) -> None:
        for mode in ["symbol_select", "symbol_filtered_select_bundle"]:
            with self.subTest(mode=mode):
                result = self.run_mode(mode, [self.call(self.billing["target_uri"]), self.call("3", 1)])
                self.assertTrue(result["selection_correct"])
                self.assertFalse(result["execution_ok"])
                self.assertFalse(result["correct"])

    def test_successful_correct_calls_still_pass_in_every_mode(self) -> None:
        for mode in bench.ALL_MODES:
            with self.subTest(mode=mode):
                calls = [self.call("3")]
                if mode in {"symbol_select", "symbol_filtered_select_bundle"}:
                    calls.insert(0, self.call(self.billing["target_uri"]))
                result = self.run_mode(mode, calls)
                self.assertTrue(result["execution_ok"])
                self.assertTrue(result["correct"])

    def test_cache_key_matches_executed_python_ground_truth(self) -> None:
        spec = importlib.util.spec_from_file_location("generated_reporting", self.root / "reports/reporting.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        actual = module.build_cache_key(" North/East Plan ", " TEAM-A ", 12)
        self.assertEqual(actual, "report:team-a:north/east_plan:v12")
        self.assertTrue(bench._answer_is_correct(self.call(actual), self.hard))

    def test_exact_answer_accepts_only_outer_presentation_wrappers(self) -> None:
        expected = "report:team-a:north/east_plan:v12"
        for answer in [
            expected, f'"{expected}"', f"'{expected}'", f"`{expected}`",
            f"```{expected}```", f"```\n{expected}\n```",
            f"```text\n{expected}\n```", f"```python\n{expected}\n```",
            f"```json\n\"{expected}\"\n```",
        ]:
            with self.subTest(answer=answer):
                self.assertTrue(bench._answer_is_correct(self.call(answer), self.hard))

    def test_wrong_slash_case_suffix_or_explanation_is_rejected(self) -> None:
        expected = "report:team-a:north/east_plan:v12"
        for answer in [
            "report:team-a:north_east_plan:v12", "report:TEAM-A:north/east_plan:v12",
            "report:team-a:North/East_plan:v12", "report:team-a:north/east plan:v12",
            expected + "extra", "Answer: " + expected, f'" {expected} "',
        ]:
            with self.subTest(answer=answer):
                self.assertFalse(bench._answer_is_correct(self.call(answer), self.hard))
        self.assertFalse(bench._answer_is_correct(self.call(expected, 1), self.hard))

    def test_saved_error_is_regraded_without_changing_timing_or_original_row(self) -> None:
        row = {
            "task_id": self.billing["id"], "mode": "full_repo", "correct": True,
            "expected_substrings": ["3"], "wall_seconds": 1.2,
            "calls": [self.call("prompt too long, max 65532", 1)],
        }
        result = rescore_row(row, {})
        self.assertFalse(result["correct"])
        self.assertTrue(result["previous_correct"])
        self.assertTrue(row["correct"])
        self.assertEqual(result["wall_seconds"], row["wall_seconds"])
        self.assertEqual(result["calls"], row["calls"])

    def test_saved_correct_key_uses_fixed_task_instead_of_old_forbidden_strings(self) -> None:
        expected = "report:team-a:north/east_plan:v12"
        row = {
            "task_id": self.hard["id"], "mode": "full_file", "correct": False,
            "required_substrings": [expected], "forbidden_substrings": ["TEAM-A", "North/East"],
            "calls": [self.call(expected)],
        }
        self.assertTrue(rescore_row(row, {self.hard["id"]: self.hard})["correct"])


if __name__ == "__main__":
    unittest.main()
