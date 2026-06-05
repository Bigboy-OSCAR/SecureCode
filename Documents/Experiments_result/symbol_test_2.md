# Symbol Bundle / Filtered Selector 2차 테스트 보고서

## 1. CLI를 통한 테스트 실행 방법

2차 실험은 기존 `symbol_test` 하네스에 `read_symbol_bundle` 계열 동작을 추가한 뒤, 기존 hard task 3개를 대상으로 실행했다.

기본 위치는 repo root이다.

```bash
cd /Users/oscar/Desktop/4th_grade/SecureCode
```

문법 확인:

```bash
uv run python -m py_compile \
  symbol_test/symbol_bench/indexer.py \
  symbol_test/symbol_bench/run_benchmark.py
```

dry-run으로 prompt 크기와 실행 경로 확인:

```bash
uv run python -m symbol_test.symbol_bench.run_benchmark \
  --scale medium \
  --tasks-file symbol_test/work/medium_hard_tasks.json \
  --modes symbol_bundle_oracle symbol_filtered_select_bundle \
  --dry-run \
  --out /private/tmp/symbol_second_dryrun.jsonl
```

실제 LLM 실행:

```bash
uv run python -m symbol_test.symbol_bench.run_benchmark \
  --scale medium \
  --tasks-file symbol_test/work/medium_hard_tasks.json \
  --modes symbol_bundle_oracle symbol_filtered_select_bundle \
  --ctx-size 8192 \
  --n-predict 64 \
  --timeout 240 \
  --out /private/tmp/symbol_second_final_results.jsonl
```

결과 요약:

```bash
uv run python -m symbol_test.symbol_bench.analyze_results \
  /private/tmp/symbol_second_final_results.jsonl
```

이번 보고서의 수치는 위 명령으로 실행한 `/private/tmp/symbol_second_final_results.jsonl` 기준이다.

## 2. 사용한 LLM 모델 및 환경

사용한 모델은 기존 실험과 동일하다.

| 항목 | 값 |
|---|---|
| 모델 | Qwen2.5 Coder 7B Instruct GGUF |
| 모델 파일 | `/Users/oscar/llm/models/qwen2.5-coder-7b/qwen2.5-coder-7b-instruct-q5_k_m.gguf` |
| Quantization | Q5_K_M |
| 실행 바이너리 | `llama-completion` |
| Backend | llama.cpp / GGML Metal backend |
| 하드웨어 | Apple M3 Pro MacBook Pro |
| 실행 옵션 | `--temp 0`, `--seed 1`, `--simple-io`, `-no-cnv`, `--no-warmup` |
| 2차 실험 ctx-size | 8192 |
| 2차 실험 n-predict | 64 |

기존 medium 전체 repo 실험에서는 `full_repo`가 65k context를 초과했지만, 이번 2차 실험은 symbol 후보와 bundle만 넣으므로 `ctx-size 8192` 안에서 실행됐다.

## 3. 이전 실험과 비교했을 때 달라진 점

이전 실험의 핵심 한계는 단일 symbol만 읽는 구조였다.

기존 `symbol_select` 흐름:

```text
질문
-> 전체 symbol index를 LLM에 전달
-> 대표 symbol URI 1개 선택
-> 선택된 symbol 본문만 read_symbol
-> 답변
```

2차 실험의 새 흐름:

```text
질문
-> 질문 기반 파일/symbol 후보 사전 필터링
-> 작은 후보 목록에서 대표 symbol URI 선택
-> expand_symbol_context로 관련 상수/helper/관련 symbol 확장
-> symbol bundle을 LLM에 전달
-> 답변
```

구현상 달라진 점은 다음과 같다.

| 구분 | 이전 실험 | 2차 실험 |
|---|---|---|
| selector 입력 | 전체 symbol index 638개 | 질문 기반 후보 symbol 2~6개 |
| resolver 단위 | 선택된 symbol 1개 | 선택된 symbol + 상수 + same-file callee/helper + 질문에 명시된 관련 symbol |
| hard task 대응 | 단일 symbol 밖 정보는 누락 | 필요한 주변 symbol을 bundle로 포함 |
| 새 mode | 없음 | `symbol_bundle_oracle`, `symbol_filtered_select_bundle` |
| 검증 기준 | required substring 중심 | required + forbidden substring 지원 |

## 4. 실행한 실험들에 대한 설명

2차 실험에서는 기존 hard task 3개를 그대로 사용했다. 이 task들은 단일 함수 본문만으로는 답하기 어렵도록 설계되어 있다.

