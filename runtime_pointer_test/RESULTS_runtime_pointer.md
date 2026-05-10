# Runtime Pointer Benchmark Results

실행일: 2026-05-11

## 목적

`Documents/1_Solving Context Window Overflow in AI Agents.pdf`의 runtime pointer 방식은 큰 tool output을 LLM context에 직접 넣지 않고, runtime memory store에 저장한 뒤 `memory pointer`를 mirrored tool에 넘긴다.

이번 실험은 같은 구조를 로컬 synthetic runtime output에 적용해서 다음 두 질문을 확인했다.

1. 큰 runtime 데이터를 LLM context에 직접 넣지 않아도 되는가?
2. pointer만 넘기고 tool이 필요한 부분만 추출하게 했을 때 성능이 유지되거나 좋아지는가?

논문에서 확인한 기준은 다음과 같다.

- 큰 tool output은 context 밖 runtime memory에 저장한다.
- 각 tool은 pointer/raw value를 구분하고, pointer면 실제 값을 resolve한 뒤 원래 tool을 실행하는 mirrored wrapper를 둔다.
- final answer가 필요할 때만 memory에서 값을 회수한다.
- 논문 실험에서는 conventional workflow가 불가능한 케이스가 있었고, SDS 실험에서는 pointer 방식이 token과 실행 시간을 줄였다.

## 비교 모드

| mode | 설명 |
|---|---|
| `full_runtime` | runtime tool output 전체를 LLM prompt에 직접 삽입 |
| `runtime_pointer_oracle` | 필요한 mirrored extraction tool call을 알고 있다고 가정하고, tool이 추출한 일부만 prompt에 삽입 |
| `runtime_pointer_select` | LLM이 작은 runtime memory catalog와 tool spec만 보고 tool call을 선택한 뒤, tool output으로 답변 |

## Runtime Pointer Tool

| tool | 목적 |
|---|---|
| `grep_runtime_log(pointer, pattern, before, after)` | runtime log string에서 특정 패턴 주변 line만 추출 |
| `extract_runtime_doc_section(pointer, query)` | runtime markdown string에서 section만 추출 |
| `extract_runtime_json_path(pointer, path)` | runtime JSON/dict에서 dot path로 필요한 object 또는 field만 추출 |

## 데이터와 질문

Synthetic runtime producer를 실행해 큰 중간 결과를 만든 뒤, process-local `RuntimeStore`에 저장했다.

| runtime output | small raw chars | medium raw chars | 질문 |
|---|---:|---:|---|
| checkout trace string | 79,071 | 608,116 | 특정 `request_id`의 `reason`, `retry_after_ms` |
| operations runbook string | 9,007 | 59,599 | 특정 section의 `max_retries`, `jitter_percent` |
| tenant snapshot dict | 134,023 | 891,159 | 특정 tenant의 `runtime_pointer_enabled`, `max_context_policy` |

각 task는 먼저 runtime producer를 실행한다. `full_runtime`은 그 output을 그대로 prompt에 넣고, pointer 모드는 다음 형식의 pointer만 prompt/tool에 넘긴다.

```text
runtime://log/collect_checkout_trace/0001
runtime://doc/compile_operations_runbook/0001
runtime://json/fetch_tenant_snapshot/0001
```

## 실행 명령

```bash
uv run python -m runtime_pointer_test.runtime_pointer_bench.run_benchmark \
  --scale small \
  --modes full_runtime runtime_pointer_oracle runtime_pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out runtime_pointer_test/work/small_final_results.jsonl
```

```bash
uv run python -m runtime_pointer_test.runtime_pointer_bench.run_benchmark \
  --scale medium \
  --modes full_runtime runtime_pointer_oracle runtime_pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out runtime_pointer_test/work/medium_final_results.jsonl
```

문법 검증:

```bash
uv run python -m compileall runtime_pointer_test
```

## Small 결과

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy | mean tool output chars |
|---|---:|---:|---:|---:|---:|---:|---:|
| `full_runtime` | 3 | 0.333 | 4.961 | 18,785 | 8,940.97 | | 0 |
| `runtime_pointer_oracle` | 3 | 1.000 | 2.768 | 311 | 1,021.06 | 1.000 | 365 |
| `runtime_pointer_select` | 3 | 1.000 | 7.050 | 756 | 2,390.06 | 1.000 | 430 |

`full_runtime` 세부 결과:

| task | result |
|---|---|
| runtime log | context 초과 실패: 35,932 tokens > 32,764 max |
| runtime doc | 성공: 2,872 prompt tokens, 10.65s |
| runtime JSON | context 초과 실패: 35,996 tokens > 32,764 max |

Small에서 `runtime_pointer_oracle`은 전체 주입 대비 prompt chars를 98.7% 줄였고, `runtime_pointer_select`는 96.2% 줄였다. 다만 `runtime_pointer_select`는 selector와 answer로 LLM을 두 번 호출하므로, context overflow가 빨리 실패한 baseline까지 평균에 넣으면 wall time이 더 길게 보인다. 성공 가능한 doc 케이스만 보면 `full_runtime` 10.65s 대비 `runtime_pointer_select` 6.22s, oracle 2.11s였다.

