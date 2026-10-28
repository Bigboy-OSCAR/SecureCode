"""Small semantic fixtures and direct equivalence checks against pinned sources.

Run with: <benchmark-venv>/bin/python -m unittest discover \
    -s 2nd/experiments/document_benchmarks -p test_metrics.py -v

The official HF datasets wrapper and LongBench's unrelated Chinese/ROUGE
dependencies are not installed: relevant functions are extracted by AST from
the unchanged vendored source and executed directly. Official SCROLLS ROUGE's
multiprocessing Pool is replaced with serial starmap solely for these fixtures.
Its scorer, text processing, reference aggregation and rounding stay intact.
"""

import ast
from collections import defaultdict
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import metrics


HERE = Path(__file__).resolve().parent
OFFICIAL = HERE / "official_sources"


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def official_functions(path, names, namespace):
    parsed = ast.parse(path.read_text())
    selected = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("Pinned official function set changed")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class SerialPool:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starmap(self, function, pairs):
        return [function(*pair) for pair in pairs]


class MetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.official_f1 = import_file("official_scrolls_f1", OFFICIAL / "scrolls/metrics/f1.py")
        cls.official_em = import_file("official_scrolls_em", OFFICIAL / "scrolls/metrics/exact_match.py")
        import collections
        import re
        import string
        lb = official_functions(
            OFFICIAL / "longbench/LongBench/metrics.py",
            {"normalize_answer", "f1_score", "qa_f1_score"},
            {"Counter": collections.Counter, "re": re, "string": string},
        )
        cls.lb = official_functions(
            OFFICIAL / "longbench/LongBench/eval.py",
            {"scorer"},
            {"dataset2metric": {name: lb["qa_f1_score"] for name in metrics.LONG_BENCH_DATASETS}},
        )

    def test_normalization_order_punctuation_and_articles(self):
        self.assertEqual(metrics.normalize_answer(" The cat's A_B, an apple! "), "cats ab apple")
        for text in [" The cat's A_B, an apple! ", "A", "", "café—au—lait", "THE\nCat"]:
            self.assertEqual(metrics.normalize_answer(text), self.official_f1.normalize_answer(text))

    def test_f1_counts_duplicate_tokens_and_empty_scores(self):
        self.assertAlmostEqual(metrics.token_f1("cat cat dog", "cat dog dog"), 2 / 3)
        self.assertEqual(metrics.token_f1("", ""), 0)
        self.assertEqual(metrics.token_f1("the", "a"), 0)
        self.assertEqual(metrics.score_example("qasper", "The blue whale", ["red fish", "blue whale"]), {"f1": 1})

    def test_f1_dataset_aggregation_matches_both_official_benchmarks(self):
        predictions = ["The blue whale", "cat cat dog", "", "Yes.\nThe evidence also says something else."]
        references = [["red fish", "blue whale"], ["cat dog dog"], ["missing"], ["yes"]]
        for dataset in ["qasper", "narrative_qa"]:
            actual = metrics.score_dataset(dataset, predictions, references)
            expected = self.official_f1.compute_f1(predictions, references)
            self.assertAlmostEqual(actual["score_unrounded"], expected)
            self.assertEqual(actual["score"], round(expected, 4))
        for dataset in metrics.LONG_BENCH_DATASETS:
            self.assertEqual(
                metrics.score_dataset(dataset, predictions, references)["score"],
                self.lb["scorer"](dataset, predictions, references, []),
            )
            # Selected LongBench QA datasets retain trailing explanatory lines.
            self.assertLess(metrics.score_example(dataset, predictions[-1], references[-1])["f1"], 1)

    def test_quality_requires_full_normalized_answer_not_choice_letter(self):
        predictions = ["The Red Fox!", "A", "red fox because it hunts", "blue dog"]
        references = [["red fox"], ["red fox"], ["red fox"], ["blue dog", "green cat"]]
        actual = metrics.score_dataset("quality", predictions, references)
        self.assertEqual(actual["score"], 50)
        self.assertEqual(actual["score"], self.official_em.compute_exact_match(predictions, references))

    def test_bad_inputs_fail_instead_of_changing_population(self):
        for dataset in metrics.DATASET_METRICS:
            with self.assertRaises(ValueError):
                metrics.score_dataset(dataset, ["x"], [])
            with self.assertRaises(ValueError):
                metrics.score_dataset(dataset, [], [])
            with self.assertRaises(ValueError):
                metrics.score_example(dataset, "x", [])
            with self.assertRaises(TypeError):
                metrics.score_example(dataset, None, ["x"])
        with self.assertRaises(ValueError):
            metrics.aggregate_scores("qasper", [{"f1": float("nan")}])
        with self.assertRaises(ValueError):
            metrics.score_example("not-a-dataset", "x", ["x"])

    def test_empty_failed_requests_remain_in_denominator(self):
        self.assertEqual(metrics.score_dataset("hotpotqa", ["answer", ""], [["answer"], ["answer"]])["score"], 50)

    def test_qmsum_geometric_mean_is_computed_after_corpus_average(self):
        rows = [dict.fromkeys(metrics.ROUGE_TYPES, 1.0), {"rouge1": 1.0, "rouge2": 0.0, "rougeL": 0.5, "rougeLsum": 0.5}]
        actual = metrics.aggregate_scores("qmsum", rows)
        expected = (100 * 50 * 75) ** (1 / 3)
        self.assertAlmostEqual(actual["score_unrounded"], expected)
        self.assertNotAlmostEqual(actual["score_unrounded"], 50)  # Incorrect mean of item geomeans.

    def test_qmsum_official_rouge_multireference_and_no_stemming(self):
        official_rouge = import_file("official_scrolls_rouge", OFFICIAL / "scrolls/metrics/rouge.py")
        helper = official_functions(
            OFFICIAL / "scrolls/metrics/scrolls.py", {"_compute_helper"}, {"defaultdict": defaultdict}
        )["_compute_helper"]
        predictions = ["a b c d", "running", "", "Alice left. Bob stayed."]
        references = [["a b x y", "a c b d"], ["run"], ["some text"], ["Bob stayed. Alice left."]]
        with patch.object(official_rouge, "Pool", SerialPool):
            expected = helper(
                predictions, references,
                metric_fn=official_rouge.compute_rouge,
                agg_fn=max,
                metric_fn_kwargs={"use_stemmer": False},
                metric_returns_per_example=True,
                transform_single_input_fn=official_rouge.postprocess_text,
                transform_result_fn=lambda output: {key: value.fmeasure * 100 for key, value in output.items()},
                transform_aggregated_result_fn=lambda output: output.update(
                    {"geometric_mean": (output["rouge1"] * output["rouge2"] * output["rougeL"]) ** (1 / 3)}
                ) or output,
            )
        actual = metrics.score_dataset("qmsum", predictions, references)
        for name, value in expected.items():
            self.assertAlmostEqual(actual["components_unrounded"][f"rouge/{name}"], value)
            self.assertEqual(actual[f"rouge/{name}"], round(value, 4))
        first = metrics.score_example("qmsum", predictions[0], references[0])
        self.assertEqual(first["rouge1"], 1)
        self.assertAlmostEqual(first["rouge2"], 1 / 3)
        self.assertEqual(first["rougeL"], 0.75)
        self.assertEqual(metrics.score_example("qmsum", "running", ["run"])["rouge1"], 0)


if __name__ == "__main__":
    unittest.main()
