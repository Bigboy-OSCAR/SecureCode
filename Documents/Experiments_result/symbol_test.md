# Symbol Index / Symbol Selector 테스트 보고서

## 1. 테스트 진행 방식

이번 테스트의 목적은 코드 전체를 LLM context에 직접 넣는 방식과, 파일별 symbol index를 만든 뒤 필요한 함수/클래스만 선택적으로 읽는 방식을 비교하는 것이다. 특히 `memory://symbol/file.py::func_name` 형태의 symbol selector가 실제로 token 사용량과 실행 시간을 줄이는지 확인했다.

테스트는 `symbol_test` 폴더에 독립 실행 가능한 하네스로 구성했다.

| 파일 | 역할 |
|---|---|
| `symbol_test/symbol_bench/make_corpus.py` | 테스트용 Python corpus 생성 |
| `symbol_test/symbol_bench/indexer.py` | Python AST parser로 함수/클래스 이름, 시작줄, 끝줄을 추출해 symbol index 생성 |
| `symbol_test/symbol_bench/run_benchmark.py` | 5가지 실행 방식을 llama.cpp/Qwen2.5 모델로 실행하고 결과를 JSONL로 저장 |
| `symbol_test/symbol_bench/analyze_results.py` | 결과 JSONL을 모드별 accuracy, token, 시간 기준으로 요약 |
| `symbol_test/work/<scale>/symbol_index.json` | parser가 생성한 symbol index |
| `symbol_test/work/<scale>/tasks.json` | 정답 검증이 가능한 코드 이해 질문 목록 |

테스트 corpus는 실제 프로젝트와 유사하게 여러 Python 파일과 다수의 함수/클래스를 포함하도록 생성했다. 타깃 파일에는 정답이 되는 함수가 있고, `noise` 파일에는 유사한 이름의 방해 함수들을 넣어 전체 context와 symbol index를 키웠다.

예시 symbol index 항목은 다음과 같다.

```json
{
  "path": "services/auth_service.py",
  "kind": "function",
  "name": "validate_token",
  "qualname": "validate_token",
  "start_line": 19,
  "end_line": 26,
  "uri": "memory://symbol/services/auth_service.py::validate_token"
}
```

실행 환경은 M3 MacBook Pro, llama.cpp Metal backend, Qwen2.5 Coder 7B Instruct GGUF Q5_K_M 모델이다.

## 2. 실행 방식 5가지

### full_repo

모든 Python 파일 내용을 한 번에 prompt에 넣는 방식이다.

```text
질문 + 전체 repo 코드 -> LLM -> 답변
```

가장 단순하지만 repo 크기가 커질수록 prompt token과 prompt eval 시간이 급격히 증가한다. context window를 초과할 위험도 가장 크다.

### full_file

정답이 들어 있는 파일 하나만 통째로 prompt에 넣는 방식이다.

```text
질문 + 타깃 파일 전체 -> LLM -> 답변
```

`full_repo`보다 훨씬 작지만, agent가 이미 올바른 파일을 알고 있다는 가정이 필요하다.

### line_span

타깃 함수/메서드의 시작줄과 끝줄만 읽어 prompt에 넣는 방식이다.

```text
질문 + file.py#Lx-Ly 범위 -> LLM -> 답변
```

필요한 코드만 전달하므로 효율적이다. 다만 줄 번호 기반 접근은 코드 변경이나 탐색 과정에서 사람이 직접 지정하기 어렵다는 한계가 있다.

### symbol_oracle

타깃 symbol URI를 이미 알고 있다고 가정하고, 해당 함수/클래스 본문만 resolver로 읽는 방식이다.

```text
질문
-> 이미 알고 있는 memory://symbol/file.py::qualname 사용
-> symbol_index.json에서 start/end line 확인
-> 해당 symbol 본문만 읽음
-> LLM -> 답변
```

이 방식은 symbol 접근 자체의 이상적인 성능을 측정하기 위한 기준이다. selector 비용이 없기 때문에 `line_span`과 거의 같은 수준으로 빠르다.

### symbol_select

