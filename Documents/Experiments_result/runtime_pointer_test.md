# Runtime Pointer 기반 Runtime 데이터 처리 실험 보고서

실행일: 2026-05-11  
위치: `runtime_pointer_test/`

## 1. 실험 목적

이번 실험의 목적은 큰 runtime 데이터를 LLM context에 직접 넣지 않고도, `runtime://...` 형태의 runtime pointer와 mirrored extraction tool만으로 필요한 정보를 정확하게 얻을 수 있는지 확인하는 것이다.

참고 논문 `Documents/1_Solving Context Window Overflow in AI Agents.pdf`는 tool 실행 중 생성되는 큰 output을 LLM context에 그대로 넣지 않고 runtime memory에 저장한 뒤, LLM에는 짧은 memory pointer만 전달하는 방식을 제안한다. 이후 후속 tool은 pointer를 resolve해서 원래 tool이 기대하는 raw value로 바꾼 뒤 처리한다.

검증한 핵심 질문은 다음 두 가지다.

1. 큰 runtime 데이터를 LLM context에 직접 넣지 않아도 되는가?
2. pointer만 넘기고 tool이 필요한 부분만 추출하게 했을 때 성능이 유지되거나 좋아지는가?

기존 `source_pointer_test`는 disk에 존재하는 외부 데이터를 `source://...` pointer로 다루는 실험이었다. 이번 실험은 같은 아이디어를 실행 중 생성된 tool output, 즉 runtime object에 적용했다.

## 2. 사용한 LLM 모델 및 환경

실험은 로컬 llama.cpp 기반으로 실행했다.

| 항목 | 값 |
|---|---|
| Machine | M3 MacBook Pro |
| Backend | llama.cpp / Metal |
| LLM | Qwen2.5 Coder 7B Instruct GGUF Q5_K_M |
| Model path | `/Users/oscar/llm/models/qwen2.5-coder-7b/qwen2.5-coder-7b-instruct-q5_k_m.gguf` |
| 실행 binary | `llama-completion` |
| 실행 wrapper | `uv run python -m runtime_pointer_test.runtime_pointer_bench.run_benchmark` |
| Context size | `32768` |
| Generation limit | `--n-predict 128` |
| Temperature | `0` |
| Seed | `1` |
| Timeout | `300s` |

문법 검증은 다음 명령으로 수행했다.

```bash
uv run python -m compileall runtime_pointer_test
```

## 3. 테스트를 진행한 방식

테스트는 runtime producer가 큰 중간 결과를 만든 뒤, 그 결과를 처리하는 방식별 성능을 비교했다.

| mode | 설명 |
|---|---|
| `full_runtime` | runtime tool output 전체를 LLM prompt에 직접 삽입 |
| `runtime_pointer_oracle` | 필요한 mirrored extraction tool call을 이미 알고 있다고 가정하고, tool이 추출한 일부만 prompt에 삽입 |
| `runtime_pointer_select` | LLM이 작은 runtime memory catalog와 tool spec만 보고 tool call을 선택한 뒤, tool output으로 답변 |

Runtime pointer는 다음 형식을 사용했다.

```text
runtime://log/collect_checkout_trace/0001
runtime://doc/compile_operations_runbook/0001
runtime://json/fetch_tenant_snapshot/0001
```

Runtime object는 process-local `RuntimeStore`에 저장했다. store는 pointer, producer 이름, kind, 사용 가능한 tool, hint, raw value를 보관한다. 후속 tool은 pointer를 입력받으면 store에서 raw value를 resolve하고, 필요한 부분만 추출한다.

사용한 mirrored extraction tool은 다음과 같다.

| tool | 목적 |
|---|---|
| `grep_runtime_log(pointer, pattern, before, after)` | runtime log string에서 특정 패턴 주변 line만 추출 |
| `extract_runtime_doc_section(pointer, query)` | runtime markdown string에서 query와 가장 가까운 section만 추출 |
| `extract_runtime_json_path(pointer, path)` | runtime JSON/dict에서 dot path로 필요한 object 또는 field만 추출 |

Synthetic runtime producer와 질문은 다음과 같이 구성했다.

| runtime output | small raw chars | medium raw chars | 질문 |
|---|---:|---:|---|
| checkout trace string | 79,071 | 608,116 | 특정 `request_id`의 `reason`, `retry_after_ms` |
| operations runbook string | 9,007 | 59,599 | 특정 section의 `max_retries`, `jitter_percent` |
| tenant snapshot dict | 134,023 | 891,159 | 특정 tenant의 `runtime_pointer_enabled`, `max_context_policy` |

테스트 흐름은 다음과 같다.