| task | 질문 의도 | 필요한 추가 context |
|---|---|---|
| `hard_auth_exact_exception_literal` | `validate_token`이 expired token에서 raise하는 정확한 string literal 확인 | `TOKEN_EXPIRED_MESSAGE` module-level constant |
| `hard_report_cache_key_composed_result` | `build_cache_key(" North/East Plan ", " TEAM-A ", 12)`의 최종 문자열 계산 | `sanitize_report_name` helper |
| `hard_billing_status_and_fee` | `invoice_status(4)`와 `compute_late_fee(4, 10000)` 결과 결합 | `invoice_status` 함수와 `InvoiceCalculator.compute_late_fee` method |

실험 mode는 두 가지다.

### symbol_bundle_oracle

정답 target URI를 이미 알고 있다고 가정한다. selector는 실행하지 않고, target URI에 대해 바로 `expand_symbol_context`를 적용한다.

```text
target_uri
-> expand_symbol_context
-> symbol bundle
-> LLM 답변
```

이 mode는 selector 비용 없이 bundle 확장 자체가 효과가 있는지 확인하기 위한 기준이다.

### symbol_filtered_select_bundle

실제 agent workflow에 더 가까운 mode이다.

```text
질문
-> 파일명, 함수명, class/method 명칭 기반 후보 필터링
-> 필터링된 symbol outline만 LLM selector에 제공
-> 선택된 URI에 expand_symbol_context 적용
-> symbol bundle
-> LLM 답변
```

기존 `symbol_select`가 전체 638개 symbol index를 매번 넣었다면, 이번 mode는 질문에 맞는 후보만 넣는다.

## 5. 테스트를 진행하는데 필요한 각 파일들에 대한 설명

| 파일 | 역할 |
|---|---|
| `symbol_test/symbol_bench/make_corpus.py` | synthetic Python corpus 생성. `services`, `billing`, `reports`, `noise` 파일들을 만든다. |
| `symbol_test/symbol_bench/indexer.py` | AST 기반 symbol index 생성 및 symbol resolve 담당. 2차 실험에서 `expand_symbol_context`가 추가됐다. |
| `symbol_test/symbol_bench/run_benchmark.py` | LLM 호출, mode별 prompt 생성, 결과 JSONL 저장 담당. 2차 실험 mode와 후보 필터링이 추가됐다. |
| `symbol_test/symbol_bench/analyze_results.py` | JSONL 결과를 mode별 accuracy, prompt token, wall time으로 요약한다. |
| `symbol_test/work/medium/corpus/` | medium scale synthetic corpus. 실제 질문 대상 코드가 들어 있다. |
| `symbol_test/work/medium/symbol_index.json` | medium corpus에서 추출한 symbol index. 27 files, 638 symbols. |
| `symbol_test/work/medium/tasks.json` | 기존 쉬운 medium task 3개. |
| `symbol_test/work/medium_hard_tasks.json` | 이번 2차 실험에 사용한 hard task 3개. |
| `/private/tmp/symbol_second_final_results.jsonl` | 이번 실제 실행 결과. 보고서 작성용 임시 결과 파일이다. |

`indexer.py`에 추가된 주요 기능은 다음과 같다.

| 기능 | 설명 |
|---|---|
| `symbols_by_file` | 특정 파일에 속한 symbol만 조회 |
| `_module_assignments` | module-level constant/assignment 수집 |
| `_ReferenceVisitor` | 선택된 symbol 내부에서 참조하는 이름과 호출 함수 수집 |
| `expand_symbol_context` | primary symbol, 참조 상수, same-file helper/callee, 질문에 명시된 관련 symbol을 bundle로 구성 |

`run_benchmark.py`에 추가된 주요 기능은 다음과 같다.

| 기능 | 설명 |
|---|---|
| `symbol_bundle_oracle` | selector 없이 target symbol을 bundle로 확장 |
| `symbol_filtered_select_bundle` | 질문 기반 후보 필터링 후 selector + bundle 확장 |
| `--tasks-file` | 기존 `tasks.json` 대신 hard task 파일을 지정 가능 |
| `--selector-candidates` | selector에 전달할 후보 symbol 최대 개수 |
| `--bundle-depth` | helper/callee 확장 깊이 |
| `--bundle-max-symbols` | bundle에 포함할 symbol 최대 개수 |
| forbidden substring 검증 | 오답 패턴을 포함하면 실패로 처리 |

## 6. 테스트 결과 및 결과에 대한 설명

### 6.1 요약 결과

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms |
|---|---:|---:|---:|---:|---:|
| `symbol_bundle_oracle` | 3 | 0.333 | 2.298 | 369 | 1118.18 |
| `symbol_filtered_select_bundle` | 3 | 0.333 | 4.588 | 587 | 1835.71 |

### 6.2 task별 결과