LLM에게 symbol index JSON을 보여주고, 질문에 필요한 symbol URI를 직접 고르게 한 뒤, 선택된 symbol 본문만 읽어 답하게 하는 방식이다.

```text
1차 호출: 질문 + symbol index JSON -> LLM이 symbol URI 선택
2차 호출: 질문 + 선택된 symbol 본문 -> LLM이 답변
```

가장 실제 agent workflow에 가깝다. 하지만 현재 구현은 전체 symbol index를 매번 LLM에 넣기 때문에 index가 커질수록 selector 호출 비용이 커진다.

## 3. 테스트 결과

### 3.1 간단한 테스트 결과

간단한 테스트는 `small` corpus의 1개 질문을 대상으로 5개 방식을 모두 실행했다.

| mode | cases | accuracy | wall time | prompt tokens | prompt eval |
|---|---:|---:|---:|---:|---:|
| full_repo | 1 | 1.00 | 14.200s | 4098 | 13056.17ms |
| full_file | 1 | 1.00 | 2.089s | 317 | 985.53ms |
| line_span | 1 | 1.00 | 2.110s | 217 | 694.36ms |
| symbol_oracle | 1 | 1.00 | 2.109s | 214 | 683.56ms |
| symbol_select | 1 | 1.00 | 11.304s | 2709 | 8390.18ms |

간단한 테스트에서는 `symbol_oracle`이 `full_repo` 대비 약 94.7%의 prompt 문자 수 감소, 약 85.1%의 wall time 감소를 보였다. `symbol_select`도 정답 symbol을 올바르게 선택했지만, selector 호출이 추가되기 때문에 작은 corpus에서는 `symbol_oracle`보다 느렸다.

### 3.2 Medium 테스트 결과

실제 사용에 더 가깝게 보기 위해 `medium` corpus를 사용했다.

```text
files: 27
symbols: 638
tasks: 3
```

먼저 `ctx-size 65536`으로 전체 모드를 실행했을 때, `full_repo`는 context 초과로 실패했다.

```text
main: prompt is too long (67188 tokens, max 65532)
```

따라서 `full_repo`는 첫 케이스만 `ctx-size 131072`, `timeout 900`으로 재측정했다.

| mode | cases | accuracy | mean wall time | mean prompt tokens | mean prompt eval | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| full_repo | 1 | 1.000 | 612.869s | 67188 | 610521.20ms | |
| full_file | 3 | 1.000 | 2.286s | 256 | 803.70ms | |
| line_span | 3 | 1.000 | 2.120s | 199 | 650.56ms | |
| symbol_oracle | 3 | 1.000 | 2.131s | 199 | 654.80ms | |
| symbol_select | 3 | 1.000 | 181.191s | 33871 | 177625.00ms | 1.000 |

`full_repo` 대비 감소율은 다음과 같다.

| mode | token reduction | wall time reduction |
|---|---:|---:|
| full_file | 99.6% | 99.6% |
| line_span | 99.7% | 99.7% |
| symbol_oracle | 99.7% | 99.7% |
| symbol_select | 49.6% | 70.4% |

Medium 테스트에서 가장 중요한 결과는 `full_repo` 방식이 65k context에서는 실패했고, 131k context에서도 한 질문 처리에 약 10분 13초가 걸렸다는 점이다. 반면 `symbol_oracle`은 필요한 함수 본문만 읽기 때문에 3개 질문 모두 약 2.1초대에 완료됐다.

`symbol_select`는 3개 질문 모두 올바른 symbol을 선택했지만, 전체 symbol index 638개를 매번 prompt로 전달했기 때문에 평균 181초가 걸렸다. 즉 symbol 선택 정확도는 확인됐지만, naive selector 구조는 latency 측면에서 개선이 필요하다.

## 4. 발전 방향 및 실현 가능성

이번 테스트의 결론은 symbol 단위 접근 자체는 충분히 실현 가능하고 성능 개선 효과도 크다는 것이다. 특히 `memory://symbol/file.py::qualname`으로 접근해 필요한 함수/클래스 본문만 읽는 방식은 전체 repo 주입 대비 token과 시간을 크게 줄였다.

