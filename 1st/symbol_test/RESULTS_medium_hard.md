# Medium Hard Benchmark Results

실행일: 2026-04-28

기존 진행 결과는 수정하지 않고, 어려운 질문 3개를 별도 task 파일로 추가해 medium corpus에서 재실행했다.

## 추가한 hard task

파일: `symbol_test/work/medium_hard_tasks.json`

| task | 의도 |
|---|---|
| `hard_auth_exact_exception_literal` | `validate_token` 내부만 보면 상수 이름만 보이고, 실제 string literal 값은 module-level constant를 함께 읽어야 함 |
| `hard_report_cache_key_composed_result` | `build_cache_key`와 `sanitize_report_name`을 함께 이해해야 정확한 최종 문자열 계산 가능 |
| `hard_billing_status_and_fee` | `InvoiceCalculator.compute_late_fee`와 `invoice_status`를 함께 봐야 status와 fee를 모두 계산 가능 |

## 실행 조건

- Corpus: `medium`
- Files: 27
- Symbols: 638
- Tasks: 3 hard tasks
- Modes: `full_repo`, `full_file`, `line_span`, `symbol_oracle`, `symbol_select`
- Context size: 65536
- Output: `symbol_test/work/medium_hard_results.jsonl`
- Summary: `symbol_test/work/medium_hard_summary.json`

## 결과 요약

| mode | cases | accuracy | mean wall s | mean prompt tokens | mean prompt eval ms | selection accuracy |
|---|---:|---:|---:|---:|---:|---:|
| full_repo | 3 | 0.000 | 1.087 | 52313 | N/A | |
| full_file | 3 | 0.333 | 2.604 | 281 | 878.29 | |
| line_span | 3 | 0.000 | 2.461 | 224 | 696.98 | |
| symbol_oracle | 3 | 0.000 | 2.451 | 225 | 697.97 | |
| symbol_select | 3 | 0.000 | 172.170 | 33922 | 168318.31 | 1.000 |

`full_repo`는 medium 전체 repo prompt가 65k context를 초과해 실패했다. 따라서 accuracy는 0으로 기록했다.

## 주요 관찰

### 1. 단순 질문과 달리 line_span / symbol_oracle이 모두 실패했다

기존 질문은 타깃 함수 본문만 읽어도 답이 나오는 형태였다. hard task는 의도적으로 상수, helper 함수, 다른 함수 결과를 함께 봐야 하도록 구성했다.

그 결과 `line_span`과 `symbol_oracle`은 모두 0/3이었다. 이는 단일 span 또는 단일 symbol 접근만으로는 cross-symbol 질문을 안정적으로 해결할 수 없음을 보여준다.

### 2. symbol_select는 URI 선택은 모두 맞췄지만 답변은 모두 실패했다

`symbol_select`의 selection accuracy는 1.000이었다.

선택된 URI:

| task | selected URI |
|---|---|
| hard_auth_exact_exception_literal | `memory://symbol/services/auth_service.py::validate_token` |
| hard_report_cache_key_composed_result | `memory://symbol/reports/reporting.py::build_cache_key` |
| hard_billing_status_and_fee | `memory://symbol/billing/payments.py::InvoiceCalculator.compute_late_fee` |

하지만 각 질문은 선택된 단일 symbol 밖의 정보가 필요했다. 따라서 URI 선택은 맞았지만, resolver가 단일 symbol만 전달했기 때문에 최종 답변은 실패했다.

### 3. full_file도 어려운 계산에서는 1/3만 성공했다

`full_file`은 관련 파일 전체를 읽을 수 있어 가장 유리한 조건 중 하나였지만, 계산형 질문에서는 모델이 잘못 계산한 케이스가 있었다.

예:

| task | full_file answer | expected |
|---|---|---|
| hard_auth_exact_exception_literal | `TOKEN_EXPIRED` | `TOKEN_EXPIRED` |
| hard_report_cache_key_composed_result | `report:team-a:north_east_plan:v12` | `report:team-a:north/east_plan:v12` |
| hard_billing_status_and_fee | `status=late, fee=150` | `status=late, fee=125` |

이는 context 접근 방식뿐 아니라 모델의 실제 코드 실행/계산 능력도 별도 변수임을 보여준다.

## 결론

hard task 결과는 기존 결론을 더 정교하게 만든다.

1. `symbol_oracle`은 단일 함수 안에 답이 있을 때 매우 빠르고 정확하다.
2. 하지만 질문이 여러 symbol을 요구하면 단일-symbol 접근은 부족하다.
3. `symbol_select`는 올바른 symbol을 고를 수 있었지만, 단일 symbol만 읽는 후속 단계가 병목이었다.
4. 따라서 다음 단계는 `single-symbol selector`가 아니라 `multi-symbol retrieval`이어야 한다.

필요한 발전 방향:

```text
질문
-> 관련 파일 후보 선택
-> 여러 symbol 후보 선택
-> 선택된 symbol들의 dependency/helper/constant 확장
-> 필요한 symbol bundle 구성
-> LLM 답변 또는 코드 수정
```

즉, 실제 사용에 가까운 구조는 `read_symbol` 하나가 아니라 `read_symbol_bundle` 또는 `expand_symbol_context`에 가깝다.