| mode | task | selector 후보 수 | 선택 URI | bundle 내용 | 정답 여부 | 모델 답변 |
|---|---|---:|---|---|---:|---|
| `symbol_bundle_oracle` | `hard_auth_exact_exception_literal` | - | oracle | `validate_token` + `TOKEN_EXPIRED_MESSAGE` | 성공 | `TOKEN_EXPIRED` |
| `symbol_filtered_select_bundle` | `hard_auth_exact_exception_literal` | 6 | `validate_token` | `validate_token` + `TOKEN_EXPIRED_MESSAGE` | 성공 | `TOKEN_EXPIRED` |
| `symbol_bundle_oracle` | `hard_report_cache_key_composed_result` | - | oracle | `build_cache_key` + `sanitize_report_name` | 실패 | `report:team-a:north_east_plan:v12` |
| `symbol_filtered_select_bundle` | `hard_report_cache_key_composed_result` | 2 | `build_cache_key` | `build_cache_key` + `sanitize_report_name` | 실패 | `report:team-a:north_east_plan:v12` |
| `symbol_bundle_oracle` | `hard_billing_status_and_fee` | - | oracle | `compute_late_fee` + `invoice_status` 등 | 실패 | `status=late, fee=150` |
| `symbol_filtered_select_bundle` | `hard_billing_status_and_fee` | 4 | `compute_late_fee` | `compute_late_fee` + `invoice_status` 등 | 실패 | `status=late, fee=150` |

### 6.3 결과 해석

이번 실험에서 retrieval 자체는 의도대로 동작했다.

`hard_auth_exact_exception_literal`에서는 기존 단일 symbol 방식으로는 `TOKEN_EXPIRED_MESSAGE`의 실제 literal을 볼 수 없었다. 2차 실험에서는 module-level assignment를 bundle에 포함했고, 모델이 `TOKEN_EXPIRED`를 맞혔다.

`hard_report_cache_key_composed_result`에서는 `sanitize_report_name`이 bundle에 포함됐다. 하지만 모델은 `report_name.strip().replace(" ", "_").lower()`를 계산하면서 `/`를 유지해야 하는데도 `North/East Plan`을 `north_east_plan`으로 잘못 변환했다. 즉 context retrieval은 성공했지만 문자열 연산 추론이 실패했다.

`hard_billing_status_and_fee`에서도 `invoice_status`와 `compute_late_fee`가 함께 포함됐다. 하지만 모델은 `10000 * 0.0125 * 1 = 125`를 `150`으로 계산했다. 이 역시 context 부족보다는 산술 추론 오류에 가깝다.

## 7. 이전 실험보다 이번 실험에서 있었던 발전 내용

가장 큰 발전은 selector 비용과 단일 symbol 한계를 동시에 줄였다는 점이다.

기존 hard test의 주요 결과:

| mode | accuracy | mean wall s | mean prompt tokens | selection accuracy |
|---|---:|---:|---:|---:|
| `symbol_oracle` | 0.000 | 2.451 | 225 | - |
| `symbol_select` | 0.000 | 172.170 | 33922 | 1.000 |

2차 hard test 결과:

| mode | accuracy | mean wall s | mean prompt tokens | selection accuracy |
|---|---:|---:|---:|---:|
| `symbol_bundle_oracle` | 0.333 | 2.298 | 369 | - |
| `symbol_filtered_select_bundle` | 0.333 | 4.588 | 587 | 1.000 |

발전 내용은 다음과 같다.

1. `symbol_oracle`의 0/3을 `symbol_bundle_oracle`에서 1/3으로 개선했다.
2. 기존 `symbol_select`의 평균 prompt token 33,922를 `symbol_filtered_select_bundle`에서 587로 줄였다.
3. 기존 `symbol_select`의 평균 wall time 172.170초를 4.588초로 줄였다.
4. selector 후보를 전체 638개 symbol에서 task별 2~6개 symbol로 줄였다.
5. selector selection accuracy는 3/3으로 유지했다.
6. 단일 symbol 본문만 읽던 resolver를 상수/helper/관련 symbol bundle로 확장했다.

`symbol_filtered_select_bundle`은 기존 `symbol_select` 대비 prompt token을 약 98.3%, wall time을 약 97.3% 줄였다. 동시에 단일 symbol 밖 상수를 읽어야 하는 문제를 해결했다.

## 8. 한계점

이번 실험의 한계는 세 가지다.

첫째, 정확도는 아직 1/3이다. bundle에 필요한 코드가 들어가도 모델이 문자열 변환과 산술 계산을 틀릴 수 있다. 즉 retrieval 개선만으로 최종 답변 정확도가 자동으로 보장되지는 않는다.

둘째, dependency 확장이 같은 파일 중심이다. 현재 `expand_symbol_context`는 same-file callee/helper와 module-level assignment를 중심으로 확장한다. 실제 코드베이스에서는 import된 함수, 다른 파일의 class, config constant, type alias까지 따라가야 할 수 있다.