다만 현재 `symbol_select`는 전체 symbol index를 한 번에 LLM에게 전달한다. medium corpus에서도 selector prompt가 커져 평균 181초가 걸렸으므로, 실제 사용을 위해서는 후보 symbol을 먼저 줄이는 구조가 필요하다.

앞으로 발전시킬 방향은 다음과 같다.

1. 파일/디렉터리 단위 사전 필터링

   질문에 포함된 키워드, 현재 열려 있는 파일, import 관계, 최근 수정 파일 등을 사용해 전체 symbol index가 아니라 관련 파일의 symbol만 selector에 전달한다.

2. two-stage symbol retrieval

   먼저 `file outline` 수준에서 관련 파일을 고르고, 그 다음 해당 파일 안의 symbol 후보만 LLM selector에 제공한다.

   ```text
   질문 -> 관련 파일 후보 선택 -> 해당 파일의 symbol 후보 선택 -> read_symbol
   ```

3. 문자열 검색과 symbol selector 결합

   `rg`, 함수명 부분 검색, class/function name matching을 먼저 수행해 후보를 줄인 뒤 LLM selector를 사용한다. 이 경우 LLM은 수백 개 symbol이 아니라 수십 개 이하의 후보만 비교하면 된다.

4. symbol index 압축

   selector 단계에서는 전체 metadata를 전달하지 않고 `uri`, `kind`, `qualname`, `short signature` 정도만 전달한다. 필요 시 docstring이나 주변 context는 resolver 단계에서 별도로 읽는다.

5. index 및 선택 결과 캐싱

   동일 repo에서 반복 작업할 경우 symbol index는 한 번만 생성하고, 자주 선택되는 symbol URI는 캐싱한다. 이렇게 하면 후속 질문에서는 selector 비용을 줄일 수 있다.

6. 실제 코드베이스 적용

   현재 테스트는 synthetic corpus이지만, AST parser 기반이므로 Python 코드베이스에는 바로 적용 가능하다. JavaScript/TypeScript, Java, C/C++ 등은 tree-sitter 같은 parser를 추가하면 같은 구조로 확장할 수 있다.

최종적으로 실현 가능한 구조는 다음과 같다.

```text
전체 repo
-> parser로 file outline / symbol index 생성
-> 질문 기반 후보 파일 필터링
-> 후보 symbol selector
-> memory://symbol/... resolve
-> 필요한 함수/클래스 본문만 LLM에 전달
-> 답변 또는 코드 수정
```

따라서 이 접근 방식은 실현 가능성이 높다. 핵심 과제는 symbol resolver가 아니라 selector 입력을 줄이는 retrieval 단계다. 즉, `전체 symbol index -> LLM selector` 구조를 그대로 쓰는 것은 비효율적이고, `필터링된 후보 symbol -> LLM selector` 구조로 발전시키면 실제 코드 에이전트에서 충분히 유효한 방식이 될 수 있다.

## 5. 어려운 질문 추가 테스트

기존 질문은 대부분 특정 함수 본문 안에서 바로 답을 찾을 수 있는 형태였다. 그래서 `line_span`이나 `symbol_oracle`처럼 단일 함수 범위만 읽는 방식도 높은 정확도를 보였다. 이 한계를 확인하기 위해 기존 진행 내용은 수정하지 않고, `medium` corpus에 대해 어려운 질문 3개를 별도로 추가해 다시 테스트했다.

추가한 파일은 다음과 같다.

| 파일 | 설명 |
|---|---|
| `symbol_test/work/medium_hard_tasks.json` | 어려운 질문 3개 정의 |
| `symbol_test/work/medium_hard_results.jsonl` | hard test raw 결과 |
| `symbol_test/work/medium_hard_summary.json` | hard test 요약 결과 |
| `symbol_test/RESULTS_medium_hard.md` | hard test 별도 요약 문서 |

### 5.1 어려운 질문 3개와 어려운 이유