```text
runtime producer 실행
-> 큰 runtime output 생성
-> RuntimeStore에 저장하고 runtime:// pointer 발급
-> full_runtime은 raw output 전체를 prompt에 삽입
-> pointer mode는 pointer와 tool output 일부만 prompt에 삽입
-> LLM 답변이 expected_substrings를 모두 포함하는지 평가
```

`runtime_pointer_select`는 두 번의 LLM 호출로 평가했다.

```text
1차 호출: question + 작은 runtime memory catalog + tool spec -> tool call JSON 선택
2차 호출: selected tool call + extracted content -> 최종 답변
```

측정 지표는 accuracy, wall time, prompt chars, prompt tokens, prompt eval ms, selector accuracy, tool output chars다.

Small 실행 명령:

```bash
uv run python -m runtime_pointer_test.runtime_pointer_bench.run_benchmark \
  --scale small \
  --modes full_runtime runtime_pointer_oracle runtime_pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out runtime_pointer_test/work/small_final_results.jsonl
```

Medium 실행 명령:

```bash
uv run python -m runtime_pointer_test.runtime_pointer_bench.run_benchmark \
  --scale medium \
  --modes full_runtime runtime_pointer_oracle runtime_pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out runtime_pointer_test/work/medium_final_results.jsonl
```

결과 요약 명령:

```bash
uv run python -m runtime_pointer_test.runtime_pointer_bench.analyze_results \
  runtime_pointer_test/work/small_final_results.jsonl
```

```bash
uv run python -m runtime_pointer_test.runtime_pointer_bench.analyze_results \
  runtime_pointer_test/work/medium_final_results.jsonl
```

## 4. 테스트에 필요한 파일 설명

| 파일 | 역할 |
|---|---|
| `runtime_pointer_test/README.md` | 빠른 실행 방법, 비교 모드, runtime pointer tool 설명 |
| `runtime_pointer_test/runtime_pointer_test.md` | 현재 보고서 |
| `runtime_pointer_test/RESULTS_runtime_pointer.md` | 실행 결과 중심 요약, 해석, 한계 정리 |
| `runtime_pointer_test/.gitignore` | dry-run 결과와 Python cache 제외 |
| `runtime_pointer_test/runtime_pointer_bench/__init__.py` | Python package marker |
| `runtime_pointer_test/runtime_pointer_bench/make_runtime_data.py` | synthetic runtime producer와 task 정의 |
| `runtime_pointer_test/runtime_pointer_bench/runtime_tools.py` | `RuntimeStore`, pointer resolver, mirrored extraction tool 구현 |
| `runtime_pointer_test/runtime_pointer_bench/run_benchmark.py` | llama.cpp 호출, mode별 prompt 구성, 결과 JSONL 저장 |
| `runtime_pointer_test/runtime_pointer_bench/analyze_results.py` | JSONL 결과를 mode별 accuracy, token, time 기준으로 요약 |
| `runtime_pointer_test/work/small_final_results.jsonl` | small 실제 실행 raw result |
| `runtime_pointer_test/work/medium_final_results.jsonl` | medium 실제 실행 raw result |

`make_runtime_data.py`는 disk file을 만들지 않는다. 대신 `collect_checkout_trace`, `compile_operations_runbook`, `fetch_tenant_snapshot` 같은 producer 함수가 실행 중 큰 값을 반환한다. 이 점이 `source_pointer_test`와의 핵심 차이다.

`runtime_tools.py`의 `RuntimeStore`는 이번 실험에서 process-local memory store로 동작한다. 실제 agent 시스템에 붙일 때는 session 단위 lifecycle, eviction, 권한 검사, persistence 여부를 추가해야 한다.

## 5. 테스트 결과 및 결과에 대한 설명

### Small 결과

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

Small에서도 raw runtime output을 그대로 넣는 방식은 log와 JSON에서 context window를 초과했다. 문서 task는 context 안에 들어갔지만, pointer 방식보다 훨씬 많은 prompt token과 시간이 필요했다.

성공 가능한 doc task만 비교하면 다음과 같다.

| mode | doc wall s | doc prompt tokens |
|---|---:|---:|
| `full_runtime` | 10.652 | 2,872 |
| `runtime_pointer_oracle` | 2.113 | 239 |
| `runtime_pointer_select` | 6.221 | 641 |

즉 selector 호출이 추가되는 `runtime_pointer_select`도 raw output 전체를 넣는 것보다 빨랐다.

### Medium 결과

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

Medium에서 pointer 방식은 전체 주입 대비 prompt chars와 wall time을 크게 줄였다.