셋째, 후보 필터링이 아직 lexical heuristic 기반이다. 파일명, 함수명, class/method 명칭이 질문에 드러나는 경우에는 잘 동작하지만, 질문이 추상적이거나 domain 용어만 포함하면 후보를 놓칠 수 있다.

또한 이번 corpus는 synthetic Python corpus이다. 실제 repository에서는 동적 import, decorator, class inheritance, re-export, framework convention 등이 추가되므로 parser와 resolver가 더 복잡해진다.

## 9. 코드 어시스턴스에 적용시킬 방법

코드 어시스턴스에 적용할 때는 다음 구조가 적합하다.

```text
사용자 질문 또는 코드 수정 요청
-> repo symbol index 로드 또는 생성
-> 현재 파일, 열린 파일, 에러 로그, 테스트 실패 위치, 질문 키워드로 후보 파일 필터링
-> 후보 파일의 compact symbol outline 구성
-> LLM 또는 deterministic matcher로 대표 symbol 선택
-> expand_symbol_context로 상수/helper/callee/import 관계 확장
-> bundle context를 근거로 답변, 수정 계획, 코드 패치 생성
-> 필요 시 테스트 실행 결과를 다시 retrieval query로 사용
```

실제 code assistant에서는 다음 정보도 retrieval signal로 사용할 수 있다.

| signal | 사용 방법 |
|---|---|
| 현재 열려 있는 파일 | 해당 파일의 symbol 우선 |
| stack trace | 파일 경로와 line number로 primary symbol 추정 |
| failing test name | test가 호출하는 production symbol 추적 |
| 최근 수정 파일 | 후보 파일 가중치 상승 |
| import graph | same-file을 넘어 imported callee까지 확장 |
| `rg` 검색 결과 | 문자열, 에러 메시지, 함수명 후보를 symbol 후보와 결합 |

답변형 code assistance에는 bundle context를 그대로 LLM에 넣으면 된다. 코드 수정형 assistance에는 bundle에 포함된 provenance를 이용해 “어느 symbol 때문에 이 파일을 수정해야 하는지”를 추적할 수 있다.

## 10. 앞으로 발전시킬 방향 및 실현 가능성

이 방향은 실현 가능성이 높다. 이번 2차 실험에서 selector 후보 축소와 bundle 확장이 실제로 latency와 prompt token을 크게 줄였고, 단일 symbol 방식으로 놓치던 상수 문제도 해결했다. 다만 최종 품질을 높이려면 retrieval과 reasoning을 분리해서 더 강하게 설계해야 한다.

앞으로의 발전 방향은 다음과 같다.

1. cross-file dependency 확장

   `import`, `from ... import ...`, class method call, module alias를 따라 다른 파일의 symbol까지 bundle에 포함해야 한다.

2. deterministic execution 보조

   입력값이 구체적인 계산형 질문은 LLM이 mental execution을 하게 하지 말고, 작은 Python evaluator 또는 AST 기반 interpreter로 실제 결과를 계산하는 것이 안정적이다.

3. file outline -> symbol outline의 two-stage retrieval

   먼저 관련 파일을 고르고, 그 다음 해당 파일들의 symbol만 selector에 넣는 구조로 확장한다. 현재 구현은 질문에 파일명이 명시된 경우 강하게 줄이지만, 파일명이 없을 때의 file retrieval이 더 필요하다.

4. symbol signature와 docstring 압축

   selector prompt에는 full metadata 대신 `uri`, `kind`, `qualname`, `signature`, `first docstring line` 정도만 넣어도 충분할 수 있다.

5. bundle ranking과 token budget

   helper/callee를 무조건 포함하지 않고, 질문 관련도, call depth, 최근 수정 여부, 테스트 실패 위치를 기준으로 bundle fragment를 ranking해야 한다.

6. cache 적용

   symbol index, file outline, selector 결과, 자주 쓰는 bundle을 캐싱하면 같은 repo에서 반복 작업할 때 비용을 줄일 수 있다.

7. tree-sitter 기반 다중 언어 확장

   현재는 Python AST 기반이지만, JavaScript/TypeScript, Java, C/C++ 등은 tree-sitter parser를 붙이면 같은 구조를 적용할 수 있다.

최종 목표 구조는 다음과 같다.

```text
repo
-> parser/tree-sitter index
-> file retrieval
-> compact symbol retrieval
-> symbol bundle expansion
-> deterministic tool execution where useful
-> LLM answer or code edit
```

결론적으로 이번 2차 실험은 “전체 index를 LLM에 넣는 symbol_select는 비싸다”는 이전 한계를 실제로 줄였다. 남은 핵심 과제는 symbol retrieval이 아니라, bundle로 확보한 코드를 모델이 정확히 실행/추론하도록 보조하는 단계다.
