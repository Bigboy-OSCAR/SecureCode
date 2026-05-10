# Source Pointer 기반 외부 데이터 처리 실험 보고서

실행일: 2026-05-10  
위치: `source_pointer_test/`

## 1. 실험 목적

이번 실험의 목적은 큰 disk 외부 데이터를 LLM context에 직접 넣지 않고도, `source://...` 형태의 source pointer와 extraction tool만으로 필요한 정보를 정확하게 얻을 수 있는지 확인하는 것이다.

참고 논문 `Documents/1_Solving Context Window Overflow in AI Agents.pdf`는 runtime 중 생성된 큰 tool output을 LLM context에 직접 넣지 않고 memory pointer로 관리하는 방식을 제안한다. 이 실험은 그 아이디어를 runtime object가 아니라 disk에 이미 존재하는 외부 source file에도 적용할 수 있는지 검증했다.

검증한 핵심 질문은 다음 두 가지다.

1. 큰 외부 데이터를 LLM context에 직접 넣지 않아도 되는가?
2. pointer만 넘기고 tool이 필요한 부분만 추출하게 했을 때 성능이 유지되거나 좋아지는가?

## 2. 사용한 LLM 모델 및 환경

실험은 로컬 llama.cpp 기반으로 실행했다.

| 항목 | 값 |
|---|---|
| Machine | M3 MacBook Pro |
| Backend | llama.cpp / Metal |
| LLM | Qwen2.5 Coder 7B Instruct GGUF Q5_K_M |
| Model path | `/Users/oscar/llm/models/qwen2.5-coder-7b/qwen2.5-coder-7b-instruct-q5_k_m.gguf` |
| 실행 binary | `/opt/homebrew/bin/llama-completion` |
| Context size | `32768` |
| Generation limit | `--n-predict 128` |
| Temperature | `0` |
| Seed | `1` |

## 3. CLI를 통한 테스트 실행 방법

작업 루트로 이동한다.

```bash
cd /Users/oscar/Desktop/4th_grade/SecureCode
```

Dry-run으로 corpus 생성과 prompt 크기 계산만 확인한다.

```bash
uv run python -m source_pointer_test.source_pointer_bench.run_benchmark \
  --dry-run \
  --regenerate \
  --scale small \
  --out source_pointer_test/work/small_dryrun.jsonl
```

Small scale 실제 모델 실행:

```bash
uv run python -m source_pointer_test.source_pointer_bench.run_benchmark \
  --regenerate \
  --scale small \
  --modes full_source pointer_oracle pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out source_pointer_test/work/small_final_results.jsonl
```

Medium scale 실제 모델 실행:

```bash
uv run python -m source_pointer_test.source_pointer_bench.run_benchmark \
  --regenerate \
  --scale medium \
  --modes full_source pointer_oracle pointer_select \
  --ctx-size 32768 \
  --n-predict 128 \
  --timeout 300 \
  --out source_pointer_test/work/medium_final_results.jsonl
```

결과 요약:

```bash
uv run python -m source_pointer_test.source_pointer_bench.analyze_results \
  source_pointer_test/work/small_final_results.jsonl
```

```bash
uv run python -m source_pointer_test.source_pointer_bench.analyze_results \
  source_pointer_test/work/medium_final_results.jsonl
```

문법 검증:

```bash
uv run python -m compileall source_pointer_test
```

## 4. 테스트를 진행한 방식

테스트는 세 가지 실행 모드를 비교했다.

| mode | 설명 |
|---|---|
| `full_source` | 외부 파일 전체를 LLM prompt에 직접 삽입 |
| `pointer_oracle` | 필요한 extraction tool call을 이미 알고 있다고 가정하고, tool이 추출한 일부만 prompt에 삽입 |
| `pointer_select` | LLM이 작은 source catalog와 tool spec만 보고 tool call을 선택한 뒤, tool output으로 답변 |

Source pointer는 다음 형식을 사용했다.

```text
source://log/logs/checkout_gateway.log
source://doc/docs/ops_runbook.md
source://json/json/tenant_snapshot.json
```

외부 데이터 형식별로 최소 extraction tool을 구현했다.

| tool | 목적 |
|---|---|
| `grep_log(pointer, pattern, before, after)` | 긴 log에서 특정 패턴 주변 line만 추출 |
| `extract_doc_section(pointer, query)` | 긴 문서에서 query와 가장 가까운 section만 추출 |
| `extract_json_field(pointer, path)` | 큰 JSON에서 dot path로 필요한 object 또는 field만 추출 |

테스트 데이터는 synthetic corpus로 생성했다.

| source | small | medium | 질문 |
|---|---:|---:|---|
| checkout gateway log | 80K | 596K | 특정 `request_id`의 `reason`, `retry_after_ms` |
| operations runbook markdown | 12K | 56K | 특정 section의 `max_retries`, `jitter_percent` |
| tenant snapshot JSON | 116K | 752K | 특정 tenant의 `source_pointer_enabled`, `max_context_policy` |

