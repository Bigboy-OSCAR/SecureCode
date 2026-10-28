# Active public document benchmark

Scope: all 7 datasets, A/B/R0/FULL, 7,317 unique questions, 29,268 four-arm results. No subsampling. Protocol and analysis plan were frozen before evaluation.

Actual running handles: inference server exec session 84466; evaluation runner exec session 30578. Download64871, preparation44663, prepared-verifier80143, freezer1948 are complete. Never start another runner solely because a poll times out; inspect the same live session or process first. The runner has an OS lock and atomic query/call records.

The server is local llama-server port8766 with Qwen2.5-Coder-7B-Instruct Q5_K_M, context32768, one slot, model prompt cache disabled. Same source budget1024 for A/B/R0. FULL preserves all supplied context and records overflow without a generation call.

The raw and prepared corpora were audited against every original row: 10,512 reference rows, 7,317 unique questions, 1,053 exact contexts, 1,050 outer-whitespace-normalized source-context clusters. Full raw text and all references remain preserved.

Data preparation encountered three QuALITY options containing internal blank lines; parser fixed and regression-tested before protocol freeze and before benchmark inference. Final successful preparation reused earlier valid context-only assets, so its measured seconds are not a fresh full-build benchmark. This limitation must be stated wherever build time is discussed.

Next: wait for actual run completion, analyze with .venv/bin/python -B analyze_results.py analyze, independently audit payloads/scoring/cost/complete coverage, add the requested new report section with each dataset explained and results shown. Do not mark goal complete while any dataset/method is incomplete.

RAPTOR evaluates only NarrativeQA/QASPER/QuALITY, and is not directly reproduced here; use research_papers.md for exact differences and citations. A/B are explicitly prose adaptations, with extractive12-word previews and literal reference/paragraph-continuation graph; they are not literal Python symbol_index/import evaluations.

## Postprocessing prepared and running

On 2026-10-27, new postprocessing sources were independently reviewed and frozen in postprocess_manifest.json / postprocess_sources/. These are separate from the original frozen inference/analysis protocol. Verifier 15 tests, supervisor 4 safety tests, and report full-render self-test passed. The actual first 28 evaluations (42 model call records) plus the known single transport smoke call passed a read-only payload/token/schema audit; this is not final benchmark verification.

Postprocessing exec session 14219 is running under caffeinate, waiting on runner.lock. It will require exact completed.json and result hash, then run the frozen analyzer, full independent verifier, and guarded report apply. It does not start/retry inference. Parent and child share both OS lock descriptors. Consult postprocess_status.json and postprocess_*.log. If any stage fails it stops with needs_attention, preserving all evidence. Do not start another supervisor just because an observation times out.

Final independent call inventory must include 43,902 evaluation records plus exactly one audited pre-freeze smoke_transport/SMOKE/answer record (43,903 total). FULL-overflow records are noncalls; actual calls and tokens are reported separately. The final report generator only accepts complete verification-bound summaries, adds section 9 and its contents row, and clarifies the historical scope of appendix C; old experiment numbers remain unchanged and all edits are reversible. Main report has not yet been modified.