| mode | prompt char reduction | wall time reduction |
|---|---:|---:|
| `runtime_pointer_oracle` | 99.8% | 90.1% |
| `runtime_pointer_select` | 99.5% | 73.8% |

또한 데이터 크기가 small에서 medium으로 커져도 pointer mode의 prompt token은 거의 변하지 않았다.

| mode | small prompt tokens | medium prompt tokens |
|---|---:|---:|
| `runtime_pointer_oracle` | 311 | 311 |
| `runtime_pointer_select` | 756 | 757 |

이는 runtime pointer 방식의 핵심 장점이 단순 token 절약이 아니라, runtime object 크기와 LLM context 크기를 분리하는 데 있음을 보여준다.

## 6. RESULTS_runtime_pointer.md의 정리된 내용

### 해석

1. 큰 runtime 데이터를 LLM context에 직접 넣지 않아도 되는가?

가능하다. runtime log, document, JSON 모두 `runtime://...` pointer와 mirrored extraction tool만으로 정답을 만들 수 있었다. Medium log/JSON처럼 raw runtime output이 context window를 초과하는 경우에도 pointer 방식은 정상 실행됐다.

2. pointer만 넘기고 tool이 필요한 부분만 추출하면 성능이 유지되거나 좋아지는가?

이번 실험에서는 정확도는 유지가 아니라 개선됐다. `full_runtime`은 small/medium 모두 1/3만 성공했고, 두 pointer 모드는 모두 3/3 성공했다. 실행 시간도 medium 기준 `runtime_pointer_oracle`은 26.27s에서 2.61s로, `runtime_pointer_select`는 26.27s에서 6.89s로 줄었다. 이 평균은 context overflow가 빠르게 실패한 baseline을 포함하므로, 실제 성공 workflow 기준 개선 폭은 더 크다. 예를 들어 medium doc은 75.64s에서 oracle 2.11s, select 6.22s로 줄었다.

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

### 한계

- Synthetic runtime output 기준이다. 실제 tool output에서는 extractor 품질과 schema 안정성이 정확도에 직접 영향을 준다.
- `runtime_pointer_select`는 LLM 호출이 2회라 매우 작은 데이터에서는 oracle보다 느릴 수 있다.
- JSON selector가 `tenants.northwind-prod.security.runtime_pointer_enabled,max_context_policy`처럼 comma-separated sibling field path를 만들었다. extractor가 sibling key selection을 허용해서 정답은 맞았지만, 실제 시스템에서는 selector output schema 검증과 path normalization을 넣는 것이 좋다.
- `full_runtime` overflow 케이스는 prompt eval까지 도달하지 못하므로 평균 prompt eval time은 성공 케이스 중심으로만 해석해야 한다.

## 7. 코드 어시스턴스에 적용시킬 방법

코드 어시스턴스에 적용할 때는 runtime pointer를 agent의 tool output 처리 계층에 넣는 것이 적절하다. 핵심은 “큰 중간 결과를 message history에 넣지 않는다”는 규칙이다.

기본 흐름은 다음과 같다.

```text
사용자 요청
-> Agent가 tool 실행
-> tool output이 threshold보다 크면 RuntimeStore에 저장
-> LLM에는 runtime:// pointer와 짧은 summary/access instruction만 전달
-> 후속 mirrored tool이 pointer를 resolve
-> 필요한 부분만 추출하거나 다른 tool input으로 전달
-> 최종 답변에 필요한 경우에만 retrieve tool로 값을 회수
```

예를 들어 사용자가 “테스트 실패 로그를 보고 원인과 수정 위치를 찾아줘”라고 요청하면, 코드 어시스턴트는 전체 테스트 로그를 context에 넣지 않는다.

```text
run_tests()
-> output이 큼
-> runtime://log/run_tests/0001 저장
-> grep_runtime_log(pattern="FAILED|Traceback|AssertionError")
-> 관련 line만 LLM에 전달
-> symbol index로 관련 함수 선택
-> read_symbol 또는 read_span
-> patch 생성
```

코드 어시스턴스에서는 pointer 계층을 세 가지로 분리하는 것이 좋다.

| pointer | 대상 | 예시 |
|---|---|---|
| code pointer | repo 내부 코드 구조 | `memory://symbol/services/payment.py::authorize_payment` |
| source pointer | disk에 이미 존재하는 외부 자료 | `source://log/prod/checkout.log` |
| runtime pointer | 실행 중 생성된 tool output | `runtime://log/run_tests/0001` |

이렇게 분리하면 LLM은 전체 repo, 전체 파일, 전체 로그, 전체 JSON을 직접 들고 있지 않아도 된다. 대신 필요한 시점에 필요한 해상도의 pointer만 resolve한다.

