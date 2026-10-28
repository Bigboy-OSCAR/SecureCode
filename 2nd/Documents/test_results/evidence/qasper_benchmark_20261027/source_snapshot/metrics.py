"""Auditable metrics for the seven document benchmark datasets.

The formulas and aggregation match these *vendored* official sources:

* tau/scrolls @ 927b875150ac8f02262ddd3b078d33a9debc935b,
  metrics/{scrolls,f1,exact_match,rouge}.py.
* THUDM/LongBench @ 2e00731f8d0bff23dc4325161044d0ed8af94c1e,
  LongBench/{metrics,eval}.py.

QMSum needs rouge-score==0.1.2, nltk==3.9.2, and NLTK's English
``punkt_tab`` resource. These are experiment reproducibility pins, not pins
specified by SCROLLS. Other datasets need only Python's standard library.
No model calls, reference-dependent retrieval, or answer repair occur here.
Predictions are scored exactly as supplied, including incomplete generations.
The caller is responsible for retaining failed/overflow cases in its population.

Public API:
    score_example(dataset, prediction, references) -> dict[str, float]
    aggregate_scores(dataset, example_scores) -> dict
    score_dataset(dataset, predictions, references) -> dict

Example components are unrounded fractions in [0, 1]. Dataset metrics are
percentages. ``score_unrounded`` is for analysis; ``score`` reproduces official
rounding (SCROLLS: four decimals; LongBench: two). For QMSum the primary metric
is the geometric mean of the *corpus mean* R1/R2/RL, not an average of per-item
geometric means. Max-over-reference selection is independent per ROUGE metric.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
import importlib.metadata
import math
import re
import string
from typing import Mapping, Sequence


SCROLLS_REVISION = "927b875150ac8f02262ddd3b078d33a9debc935b"
LONGBENCH_REVISION = "2e00731f8d0bff23dc4325161044d0ed8af94c1e"
QMSUM_DEPENDENCIES = {"rouge-score": "0.1.2", "nltk": "3.9.2"}
DATASET_METRICS = {
    "qmsum": "rouge/geometric_mean",
    "qasper": "f1",
    "narrative_qa": "f1",
    "quality": "exact_match",
    "hotpotqa": "f1",
    "musique": "f1",
    "multifieldqa_en": "f1",
}
LONG_BENCH_DATASETS = frozenset({"hotpotqa", "musique", "multifieldqa_en"})
ROUGE_TYPES = ("rouge1", "rouge2", "rougeL", "rougeLsum")


def normalize_answer(text: str) -> str:
    """Official SQuAD-style normalization shared by these QA evaluators.

    Punctuation removal uses ``string.punctuation`` (ASCII only); punctuation
    is deleted, not replaced with spaces. Articles are removed after this.
    """
    text = "".join(char for char in text.lower() if char not in string.punctuation)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def token_f1(prediction: str, reference: str) -> float:
    """Multiset token overlap; even two normalized-empty answers score zero."""
    predicted = normalize_answer(prediction).split()
    expected = normalize_answer(reference).split()
    overlap = sum((Counter(predicted) & Counter(expected)).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return (2 * precision * recall) / (precision + recall)


def normalized_exact_match(prediction: str, reference: str) -> float:
    """SCROLLS QuALITY EM compares normalized full texts, not choice labels."""
    return float(normalize_answer(prediction) == normalize_answer(reference))


def _check_dataset(dataset: str) -> None:
    if dataset not in DATASET_METRICS:
        raise ValueError(f"Unsupported dataset {dataset!r}; use {tuple(DATASET_METRICS)}")


def _check_item(prediction: str, references: Sequence[str]) -> None:
    if not isinstance(prediction, str):
        raise TypeError("prediction must be a string, not a missing value")
    if isinstance(references, (str, bytes)) or not isinstance(references, Sequence):
        raise TypeError("references must be a sequence of strings")
    if not references or any(not isinstance(reference, str) for reference in references):
        raise ValueError("Every evaluated item needs at least one string reference")


@lru_cache(maxsize=1)
def _rouge_runtime():
    """Fail explicitly on missing/mismatched dependencies; no metric fallback."""
    for package, expected in QMSUM_DEPENDENCIES.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"QMSum requires {package}=={expected}") from exc
        if actual != expected:
            raise RuntimeError(f"QMSum requires {package}=={expected}; found {actual}")
    import nltk
    from rouge_score import rouge_scorer

    # Preflight catches a missing punkt_tab resource before processing the corpus.
    nltk.sent_tokenize("First sentence. Second sentence.", language="english")
    return nltk, rouge_scorer.RougeScorer(ROUGE_TYPES, use_stemmer=False)


def score_example(dataset: str, prediction: str, references: Sequence[str]) -> dict[str, float]:
    """Score one item against all its references without stripping model output."""
    _check_dataset(dataset)
    _check_item(prediction, references)
    if dataset == "qmsum":
        nltk, scorer = _rouge_runtime()
        # Exact SCROLLS postprocessing; needed especially for ROUGE-Lsum.
        processed_prediction = "\n".join(nltk.sent_tokenize(prediction))
        scores = [
            scorer.score("\n".join(nltk.sent_tokenize(reference)), processed_prediction)
            for reference in references
        ]
        return {name: max(score[name].fmeasure for score in scores) for name in ROUGE_TYPES}
    if dataset == "quality":
        return {"exact_match": max(normalized_exact_match(prediction, ref) for ref in references)}
    # All five remaining datasets use the same normalized max-reference F1.
    # LongBench's first-line-only transformation is *not* used for these three
    # selected LongBench datasets; scoring the whole prediction is intentional.
    return {"f1": max(token_f1(prediction, ref) for ref in references)}


def aggregate_scores(dataset: str, example_scores: Sequence[Mapping[str, float]]) -> dict:
    """Aggregate all items, including zero scores for failed/overflow requests.

    QMSum returns rouge1/rouge2/rougeL/rougeLsum and their primary geometric
    mean under the official ``rouge/...`` names. Extra metadata keys in input
    component mappings are ignored. Missing/invalid components fail loudly.
    """
    _check_dataset(dataset)
    if not example_scores:
        raise ValueError("Cannot report a dataset score for an empty population")
    components = ROUGE_TYPES if dataset == "qmsum" else (DATASET_METRICS[dataset],)
    values = {}
    for component in components:
        component_values = [float(item[component]) for item in example_scores]
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in component_values):
            raise ValueError(f"Invalid {component} component: expected finite fractions in [0, 1]")
        # Keep the official evaluator's ordinary summation order. SCROLLS ROUGE
        # multiplies each per-example fraction by 100 before corpus averaging.
        if dataset == "qmsum":
            values[f"rouge/{component}"] = sum(value * 100 for value in component_values) / len(component_values)
        else:
            values[component] = 100.0 * sum(component_values) / len(component_values)
    if dataset == "qmsum":
        values["rouge/geometric_mean"] = (
            values["rouge/rouge1"] * values["rouge/rouge2"] * values["rouge/rougeL"]
        ) ** (1.0 / 3.0)
    primary_key = DATASET_METRICS[dataset]
    decimals = 2 if dataset in LONG_BENCH_DATASETS else 4
    return {
        "dataset": dataset,
        "num_predicted": len(example_scores),
        "metric": primary_key,
        "score": round(values[primary_key], decimals),
        "score_unrounded": values[primary_key],
        **{name: round(value, decimals) for name, value in values.items()},
        "components_unrounded": values,
    }


def score_dataset(dataset: str, predictions: Sequence[str], references: Sequence[Sequence[str]]) -> dict:
    """Convenience wrapper; mismatched lengths must never silently drop items."""
    _check_dataset(dataset)
    if isinstance(predictions, (str, bytes)) or isinstance(references, (str, bytes)):
        raise TypeError("predictions and references must be per-item sequences")
    if len(predictions) != len(references):
        raise ValueError("predictions and references must have equal lengths")
    result = aggregate_scores(
        dataset, [score_example(dataset, prediction, refs) for prediction, refs in zip(predictions, references)]
    )
    result["mean_prediction_length_characters"] = round(sum(map(len, predictions)) / len(predictions), 4)
    return result