| task | 질문 요약 | 어려운 이유 |
|---|---|---|
| `hard_auth_exact_exception_literal` | `validate_token`에서 만료된 active token일 때 `ValueError`에 들어가는 정확한 string literal 값을 묻는 질문 | `validate_token` 본문에는 `TOKEN_EXPIRED_MESSAGE`라는 상수 이름만 있고, 실제 값 `"TOKEN_EXPIRED"`는 module-level constant에 있다. 따라서 함수 본문만 읽으면 정확한 literal을 알기 어렵다. |
| `hard_report_cache_key_composed_result` | `report_name=' North/East Plan '`, `tenant_id=' TEAM-A '`, `version=12`일 때 `build_cache_key`의 최종 반환 문자열을 묻는 질문 | `build_cache_key`는 내부에서 `sanitize_report_name`을 호출한다. 최종 답을 계산하려면 tenant normalization뿐 아니라 helper 함수의 `strip`, 공백 치환, lower-case 동작까지 함께 이해해야 한다. |
| `hard_billing_status_and_fee` | `days_late=4`, `subtotal_cents=10000`일 때 `invoice_status` 결과와 `compute_late_fee` 결과를 함께 묻는 질문 | status는 `invoice_status`에서 계산되고 fee는 `InvoiceCalculator.compute_late_fee`에서 계산된다. 서로 다른 symbol 두 개를 함께 읽고 계산해야 한다. |

이 세 질문은 공통적으로 “단일 함수 본문 안에 답이 완전히 들어 있지 않은 질문”이다. 따라서 기존의 `line_span`이나 단일 `read_symbol` 방식이 실제 코드 이해 문제에서 어디까지 통하는지 확인할 수 있다.

### 5.2 각 실행 방식의 질문별 성공 여부

아래 표는 hard task 3개에 대해 각 모드가 최종 답변을 맞혔는지 나타낸 것이다.

| mode | hard_auth_exact_exception_literal | hard_report_cache_key_composed_result | hard_billing_status_and_fee | 전체 성공률 |
|---|---:|---:|---:|---:|
| `full_repo` | 실패 | 실패 | 실패 | 0/3 |
| `full_file` | 성공 | 실패 | 실패 | 1/3 |
| `line_span` | 실패 | 실패 | 실패 | 0/3 |
| `symbol_oracle` | 실패 | 실패 | 실패 | 0/3 |
| `symbol_select` | 실패 | 실패 | 실패 | 0/3 |

`full_repo`는 질문 난이도와 별개로 medium 전체 repo prompt가 `ctx-size 65536`을 초과해 실패했다. 이전 medium 테스트에서도 같은 문제가 확인됐다.

`symbol_select`는 3개 질문 모두 올바른 대표 symbol URI를 선택했다.

| task | 선택된 symbol URI | 선택 성공 여부 |
|---|---|---:|
| `hard_auth_exact_exception_literal` | `memory://symbol/services/auth_service.py::validate_token` | 성공 |
| `hard_report_cache_key_composed_result` | `memory://symbol/reports/reporting.py::build_cache_key` | 성공 |
| `hard_billing_status_and_fee` | `memory://symbol/billing/payments.py::InvoiceCalculator.compute_late_fee` | 성공 |

하지만 선택된 단일 symbol만 읽어서는 질문에 필요한 상수, helper 함수, 관련 함수까지 포함되지 않았다. 따라서 URI 선택은 성공했지만 최종 답변은 실패했다.

### 5.3 어려운 질문 테스트 결과

Hard test의 요약 수치는 다음과 같다.

| mode | cases | accuracy | mean wall time | mean prompt tokens | mean prompt eval | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| `full_repo` | 3 | 0.000 | 1.087s | 52313 | N/A | |
| `full_file` | 3 | 0.333 | 2.604s | 281 | 878.29ms | |
| `line_span` | 3 | 0.000 | 2.461s | 224 | 696.98ms | |
| `symbol_oracle` | 3 | 0.000 | 2.451s | 225 | 697.97ms | |
| `symbol_select` | 3 | 0.000 | 172.170s | 33922 | 168318.31ms | 1.000 |