이 구성은 참고 문서의 지적처럼 외부 데이터에 단일 하위 pointer 체계를 억지로 적용하지 않고, 데이터 형식에 맞는 tool을 사용한다는 원칙을 따른다. log는 line 주변 grep이 자연스럽고, document는 section 추출이 자연스럽고, JSON은 key path 추출이 자연스럽다.

## 5. 테스트에 필요한 파일 설명

| 파일 | 역할 |
|---|---|
| `source_pointer_test/README.md` | 빠른 실행 방법과 모드 설명 |
| `source_pointer_test/source_pointer_test.md` | 현재 보고서 |
| `source_pointer_test/RESULTS_source_pointer.md` | 실행 결과 중심 요약 |
| `source_pointer_test/source_pointer_bench/__init__.py` | Python package marker |
| `source_pointer_test/source_pointer_bench/make_corpus.py` | synthetic 외부 source corpus 생성 |
| `source_pointer_test/source_pointer_bench/source_tools.py` | source pointer resolver와 extraction tool 구현 |
| `source_pointer_test/source_pointer_bench/run_benchmark.py` | llama.cpp 호출, mode별 prompt 구성, 결과 JSONL 저장 |
| `source_pointer_test/source_pointer_bench/analyze_results.py` | JSONL 결과를 mode별 accuracy, token, time 기준으로 요약 |
| `source_pointer_test/work/small/manifest.json` | small corpus의 source pointer catalog |
| `source_pointer_test/work/small/tasks.json` | small corpus의 질문과 기대 정답 |
| `source_pointer_test/work/medium/manifest.json` | medium corpus의 source pointer catalog |
| `source_pointer_test/work/medium/tasks.json` | medium corpus의 질문과 기대 정답 |
| `source_pointer_test/work/small_final_results.jsonl` | small 실제 실행 raw result |
| `source_pointer_test/work/medium_final_results.jsonl` | medium 실제 실행 raw result |

`manifest.json`은 각 source file의 pointer, kind, byte size, 사용 가능한 tool, 검색 hint를 담는다. `tasks.json`은 질문, target pointer, 사용할 tool call, 기대 substring을 담는다.

## 6. 테스트 결과 및 설명

### Small 결과

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| `full_source` | 3 | 0.333 | 54.401 | 18,369 | 79,517.68 | |
| `pointer_oracle` | 3 | 1.000 | 2.472 | 286 | 866.69 | 1.000 |
| `pointer_select` | 3 | 1.000 | 6.430 | 778 | 2,370.58 | 1.000 |

Small에서 `full_source`는 log task에서 context 초과로 실패했다.

```text
main: prompt is too long (35923 tokens, max 32764)
```

JSON task는 context 안에는 들어갔지만 32,616 prompt tokens를 사용했고 152.94초가 걸렸으며, `pointer-first`가 아니라 distractor 값인 `pointer-preferred`를 답해 실패했다. 즉 전체 source를 넣는 방식은 context overflow뿐 아니라 긴 context 안에서 관련 위치를 놓치는 문제도 보였다.

반면 `pointer_oracle`과 `pointer_select`는 3개 task 모두 성공했다. `pointer_select`는 selector 호출이 추가되므로 `pointer_oracle`보다 느리지만, 전체 source 주입보다 훨씬 작고 안정적이었다.

### Medium 결과

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| `full_source` | 3 | 0.333 | 22.117 | 120,208 | 62,090.66 | |
| `pointer_oracle` | 3 | 1.000 | 2.443 | 286 | 871.16 | 1.000 |
| `pointer_select` | 3 | 1.000 | 6.423 | 780 | 2,355.91 | 1.000 |

Medium에서는 `full_source`가 3개 중 2개에서 context 초과로 실패했다.

```text
log:  prompt is too long (275609 tokens, max 32764)
JSON: prompt is too long (216172 tokens, max 32764)
```

문서 task는 성공했지만 16,770 prompt tokens와 63.68초가 필요했다. 같은 질문을 `pointer_oracle`로 처리하면 217 prompt tokens, 2.12초로 끝났다.

결과적으로 pointer 방식은 source file 크기가 커져도 prompt token이 거의 변하지 않았다.

| mode | small prompt tokens | medium prompt tokens |
|---|---:|---:|
| `pointer_oracle` | 286 | 286 |
| `pointer_select` | 778 | 780 |

이는 source pointer 방식의 장점이 단순 token 절약이 아니라, 외부 source 크기와 LLM context 크기를 분리하는 데 있음을 보여준다.

## 7. 코드 어시스턴스에 적용시킬 방법

코드 어시스턴스에 적용할 때는 source pointer를 단독 기능으로 보지 않고, agent의 데이터 접근 계층으로 넣는 것이 적절하다.

기본 흐름은 다음과 같다.