## Medium 결과

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy | mean tool output chars |
|---|---:|---:|---:|---:|---:|---:|---:|
| `full_runtime` | 3 | 0.333 | 26.270 | 131,136 | 73,757.09 | | 0 |
| `runtime_pointer_oracle` | 3 | 1.000 | 2.610 | 311 | 988.99 | 1.000 | 365 |
| `runtime_pointer_select` | 3 | 1.000 | 6.891 | 757 | 2,361.86 | 1.000 | 430 |

`full_runtime` 세부 결과:

| task | result |
|---|---|
| runtime log | context 초과 실패: 275,619 tokens > 32,764 max |
| runtime doc | 성공: 18,377 prompt tokens, 75.64s |
| runtime JSON | context 초과 실패: 238,593 tokens > 32,764 max |

Medium에서 pointer 방식은 전체 주입 대비 prompt chars를 크게 줄였다.

| mode | prompt char reduction | wall time reduction |
|---|---:|---:|
| `runtime_pointer_oracle` | 99.8% | 90.1% |
| `runtime_pointer_select` | 99.5% | 73.8% |

또한 데이터 크기가 small에서 medium으로 커져도 pointer 모드의 prompt token은 거의 변하지 않았다.

| mode | small prompt tokens | medium prompt tokens |
|---|---:|---:|
| `runtime_pointer_oracle` | 311 | 311 |
| `runtime_pointer_select` | 756 | 757 |

## 해석

1. 큰 runtime 데이터를 LLM context에 직접 넣지 않아도 되는가?

가능하다. runtime log, document, JSON 모두 `runtime://...` pointer와 mirrored extraction tool만으로 정답을 만들 수 있었다. Medium log/JSON처럼 raw runtime output이 context window를 초과하는 경우에도 pointer 방식은 정상 실행됐다.

2. pointer만 넘기고 tool이 필요한 부분만 추출하면 성능이 유지되거나 좋아지는가?

이번 실험에서는 정확도는 유지가 아니라 개선됐다. `full_runtime`은 small/medium 모두 1/3만 성공했고, 두 pointer 모드는 모두 3/3 성공했다. 실행 시간도 medium 기준 `runtime_pointer_oracle`은 26.27s -> 2.61s, `runtime_pointer_select`는 26.27s -> 6.89s로 줄었다. 이 평균은 context overflow가 빠르게 실패한 baseline을 포함하므로, 실제 성공 workflow 기준 개선 폭은 더 크다. 예를 들어 medium doc은 75.64s -> 2.11s oracle, 6.22s select로 줄었다.

3. source pointer 실험을 runtime pointer에도 적용할 수 있는가?

적용 가능하다. 차이는 resolver의 위치다.

| source pointer | runtime pointer |
|---|---|
| disk source resolver가 file을 읽음 | runtime memory store가 tool output을 보관 |
| `source://...`가 기존 외부 데이터 위치를 가리킴 | `runtime://...`가 실행 중 생성된 중간 결과를 가리킴 |
| format-specific extraction tool이 필요 | mirrored tool wrapper와 extraction tool이 필요 |

핵심 흐름은 동일하다.

```text
큰 데이터 생성/존재
-> pointer catalog만 LLM에 노출
-> LLM 또는 planner가 extraction tool 선택
-> tool이 pointer를 resolve하고 필요한 부분만 추출
-> LLM은 작은 context로 답변
```

## 한계

- Synthetic runtime output 기준이다. 실제 tool output에서는 extractor 품질과 schema 안정성이 정확도에 직접 영향을 준다.
- `runtime_pointer_select`는 LLM 호출이 2회라 매우 작은 데이터에서는 oracle보다 느리다.
- JSON selector가 `tenants.northwind-prod.security.runtime_pointer_enabled,max_context_policy`처럼 comma-separated sibling field path를 만들었다. extractor가 sibling key selection을 허용해서 정답은 맞았지만, 실제 시스템에서는 selector output schema 검증과 path normalization을 넣는 것이 좋다.
- `full_runtime` overflow 케이스는 prompt eval까지 도달하지 못하므로 평균 prompt eval time은 성공 케이스 중심으로만 해석해야 한다.

## 결론

Runtime pointer 방식은 이번 실험 조건에서 유효하다. 큰 runtime tool output을 LLM context에 직접 넣는 방식은 context overflow로 실패하거나, context 안에 들어가도 prompt eval 시간이 크게 증가했다. 반면 `runtime://...` pointer와 mirrored extraction tool 조합은 데이터 크기와 LLM context 크기를 분리했고, 정확도를 3/3으로 유지하면서 prompt token과 실행 시간을 크게 줄였다.