대표적인 오답은 다음과 같다.

| task | mode | 모델 답변 | 기대 답 |
|---|---|---|---|
| `hard_auth_exact_exception_literal` | `symbol_oracle` | `Token expired` | `TOKEN_EXPIRED` |
| `hard_report_cache_key_composed_result` | `symbol_oracle` | `report:team-a:north/east plan:v12` | `report:team-a:north/east_plan:v12` |
| `hard_billing_status_and_fee` | `symbol_oracle` | `status=OVERDUE, fee=150` | `status=late, fee=125` |

이 결과는 기존 쉬운 질문 테스트와 대비된다.

#### 기존 간단한 테스트 결과

| mode | cases | accuracy | wall time | prompt tokens |
|---|---:|---:|---:|---:|
| `full_repo` | 1 | 1.00 | 14.200s | 4098 |
| `full_file` | 1 | 1.00 | 2.089s | 317 |
| `line_span` | 1 | 1.00 | 2.110s | 217 |
| `symbol_oracle` | 1 | 1.00 | 2.109s | 214 |
| `symbol_select` | 1 | 1.00 | 11.304s | 2709 |

쉬운 질문에서는 단일 함수 본문만으로 정답이 충분했기 때문에 `line_span`, `symbol_oracle`, `symbol_select`가 모두 성공했다.

#### 기존 medium 테스트 결과

| mode | cases | accuracy | mean wall time | mean prompt tokens |
|---|---:|---:|---:|---:|
| `full_repo` | 1 | 1.000 | 612.869s | 67188 |
| `full_file` | 3 | 1.000 | 2.286s | 256 |
| `line_span` | 3 | 1.000 | 2.120s | 199 |
| `symbol_oracle` | 3 | 1.000 | 2.131s | 199 |
| `symbol_select` | 3 | 1.000 | 181.191s | 33871 |

기존 medium 질문도 주로 단일 symbol 안에서 답을 찾을 수 있는 형태였기 때문에 `line_span`과 `symbol_oracle`이 높은 정확도를 보였다. 그러나 hard test에서는 이 가정이 깨졌다.

### 5.4 Hard test를 통해 알게 된 점

이번 hard test로 확인한 핵심은 다음과 같다.

1. 단일 symbol 접근은 빠르지만, 답이 단일 symbol 안에 있을 때만 안정적이다.
2. 실제 코드 이해 질문은 상수, helper 함수, class method, 관련 함수 호출을 함께 봐야 하는 경우가 많다.
3. `symbol_select`는 올바른 대표 symbol을 고를 수 있었지만, 대표 symbol 하나만 읽는 것으로는 충분하지 않았다.
4. 따라서 앞으로의 구현은 `read_symbol` 하나가 아니라, 관련 상수/helper/호출 관계를 함께 묶는 `read_symbol_bundle` 또는 `expand_symbol_context`가 필요하다.

## 6. `read_symbol_bundle` / `expand_symbol_context` 구현 예상 방식

`read_symbol_bundle` 또는 `expand_symbol_context`는 하나의 symbol URI를 입력받아, 해당 symbol 본문뿐 아니라 답변에 필요한 주변 symbol/context를 함께 묶어 반환하는 도구로 설계할 수 있다.

### 6.1 기본 입력과 출력

입력 예시는 다음과 같다.

```text
memory://symbol/reports/reporting.py::build_cache_key
```

출력은 단일 함수 본문이 아니라 bundle 형태가 된다.

```text
symbol: build_cache_key
dependencies:
- sanitize_report_name
- module-level constants used by selected symbols
context:
- selected symbol source
- helper function source
- relevant constants
```

즉, 기존 `read_symbol`이 아래처럼 동작했다면,

```text
read_symbol(uri) -> 해당 함수/클래스 본문만 반환
```

새 방식은 다음처럼 동작해야 한다.

```text
read_symbol_bundle(uri) -> 해당 symbol + 관련 helper/constant/callee/caller 일부 반환
```

### 6.2 구현 단계

