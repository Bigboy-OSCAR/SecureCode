# Medium Real Benchmark Results

실행일: 2026-04-28

## 실행 조건

- Machine: M3 MacBook Pro
- Backend: llama.cpp / Metal
- Model: Qwen2.5 Coder 7B Instruct GGUF Q5_K_M
- Corpus: `medium`
- Files: 27
- Symbols: 638
- Tasks: 3

## 실행 명령

```bash
uv run python -m symbol_test.symbol_bench.run_benchmark \
  --regenerate \
  --scale medium \
  --modes full_repo full_file line_span symbol_oracle symbol_select \
  --ctx-size 65536 \
  --n-predict 64 \
  --runs 1 \
  --out symbol_test/work/medium_real_results.jsonl
```

`full_repo`는 65k context에서 실패했다.

```text
main: prompt is too long (67188 tokens, max 65532)
```

따라서 `full_repo` 첫 케이스만 131k context와 900초 timeout으로 다시 측정했다.

```bash
uv run python -m symbol_test.symbol_bench.run_benchmark \
  --scale medium \
  --modes full_repo \
  --ctx-size 131072 \
  --n-predict 64 \
  --runs 1 \
  --limit-cases 1 \
  --timeout 900 \
  --out symbol_test/work/medium_fullrepo_131k_onecase_results.jsonl
```

## 최종 요약

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| full_repo | 1 | 1.000 | 612.869 | 67188 | 610521.20 | |
| full_file | 3 | 1.000 | 2.286 | 256 | 803.70 | |
| line_span | 3 | 1.000 | 2.120 | 199 | 650.56 | |
| symbol_oracle | 3 | 1.000 | 2.131 | 199 | 654.80 | |
| symbol_select | 3 | 1.000 | 181.191 | 33871 | 177625.00 | 1.000 |

## full_repo 대비 감소율

| mode | token reduction | wall time reduction |
|---|---:|---:|
| full_file | 99.6% | 99.6% |
| line_span | 99.7% | 99.7% |
| symbol_oracle | 99.7% | 99.7% |
| symbol_select | 49.6% | 70.4% |

## 해석

- `full_repo`는 medium corpus에서도 65k context를 초과했고, 131k context로 첫 케이스를 처리하는 데 약 10분 13초가 걸렸다.
- `symbol_oracle`은 필요한 함수 본문만 읽기 때문에 3개 task 모두 2.1초대에 완료됐다.
- `line_span`과 `symbol_oracle`은 성능이 거의 같다. 차이는 접근 방식이다. `symbol_oracle`은 줄 번호가 아니라 `memory://symbol/file.py::qualname`으로 접근한다.
- `symbol_select`는 3개 task 모두 올바른 symbol을 골랐지만, 전체 symbol index 638개를 매번 LLM에 넣기 때문에 평균 181초가 걸렸다.
- 실제 사용에서는 전체 repo 주입을 피하는 효과는 매우 크지만, naive `symbol_select`는 index 후보를 먼저 줄이지 않으면 여전히 무겁다.

## 결론

성능 향상은 명확하다. 단, 가장 효율적인 구조는 `전체 symbol index -> LLM selector`가 아니라 `파일/키워드/outline 필터링 -> 작은 후보 symbol index -> selector -> read_symbol`이다.
