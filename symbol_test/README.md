# Symbol Selector Benchmark

이 폴더는 `file outline / symbol index`를 만든 뒤 `memory://symbol/file.py::func_name` 형식으로 접근했을 때, 전체 코드 주입 대비 성능이 언제 좋아지는지 확인하는 테스트 하네스입니다.

## 비교 모드

- `full_repo`: 모든 Python 파일 내용을 한 번에 프롬프트에 넣음
- `full_file`: 타깃 파일 전체만 넣음
- `line_span`: 타깃 함수/메서드의 시작줄-끝줄 span만 넣음
- `symbol_oracle`: 타깃 `memory://symbol/...` URI를 알고 있다고 가정하고 resolver로 본문만 넣음
- `symbol_select`: LLM에 symbol index JSON만 주고 URI를 고르게 한 뒤, resolver로 해당 symbol 본문을 읽어 답하게 함

`symbol_select`는 2회 호출이므로 작은 파일에서는 손해가 날 수 있습니다. 반대로 repo/file이 커지고 관련 함수가 작을수록 prompt eval 비용이 줄어드는지 확인할 수 있습니다.

## 빠른 실행

```bash
cd /Users/oscar/Desktop/4th_grade/SecureCode
uv run python -m symbol_test.symbol_bench.run_benchmark --dry-run --regenerate --scale small
```

실제 Qwen2.5 Coder 7B 모델로 짧게 실행:

```bash
cd /Users/oscar/Desktop/4th_grade/SecureCode
uv run python -m symbol_test.symbol_bench.run_benchmark \
  --regenerate \
  --scale small \
  --limit-cases 1 \
  --modes full_file symbol_oracle symbol_select \
  --ctx-size 8192
```

중간/큰 corpus 비교:

```bash
uv run python -m symbol_test.symbol_bench.run_benchmark --regenerate --scale medium --ctx-size 32768
uv run python -m symbol_test.symbol_bench.run_benchmark --regenerate --scale large --ctx-size 65536
```

결과 요약:

```bash
uv run python -m symbol_test.symbol_bench.analyze_results symbol_test/work/results_small_YYYYMMDD_HHMMSS.jsonl
```

## 산출물

- `symbol_test/work/<scale>/corpus`: synthetic Python corpus
- `symbol_test/work/<scale>/symbol_index.json`: parser가 만든 symbol index
- `symbol_test/work/<scale>/tasks.json`: 정답이 있는 코드 이해 태스크
- `symbol_test/work/results_<scale>_*.jsonl`: 모드별 raw benchmark result

## 해석 기준

성능 향상이 있었다고 보려면 최소한 아래 조건을 같이 봅니다.

- accuracy가 baseline과 같거나 더 높음
- `prompt_chars` 또는 `prompt_tokens`가 감소
- `prompt_eval_ms` 또는 `wall_seconds`가 감소
- `symbol_select`의 URI 선택 정확도가 충분히 높음

예상되는 개선 구간은 `full_repo`나 `full_file`이 큰데 실제 답에 필요한 symbol이 작고, 질문이 함수/클래스명을 명시하거나 symbol index만으로 타깃을 안정적으로 고를 수 있는 경우입니다.