예상 구현 방식은 다음과 같다.

1. 선택된 symbol AST 분석

   선택된 함수/클래스 본문을 AST로 분석해 내부에서 참조하는 이름들을 수집한다.

   예:

   ```python
   def build_cache_key(report_name, tenant_id, version):
       safe_name = sanitize_report_name(report_name)
       safe_tenant = tenant_id.strip().lower()
       return f"report:{safe_tenant}:{safe_name}:v{version}"
   ```

   여기서 `sanitize_report_name`은 같은 파일 안의 helper 함수로 확장 대상이 된다.

2. module-level constant 추적

   선택된 symbol 내부에서 참조하는 대문자 상수나 module-level assignment를 찾는다.

   예:

   ```python
   TOKEN_EXPIRED_MESSAGE = "TOKEN_EXPIRED"
   ```

   `validate_token`이 `TOKEN_EXPIRED_MESSAGE`를 참조하면 bundle에 이 상수 정의도 포함한다.

3. 같은 파일 내 helper/callee 추적

   선택된 symbol이 호출하는 같은 파일 내 함수가 symbol index에 있으면 함께 읽는다.

   예:

   ```text
   build_cache_key -> sanitize_report_name
   ```

4. 질문 기반 관련 symbol 추가

   질문 텍스트에 다른 함수명이나 class name이 명시되어 있으면 해당 symbol도 bundle에 포함한다.

   예:

   ```text
   question: combine invoice_status and compute_late_fee
   selected: compute_late_fee
   추가 포함: invoice_status
   ```

5. token budget 기반 제한

   관련 symbol을 무제한 포함하면 다시 context가 커질 수 있다. 따라서 depth와 token budget을 둔다.

   권장 기본값:

   ```text
   dependency_depth: 1
   max_symbols: 5~10
   max_bundle_tokens: 2000~4000
   ```

6. bundle provenance 표시

   LLM이 어떤 코드 조각이 왜 포함됐는지 이해할 수 있도록 각 조각에 URI와 포함 이유를 붙인다.

   예:

   ```text
   ### primary symbol
   memory://symbol/reports/reporting.py::build_cache_key

   ### helper referenced by primary symbol
   memory://symbol/reports/reporting.py::sanitize_report_name
   ```

### 6.3 예상 동작 예시

`hard_report_cache_key_composed_result` 질문에서는 현재 `symbol_select`가 다음 URI를 고른다.

```text
memory://symbol/reports/reporting.py::build_cache_key
```

기존 `read_symbol`은 `build_cache_key` 본문만 반환한다.

```python
def build_cache_key(report_name: str, tenant_id: str, version: int) -> str:
    safe_name = sanitize_report_name(report_name)
    safe_tenant = tenant_id.strip().lower()
    return f"report:{safe_tenant}:{safe_name}:v{version}"
```

하지만 `read_symbol_bundle`은 helper까지 포함해야 한다.

```python
def sanitize_report_name(report_name: str) -> str:
    return report_name.strip().replace(" ", "_").lower()

def build_cache_key(report_name: str, tenant_id: str, version: int) -> str:
    safe_name = sanitize_report_name(report_name)
    safe_tenant = tenant_id.strip().lower()
    return f"report:{safe_tenant}:{safe_name}:v{version}"
```

이렇게 하면 모델이 `North/East Plan`이 `north/east_plan`으로 변환된다는 사실을 알 수 있다.

### 6.4 최종 목표 구조

최종 구현은 다음 구조가 되어야 한다.

```text
질문
-> symbol selector가 대표 symbol 선택
-> expand_symbol_context가 대표 symbol의 helper/constant/callee를 확장
-> 필요한 symbol bundle 구성
-> LLM이 bundle을 보고 답변 또는 코드 수정
```

이 구조는 기존 `symbol_oracle`의 속도 장점과 `full_file`의 주변 정보 장점을 절충한다. 전체 파일이나 전체 repo를 넣지 않으면서도, 단일 함수만 읽을 때 놓치는 상수/helper/호출 관계를 보완할 수 있다.
