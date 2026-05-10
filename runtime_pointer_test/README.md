# Runtime Pointer Benchmark

이 폴더는 큰 runtime tool output을 LLM context에 직접 넣는 방식과, `runtime://...` memory pointer만 넘긴 뒤 mirrored extraction tool이 필요한 부분만 읽는 방식을 비교하는 테스트 하네스입니다.

참고 논문 `Documents/1_Solving Context Window Overflow in AI Agents.pdf`의 핵심 구조를 따릅니다.

- 큰 tool output은 runtime memory store에 저장한다.
- LLM에는 raw output 대신 짧은 memory pointer와 access instruction만 전달한다.
- 후속 tool은 pointer를 받아 실제 값을 resolve한 뒤 필요한 부분만 처리한다.

## 비교 모드

- `full_runtime`: runtime tool output 전체를 프롬프트에 직접 삽입
- `runtime_pointer_oracle`: 정답 task에 필요한 extraction tool call을 알고 있다고 가정하고, tool output만 프롬프트에 삽입
- `runtime_pointer_select`: LLM에 작은 runtime memory catalog와 tool spec만 주고 tool call을 고르게 한 뒤, tool output으로 답하게 함

## Runtime Pointer Tool

- `grep_runtime_log(runtime://log/..., pattern, before, after)`
- `extract_runtime_doc_section(runtime://doc/..., query)`
- `extract_runtime_json_path(runtime://json/..., path)`

## 빠른 실행

```bash
cd /Users/oscar/Desktop/4th_grade/SecureCode
uv run python -m runtime_pointer_test.runtime_pointer_bench.run_benchmark --dry-run --scale small
```

실제 모델 실행:

```bash
uv run python -m runtime_pointer_test.runtime_pointer_bench.run_benchmark \
  --scale small \
  --modes full_runtime runtime_pointer_oracle runtime_pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out runtime_pointer_test/work/small_final_results.jsonl
```

중간 규모:

```bash
uv run python -m runtime_pointer_test.runtime_pointer_bench.run_benchmark \
  --scale medium \
  --modes full_runtime runtime_pointer_oracle runtime_pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out runtime_pointer_test/work/medium_final_results.jsonl
```

결과 요약:

```bash
uv run python -m runtime_pointer_test.runtime_pointer_bench.analyze_results runtime_pointer_test/work/small_final_results.jsonl
```
