# Source Pointer Benchmark

이 폴더는 큰 외부 disk 데이터를 LLM context에 직접 넣는 방식과, `source://...` 포인터만 넘긴 뒤 형식별 tool이 필요한 부분만 추출하는 방식을 비교하는 테스트 하네스입니다.

## 비교 모드

- `full_source`: 외부 파일 전체를 프롬프트에 넣음
- `pointer_oracle`: 정답 task에 필요한 extraction tool call을 알고 있다고 가정하고, tool output만 프롬프트에 넣음
- `pointer_select`: LLM에 작은 source catalog와 tool spec만 주고 tool call을 고르게 한 뒤, tool output으로 답하게 함

## Source Pointer Tool

- `grep_log(source://log/..., pattern, before, after)`
- `extract_doc_section(source://doc/..., query)`
- `extract_json_field(source://json/..., path)`

## 빠른 실행

```bash
cd /Users/oscar/Desktop/4th_grade/SecureCode
uv run python -m source_pointer_test.source_pointer_bench.run_benchmark --dry-run --regenerate --scale small
```

실제 모델 실행:

```bash
uv run python -m source_pointer_test.source_pointer_bench.run_benchmark \
  --regenerate \
  --scale small \
  --modes full_source pointer_oracle pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --out source_pointer_test/work/small_results.jsonl
```

중간 규모에서 context overflow 여부까지 확인:

```bash
uv run python -m source_pointer_test.source_pointer_bench.run_benchmark \
  --regenerate \
  --scale medium \
  --modes full_source pointer_oracle pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out source_pointer_test/work/medium_results.jsonl
```

결과 요약:

```bash
uv run python -m source_pointer_test.source_pointer_bench.analyze_results source_pointer_test/work/small_results.jsonl
```
