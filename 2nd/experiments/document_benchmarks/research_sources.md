# Official benchmark sources checked on 2026-10-27

This note records sources and implementation constraints; it contains no experimental results. “Scroll” in the request most plausibly means **SCROLLS: Standardized CompaRison Over Long Language Sequences**, because all four named tasks are in that suite. Use SCROLLS validation, not ZeroSCROLLS or the LongBench versions of the same task names. [Official repository](https://github.com/tau-nlp/scrolls), [paper](https://aclanthology.org/2022.emnlp-main.823/).

Latest scope received from the parent: evaluate **A, B, R0, FULL**. This supersedes the temporary A/B/R0-only scope. The source inventory below is independent of method count. Sixteen pinned official evaluator/loader/prompt/license files are stored in `official_sources/`, with source URLs, sizes, and SHA-256 in `official_sources/manifest.json`. Paper-specific cross-checks are in `research_papers.md`.

## Frozen public sources

Hugging Face API calls verified both repositories are public and ungated (`private=false`, `gated=false`). No account or token is required to download these public archives.

| Resource | Revision |
|---|---|
| HF `tau/scrolls` | `927b875150ac8f02262ddd3b078d33a9debc935b` |
| GitHub `tau-nlp/scrolls` | `bfc0da0747976418cd0c4b8837db023ea567ba84` |
| HF `zai-org/LongBench` (former `THUDM/LongBench`) | `5e628be450b7e67fb7ae6e201bd6d8f7056f7672` |
| GitHub `THUDM/LongBench` | `2e00731f8d0bff23dc4325161044d0ed8af94c1e` |

Revisions and bytes were retrieved from `https://huggingface.co/api/datasets/{repo}` and `/tree/{revision}?recursive=true`, and GitHub commit/tree APIs. Freeze these values rather than relying on moving `main` URLs.

SCROLLS archive base: `https://huggingface.co/datasets/tau/scrolls/resolve/927b875150ac8f02262ddd3b078d33a9debc935b/`

| Task | File appended to base | ZIP member | Current archive bytes | HF LFS SHA-256 |
|---|---|---|---:|---|
| QMSum | `qmsum.zip` | `qmsum/validation.jsonl` | 27,345,654 | `bbe55e932a78d7e1abcb90d9d6388862b54672c1e1b6c70c1461e5db7678281b` |
| Qasper | `qasper.zip` | `qasper/validation.jsonl` | 23,532,127 | `16d6202820d052e642190f37b4ebdf3a22e177d64572265d8b8123fe3224c9b1` |
| NarrativeQA | `narrative_qa.zip` | `narrative_qa/validation.jsonl` | 8,833,025,309 | `f331944ec49bf54c241174e9c9a443996f3593c25fe0710bf92276dee4156e4a` |
| QuALITY | `quality.zip` | `quality/validation.jsonl` | 31,252,462 | `3bb71203206d60db4da2af517ed29f433798a0fb34dbdeb95088cd61527c2cce` |

Archive/member conventions are specified by the [official loader](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/scrolls.py). The large NarrativeQA archive includes train/test data which this experiment does not need; HTTP range retrieval of its validation member is a possible transfer optimization. Verify range responses and extracted-member integrity rather than claiming to have checked the complete ZIP SHA when only a member was downloaded.

LongBench v1 archive: [pinned data.zip](https://huggingface.co/datasets/zai-org/LongBench/resolve/5e628be450b7e67fb7ae6e201bd6d8f7056f7672/data.zip), **113,932,529 bytes**, SHA-256 `cb45b11a4133c6bc1d6a44b0f8e701335ff1e543195db1103472e575857f7f64`. Use `hotpotqa.jsonl`, `musique.jsonl`, `multifieldqa_en.jsonl`; locate their actual member paths from the central directory. These are the LongBench **test** split. Do not use `_e` files (LongBench-E) or LongBench v2. [Official dataset card](https://huggingface.co/datasets/zai-org/LongBench/blob/5e628be450b7e67fb7ae6e201bd6d8f7056f7672/README.md).

## Counts and schemas

| Dataset | Requested split | Published JSONL row count | Unit warning |
|---|---|---:|---|
| QMSum | SCROLLS validation | 272 | Query-summary pairs |
| Qasper | SCROLLS validation | 1,726 | Multiple reference rows may share a question ID |
| NarrativeQA | SCROLLS validation | 5,878 | Multiple reference rows may share a question ID |
| QuALITY | SCROLLS validation | 2,086 | Questions, not source articles |
| HotpotQA | LongBench test | 200 | Adapted LongBench examples, not full original HotpotQA dev |
| MuSiQue | LongBench test | 200 | Adapted LongBench examples, not full original MuSiQue dev |
| MultiFieldQA-en | LongBench test | 150 | LongBench examples |

SCROLLS counts above are published by [TensorFlow Datasets](https://www.tensorflow.org/datasets/catalog/scrolls), whose page is dated 2022-12-06. **These are reference counts, not verified current archive counts.** Count actual rows and unique IDs after acquisition, and report unique question counts. The current NarrativeQA archive is larger than the old TFDS download statistic. LongBench counts are from its official card.

SCROLLS JSONL fields: string `id`, `pid`, `input`, `output`; raw QuALITY records may additionally include `is_hard`. `id` identifies an input/question; `pid` identifies an input-output pair. `input` is the benchmark's formatted question plus document, not an isolated document field. Separate the actual question from the source text using verified task-specific boundaries. Multiple Qasper/NarrativeQA rows can repeat `id` with distinct `output` values. Group by `id`, assert consistent inputs, preserve every reference answer, and generate **one prediction per unique ID**. [Card](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/README.md), [official deduplication](https://github.com/tau-nlp/scrolls/blob/bfc0da0747976418cd0c4b8837db023ea567ba84/evaluator/dataset_evaluator.py).

LongBench JSONL fields: `input` (question), `context` (source documents), `answers` (list), `length`, `dataset`, `language`, `all_classes`, `_id`. The supplied `length` is **English word count**, not this experiment's model-token count. Measure actual tokens with the chosen model. [Schema and construction](https://huggingface.co/datasets/zai-org/LongBench/blob/5e628be450b7e67fb7ae6e201bd6d8f7056f7672/README.md).

## Official evaluation rules

SCROLLS metric files are in the HF dataset repository, **not** the GitHub repository's root `metrics/` directory:

- [metrics/scrolls.py](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/metrics/scrolls.py)
- [metrics/f1.py](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/metrics/f1.py)
- [metrics/exact_match.py](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/metrics/exact_match.py)
- [metrics/rouge.py](https://huggingface.co/datasets/tau/scrolls/blob/927b875150ac8f02262ddd3b078d33a9debc935b/metrics/rouge.py)

| Task | Main metric | Exact aggregation |
|---|---|---|
| QMSum | ROUGE-1, ROUGE-2, ROUGE-L; `scrolls_score` is their geometric mean | Sentence-tokenize then join with newlines; `rouge_score.RougeScorer`, **no stemming**. Best reference per metric per question, then arithmetic mean over questions; geometric mean of the three corpus means. Also emits ROUGE-Lsum. |
| Qasper / NarrativeQA | Normalized token F1 | Lowercase, remove ASCII punctuation, remove English articles a/an/the, collapse whitespace; multiset token overlap; maximum over reference answers; arithmetic mean × 100. No token overlap returns 0, including empty-vs-empty. |
| QuALITY | Normalized exact match | Same normalization; maximum over reference answer texts; arithmetic mean × 100. SCROLLS targets are answer text, not A/B/C/D. If generating choice labels, any mapping back to option text must be fixed and disclosed. |
| LongBench HotpotQA / MuSiQue / MultiFieldQA-en | Normalized token F1 | Same normalizer and token overlap formula; maximum over `answers`; arithmetic mean × 100, rounded to two decimals. |

LongBench implementations: [eval.py](https://github.com/THUDM/LongBench/blob/2e00731f8d0bff23dc4325161044d0ed8af94c1e/LongBench/eval.py), [metrics.py](https://github.com/THUDM/LongBench/blob/2e00731f8d0bff23dc4325161044d0ed8af94c1e/LongBench/metrics.py). Do not call F1 a percentage of fully correct answers. Extra EM can be supplementary, distinct from the official metric.

The official SCROLLS evaluator expects `{id: prediction}` JSON and validation split; checks for missing/redundant IDs. [Instructions](https://github.com/tau-nlp/scrolls/blob/bfc0da0747976418cd0c4b8837db023ea567ba84/evaluator/EVALUATE_DATASET.md). The original commands use older `datasets.load_metric`/script APIs; running a small, fidelity-checked adapter around the frozen metric functions avoids dependence on deprecated loaders. A sampled subset cannot be described as the complete official validation evaluation.

LongBench published prompt templates and generation ceilings: [dataset2prompt.json](https://github.com/THUDM/LongBench/blob/2e00731f8d0bff23dc4325161044d0ed8af94c1e/LongBench/config/dataset2prompt.json), [dataset2maxlen.json](https://github.com/THUDM/LongBench/blob/2e00731f8d0bff23dc4325161044d0ed8af94c1e/LongBench/config/dataset2maxlen.json). HotpotQA/MuSiQue cap is 32 generated tokens; MultiFieldQA-en 64. Same-task prompt and output allowance must be identical across experimental methods. Any changes should be stated as this experiment's protocol.

## Access and license provenance

SCROLLS and LongBench **code** repositories use MIT: [SCROLLS license](https://github.com/tau-nlp/scrolls/blob/bfc0da0747976418cd0c4b8837db023ea567ba84/LICENSE), [LongBench license](https://github.com/THUDM/LongBench/blob/2e00731f8d0bff23dc4325161044d0ed8af94c1e/LICENSE). Their HF metadata does not declare a blanket dataset license. Do not infer that all included books, papers, or source articles are MIT.

| Original resource | Published license information |
|---|---|
| QMSum | [Repository MIT license](https://github.com/Yale-LILY/QMSum/blob/main/LICENSE) |
| Qasper | [Official AllenAI dataset card: CC BY 4.0](https://huggingface.co/datasets/allenai/qasper) |
| NarrativeQA | [Official repo: Apache 2.0](https://github.com/google-deepmind/narrativeqa); downloaded original stories and Wikipedia summaries have their own source provenance |
| QuALITY | [Official site: CC BY 4.0](https://nyu-mll.github.io/quality/); [original records retain per-article license](https://github.com/nyu-mll/quality) |
| HotpotQA | [Official site: CC BY-SA 4.0](https://hotpotqa.github.io/) |
| MuSiQue | [Official repo: CC BY 4.0](https://github.com/StonyBrookNLP/musique) |
| MultiFieldQA-en | Official LongBench card identifies diverse source articles; no separate blanket data license was found in the consulted card. |

Public validation/test labels used here require no submission. SCROLLS hidden test labels are not the requested split. This local evaluation is not a leaderboard submission. Cite benchmark papers and original dataset papers in the report; avoid redistributing full copyrighted source text in report examples.

## Experimental interpretation constraints

These are natural-language document tasks, not source-code projects. A/B code symbols/import edges cannot be applied literally. Document units, headings, proximity or citation relationships are an explicitly adapted variant; label the adaptation and explain how it preserves the intended distinction. Do not fabricate code import graphs or ground-truth evidence annotations that are absent from these distributions.

Report build/index costs separately from per-question retrieval/generation, and count all LLM calls for selectors. Inspect actual model-token counts rather than assuming word counts equal context consumption. **FULL inference is mandatory under the latest direction.** Pass the complete source when it fits. Record an overflow when it does not fit; a head/tail truncation is a distinct truncated baseline, not a complete-source run. Report a common fitting-subset comparison and overflow coverage separately so differing denominators do not create false quality gains.