```text
사용자 요청
-> Agent가 필요한 외부 데이터 유형 판단
-> source pointer catalog 조회
-> 적절한 extraction tool 선택
-> tool이 pointer를 resolve하고 필요한 부분만 추출
-> LLM은 추출된 작은 context로 답변 또는 코드 수정 계획 생성
```

예를 들어 사용자가 “운영 로그에서 결제 실패 원인을 찾아 코드 수정해줘”라고 요청하면, 코드 어시스턴스는 로그 전체를 context에 넣지 않는다.

```text
source://log/prod/checkout.log
-> grep_log(pattern="request_id=...")
-> 관련 line 3~10개만 LLM에 전달
-> 관련 코드 symbol selector로 결제 처리 함수 선택
-> read_symbol 또는 read_span
-> patch 생성
```

내부 코드 접근에는 기존 `symbol_test`의 `memory://symbol/file.py::qualname` 구조를 사용하고, 외부 데이터 접근에는 `source://...` 구조를 사용하면 된다.

```text
코드 내부 데이터: memory://symbol/services/payment.py::authorize_payment
외부 disk 데이터: source://log/logs/checkout_gateway.log
```

이렇게 분리하면 코드 어시스턴트는 “코드 구조 접근”과 “외부 증거 자료 접근”을 모두 pointer 기반으로 다룰 수 있다.

## 8. 앞으로 발전시킬 방향 및 실현 가능성

이번 실험으로 source pointer 방식의 실현 가능성은 확인됐다. 다만 실제 코드 어시스턴트에 넣기 위해서는 다음 발전이 필요하다.

### 8.1 실제 파일 형식 확장

현재는 log, markdown document, JSON만 테스트했다. 실제 환경에서는 PDF, CSV, HTML, DB result, test output, build log 등이 필요하다.

우선순위는 다음과 같다.

1. `grep_log`: build/test/runtime log 처리
2. `extract_doc_section`: markdown, text, PDF 추출 텍스트 처리
3. `extract_json_field`: API result, config, structured report 처리
4. `extract_csv_rows`: 조건 기반 row/column 추출
5. `extract_html_section`: selector 또는 heading 기반 HTML 추출

### 8.2 Selector 안정성 개선

`pointer_select`는 작은 catalog에서는 성공했지만, selector prompt와 tool 인자 형식에 영향을 받았다. 실제 적용에서는 LLM이 자유 형식으로 path를 만들게 하기보다, 다음 방식을 섞는 것이 안정적이다.

- source kind별 tool 후보 제한
- catalog hint 강화
- JSON path 자동 보정
- selector output schema 검증
- 실패 시 broader extraction으로 fallback

### 8.3 Code pointer와 source pointer 결합

실제 코드 어시스턴스 문제는 외부 데이터만 읽는 것으로 끝나지 않는다. 외부 데이터에서 증거를 찾고, 관련 코드를 찾아 수정해야 한다.

권장 구조는 다음과 같다.

```text
source pointer로 외부 증거 추출
-> symbol index로 관련 코드 후보 검색
-> read_symbol_bundle로 관련 함수와 helper 확장
-> LLM이 원인 분석 및 patch 생성
-> test 실행 결과도 source pointer 또는 runtime pointer로 재사용
```

### 8.4 Runtime pointer와의 통합

논문의 runtime pointer 방식은 큰 tool output을 memory store에 넣고 pointer를 반환한다. source pointer는 disk source를 pointer로 참조한다. 둘을 통합하면 다음 구조가 된다.

| pointer type | 대상 | 예시 |
|---|---|---|
| source pointer | disk에 이미 존재하는 외부 파일 | `source://log/prod.log` |
| code pointer | repo 내부 code span 또는 symbol | `memory://symbol/file.py::func` |
| runtime pointer | tool 실행 중 생성된 큰 결과 | `runtime://tool/result-id/path` |

이 구조는 실현 가능성이 높다. 이미 source pointer는 이번 실험에서 동작했고, code pointer는 기존 `symbol_test`에서 검증됐다. 남은 과제는 runtime object store와 mirrored tool wrapper를 추가해 큰 중간 결과를 같은 방식으로 관리하는 것이다.

## 9. 결론

Source pointer 방식은 disk 외부 데이터 처리에 유효하다. 큰 외부 파일을 LLM context에 직접 넣는 방식은 context overflow, 긴 prompt eval, 긴 context 내부 distractor로 인한 오답 위험이 있었다. 반면 `source://...` pointer와 최소 extraction tool을 사용하면 필요한 부분만 LLM에 전달할 수 있고, 정확도와 실행 시간이 모두 개선됐다.

따라서 코드 어시스턴스에 적용할 때는 외부 데이터를 raw context로 넣는 방식을 기본값으로 두지 말고, source pointer catalog와 format-specific extraction tool을 통해 필요한 증거만 읽는 구조로 설계하는 것이 적절하다.