구현상 필요한 컴포넌트는 다음과 같다.

| 컴포넌트 | 역할 |
|---|---|
| `RuntimeStore` | 큰 tool output 저장, pointer 발급, lifecycle 관리 |
| `ResultHandler` | tool output 크기를 검사하고 raw 반환 또는 pointer 반환 결정 |
| `PointerResolver` | pointer를 raw value 또는 하위 path value로 변환 |
| mirrored tool wrapper | 기존 tool 앞뒤에 pointer resolve/store 로직을 추가 |
| retrieval/extraction tool | log grep, JSON path, section extract, table filter 등 작은 context 추출 |
| selector validator | LLM이 고른 tool call JSON을 schema와 allowlist로 검증 |

## 8. 앞으로 발전시킬 방향 및 실현 가능성

이번 실험으로 runtime pointer 방식의 실현 가능성은 확인됐다. 다만 실제 코드 어시스턴트에 넣기 위해서는 다음 발전이 필요하다.

### 8.1 실제 runtime output 형식 확장

현재는 log string, markdown string, JSON/dict만 테스트했다. 실제 코드 어시스턴트에서는 다음 형식이 우선순위가 높다.

1. test/build/runtime log: `grep_runtime_log`, `extract_error_block`
2. JSON/API result: `extract_runtime_json_path`, `filter_json_items`
3. table/CSV result: `filter_runtime_rows`, `select_columns`
4. diff/patch result: `extract_file_diff`, `extract_hunk`
5. stack trace: `extract_stack_frames`, `map_frame_to_symbol`
6. large stdout/stderr stream: streaming chunk index와 pattern search

### 8.2 Selector 안정성 개선

이번 실험의 `runtime_pointer_select`는 3/3 성공했지만, JSON path에서 sibling field를 comma 형태로 합치는 출력이 나왔다. 실제 적용에서는 다음 보강이 필요하다.

- tool별 JSON schema 강제
- pointer allowlist 검증
- path normalization
- 실패 시 broader parent object extraction fallback
- catalog hint 강화
- 후보 pointer가 많은 경우 keyword/filter 단계 선행

### 8.3 RuntimeStore 운영 정책

Runtime pointer는 source pointer와 달리 session 중 생성되는 임시 값이다. 따라서 운영 정책이 중요하다.

- session/job 단위 namespace 분리
- TTL 또는 LRU eviction
- 민감정보 마스킹과 접근 권한 검사
- pointer leak 방지
- memory 사용량 상한
- 필요 시 disk spillover
- final answer 이후 cleanup

### 8.4 Code pointer, source pointer와 결합

가장 현실적인 구조는 세 pointer를 함께 쓰는 것이다.

```text
runtime://log/run_tests/0001
-> 실패 block 추출
-> source://doc/project_test_policy.md
-> 관련 정책 section 추출
-> memory://symbol/app/service.py::target_function
-> 코드 수정
```

이 구조에서는 LLM context가 “전체 데이터 저장소”가 아니라 “현재 reasoning에 필요한 작은 증거 묶음”으로 유지된다.

### 8.5 성능 실험 확장

이번 실험은 3개 task와 2개 scale 기준이다. 다음 단계에서는 다음 조건을 추가해야 한다.

- runs를 5~50회로 늘려 분산 측정
- 더 큰 scale에서 overflow 지점 확인
- 실제 test log, CI log, API response로 평가
- selector 후보가 많은 catalog에서 정확도 측정
- token cost와 wall time을 성공 케이스/실패 케이스로 분리 분석
- threshold별 raw 반환 vs pointer 반환 tradeoff 측정

## 9. 결론

Runtime pointer 방식은 이번 실험 조건에서 유효하다. 큰 runtime tool output을 LLM context에 직접 넣는 방식은 context overflow로 실패하거나, context 안에 들어가도 prompt eval 시간이 크게 증가했다. 반면 `runtime://...` pointer와 mirrored extraction tool 조합은 데이터 크기와 LLM context 크기를 분리했고, 정확도를 3/3으로 유지하면서 prompt token과 실행 시간을 크게 줄였다.

따라서 코드 어시스턴스에서는 큰 test output, build log, API response, static analysis report 등을 message history에 직접 넣는 대신 runtime memory에 저장하고 pointer 기반 tool로 접근하는 구조가 실현 가능하다. 이 방식은 context overflow를 막는 방어책이면서, 정상적으로 context에 들어갈 수 있는 중간 크기 데이터에서도 token cost와 latency를 줄이는 최적화로 사용할 수 있다.
