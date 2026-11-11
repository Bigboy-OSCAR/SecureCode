# Context Selector 정책 (4.7)

- 문서 버전: 2.0 (2026-11-10, 4.7 재작업). 1.0(2026-11-07)을 대체한다.
- 담당: 박준형 (팀 합의로 2026-11-10부터 4.x 담당, 원 담당 임우형)
- 구현: 4.8 (`context.select`, `ModelRequestGate`). 이 문서는 정책 설계이며 코드를 정하지 않는다.
- 계약: [context.schema.json](../../contracts/context/context.schema.json) · [CONTEXT.md](../contracts/CONTEXT.md) · [POINTERS.md](../contracts/POINTERS.md)
- 시나리오: [selector-scenarios.json](../../contracts/context/selector-scenarios.json). 손계산 기대값이며 [검증 시험](../../services/context-service/tests/contract/test_context_selector_policy.py)이 다시 계산한다.

## 1. 목적과 범위

Context Selector는 이미 있는 세 자료 중 이번 요청에 넣을 원문을 **결정적으로** 고르는 조정 계층이다. 세 자료는 다음과 같다.

- R0 TF-IDF Symbol Bundle
- Source Pointer
- Runtime Pointer

Selector는 무엇을 넣을지와 얼마나 넣을지만 정한다.

하지 않는 것:

- 새 검색·순위 기법(임베딩, LLM 재선택, RAPTOR/요약 트리, Self-Extend)을 쓰지 않는다.
- 요약을 만들거나 파일 전체로 대체하지 않는다.
- 대화 이력을 자르거나 고치지 않는다.
- 후보는 R0 검색 결과, 사용자의 명시 선택, 현재 작업의 포인터에서만 온다.

## 2. 용어

| 용어 | 뜻 |
| --- | --- |
| 후보(candidate) | 넣을 수 있는 자료 하나. `ContextCandidate`(`candidate_id`, `ref`, `score`, `explicit`, `estimated_tokens`, `origin`) |
| origin | `explicit`(사용자가 확인한 범위), `current_task`(이번 세션의 최근 도구 출력 등 현재 작업과 연결된 포인터), `r0`(R0 검색 후보) |
| 대상(object) | 내용이 같은 불변 원본. Source는 `(relative_path, content_sha256)`, Runtime은 포인터 ID와 checksum, 심볼은 그 파일의 `(relative_path, content_sha256)`이다. 같은 파일의 심볼과 Source 포인터는 같은 대상이다 |
| 범위(range) | 대상 원본의 반열린 UTF-8 바이트 구간 `[start, end)`. 심볼 줄 범위는 그 파일의 줄 색인으로 바이트 구간으로 바꾼다 |
| materialize | 선택한 후보를 해당 resolver로 **상한 안에서** 실제로 읽고 계수해 fragment로 만드는 것 |
| fragment | 실제로 넣을 원문과 계수(`token_count`), 포함 정도(`inclusion`), 출처(`provenance`) |

## 3. 예산

### 3.1 식

```text
budget_tokens = model_context_limit
              - system_tokens - tool_schema_tokens - prompt_tokens - history_tokens
              - message_overhead_tokens - reserved_output_tokens - safety_margin_tokens
```

`ContextBudgetCosts`의 8개 값으로 그대로 표시한다. 산술 불변식은 다음과 같다.

- `budget_tokens`는 위 식의 값과 같다.
- `used_tokens`는 fragment `token_count`의 합과 같고 `budget_tokens` 이하다.

| 항목 | 무엇을 세는가 | 누가 모으고 누가 세는가 |
| --- | --- | --- |
| `system_tokens` | SDK에 넘기는 system prompt | host가 텍스트를 넘기고 service TokenCounter가 센다 |
| `tool_schema_tokens` | 모델에 보이는 도구 정의 JSON 전체 | 같음 |
| `prompt_tokens` | 이번 사용자 요청 | 같음 |
| `history_tokens` | 다음 요청에 다시 실리는 대화 이력 전부. tool-call과 tool-result 쌍을 함께 센다 | host가 SDK 이력을 직렬화해 넘긴다. 1 MiB를 넘으면 메시지 단위로 나눠 센 합이며 `provider_estimate`로 표시 |
| `message_overhead_tokens` | 역할·메시지 framing과 context block 봉투(7절의 header·footer) | 같음. 봉투는 빈 본문으로 렌더링해 센다 |
| `reserved_output_tokens` | 답변용 예약(`maxTokensPerTurn`) | host 설정값 |
| `safety_margin_tokens` | 추정 오차 여유 | 정책. `exact`가 아니면 `max(1024, ceil(limit × 2%))` 이상, `exact`면 0 이상 |

결과 처리:

- `budget_tokens < 0` → 계획 없이 `BUDGET_EXCEEDED`. 사용자에게 요청을 줄이거나 새 세션을 시작하라고 안내한다.
- `budget_tokens == 0` → 빈 계획이 유효하다. 모든 후보는 `over_budget`.

### 3.2 계수 모드와 최종 차단 책임

| 모드 | 뜻 | 사용 |
| --- | --- | --- |
| `exact` | provider와 같은 로컬 tokenizer로 센 값 | hard cap을 보장할 수 있는 유일한 모드. 검증된 tokenizer가 있는 모델에만 쓴다 |
| `provider_estimate` | provider count API 등 추정값 | 미리보기·선택에 쓰고 UI는 "추정"으로 표시한다. 안전 마진이 필수다 |
| `provider_reported` | 실제 요청 뒤 provider가 보고한 사용량 | 사후 기록에만 쓴다. 사전 선택이나 차단에는 쓰지 않는다 |
| 미지원(계수기 없음) | 셀 수 없음 | `TOKENIZER_UNAVAILABLE`로 막는다. 길이/4나 바이트 수를 토큰이라고 보고하지 않는다 |

- 미리보기의 예산은 **최종 요청의 보증이 아니다**. SDK framing 뒤 직렬화된 실제 요청 본문은 4.8 `ModelRequestGate`가 `ClineCoreOptions.fetch`에서 다시 세고, 넘으면 보내지 않는다(`BUDGET_EXCEEDED`).
- hard-cap 모드에서 `exact`가 없으면 gate는 `TOKENIZER_UNAVAILABLE`로 막는다.
- 검증되지 않은 provider·tokenizer 값을 `exact`로 표시하지 않는다. 로컬 모델(qwen 등)은 같은 tokenizer를 실제로 확인해야 `exact`가 된다.

## 4. 처리 순서

| 단계 | 내용 | 결과 |
| --- | --- | --- |
| 0 입력 상한 | 명시 선택 ≤ 32(계약), current_task 상위 16, r0 상위 16. 넘는 후보는 평가하지 않는다 | 평가 후보 ≤ 64 |
| 1 범위 | 호출자 workspace·session과 포인터 URI·등록 범위를 확인 | 실패 → `unauthorized` |
| 2 버전 | revision·content hash·index revision·만료 확인 | 실패 → `stale` |
| 3 해석 | 대상이 현재 존재하고 범위가 해석되는지 확인 | 실패 → `no_match` |
| 4 순서 | 아래 4.1절 순서로 정렬 | 이후 단계는 이 순서로 한 번씩 진행 |
| 5 이력 중복 | 같은 대상의 범위가 이미 이력에 있는 범위 안에 있으면 | `in_history` |
| 6 후보 중복 | 같은 대상의 범위가 이미 남긴 후보 범위 하나 안에 있으면 | `duplicate`(`duplicate_of` = 가장 먼저 남긴 후보) |
| 7 크기 | fragment 상한을 넘으면: 나눌 수 없는 후보는 `large_fragment`, 나눌 수 있는 후보는 상한까지 자른다 | `partial_size` |
| 8 예산 | 남은 예산 안이면 전부. 아니면 나눌 수 있는 후보는 남은 예산까지 자르고(최소 크기 이상일 때만), 나머지는 `over_budget` | `partial_budget` |
| 9 materialize | 남긴 후보를 resolver로 읽고 실제 계수로 확정(7절) | fragment |
| 10 조립·검사 | ContextPlan을 만들고 CONTEXT.md 결과 4번 불변식을 검사 | 계획 또는 오류 |

1~3단계의 우선순위는 `unauthorized` > `stale` > `no_match`다. 권한이 없는 대상의 존재 여부나 버전은 알려 주지 않는다.

### 4.1 정렬과 점수

1. 그룹 순서는 `explicit` > `current_task` > `r0`이다. 그룹 사이에서는 점수를 비교하지 않는다.
2. `explicit`: 사용자가 보낸 `context_refs` 순서.
3. `current_task`: 최근 것이 먼저(현재 run에서 만든 포인터 → 직전 run 순). 같으면 `candidate_id` 오름차순. 점수는 표시용 1.0으로 둔다.
4. `r0`: R0 TF-IDF 코사인 점수 내림차순(이미 0~1). 같은 시작 심볼의 원자·확장 후보는 가장 높은 시작 심볼 점수를 공유하고 깊이가 큰 참조 묶음을 먼저 시도한다. 예산에 맞지 않으면 원자 후보가 남는다. 동점이면 `candidate_id` 오름차순.
5. 입력 순서는 결과에 영향을 주지 않는다(시나리오 S9).

**R0 관련도 하한 (3.6 추가)**: R0 자동 후보는 같은 검색 응답 안에서 점수가 0.05 이상이고 1위 점수의 25% 이상인 것만 쓴다. 3.6 live에서 질문의 `py` 같은 흔한 토큰 때문에 점수 0.01대의 무관한 함수 15개가 들어간 것을 막는다(1위 0.519).

점수는 만든 출처 안에서만 의미가 있다. Source·Runtime 후보에 R0 점수를 지어 붙이지 않으며, 그룹이 다른 후보를 점수로 섞지 않는다.

### 4.2 나눌 수 있는 후보와 없는 후보

| 후보 | 나눌 수 있나 | 이유 |
| --- | --- | --- |
| 명시 선택(모든 종류) | 아니오 | 사용자가 확인한 범위 그대로 넣거나 빼야 한다. 줄이려면 사용자가 다시 확인해야 한다 |
| R0 심볼 | 아니오 | Symbol Bundle의 원문 단위를 유지한다. R0가 이미 예산 안 묶음을 만든다 |
| 자동(`current_task`) Source·Runtime 포인터 | 예 | 앞에서부터 UTF-8 경계로 자른 부분 구간을 넣고 출처에 실제 구간을 적는다 |

## 5. 중복

- **같은 대상 + 포함 관계**만 중복으로 본다. URI 문자열이나 파일 경로만으로 판단하지 않는다(3.6 재현 P5). revision이나 hash가 다르면 다른 대상이다.
- 포함은 반열린 구간 기준이다. 같은 구간도 포함으로 본다. 판단 대상은 이미 남긴 후보의 범위 **하나**다(여러 범위의 합집합으로 판단하지 않는다).
- 부분 겹침은 둘 다 남긴다. 겹친 바이트는 두 번 세어 예산에 반영된다(S8).
- **이력 중복(`in_history`)**: host가 넘긴 `history_refs` 기준이다. 이번 세션 이력에 이미 원문이 실린 범위로, 이전 run의 context fragment와 `runtime_read`/`source_read` 결과의 selection을 말한다. 포인터 descriptor(포인터·미리보기)만 있는 경우는 원문이 실린 것이 아니므로 이력 중복이 아니다.
- 명시 선택이 `in_history`이면 오류가 아니다. 원문이 이미 모델 입력에 있기 때문이다.
- **심볼 묶음 멤버 중복(2026-11-11)**: 묶음의 시작 심볼 하나만 중복이라고 전체 helper·상수까지 버리지 않는다. 각 완전한 심볼 구간을 기존 이력과 남긴 자료에 비교하여 이미 있는 멤버만 제외한다. 새 멤버들의 묶음은 예산 때문에 일부만 잘라 넣지 않는다. 출처와 파일/줄 표시는 실제 포함한 멤버만 반영한다.
- **이력 앞부분 건너뛰기(4.8 추가)**: 나눌 수 있는 자동 후보의 시작이 이력 구간 안에 있으면 그 구간 끝으로 시작을 옮긴다. 다음 turn은 같은 앞부분을 다시 넣지 않고 이어지는 구간을 넣는다. 전부 덮이면 `in_history`다. 같은 요청 안의 후보끼리는 옮기지 않는다(부분 겹침 유지, S8).

## 6. 누락 이유와 오류

| 이유 | 언제 | resolver 결과 대응 |
| --- | --- | --- |
| `unauthorized` | 다른 workspace·session, 허용되지 않은 외부 경로 | `FORBIDDEN`. 다른 범위의 `NOT_FOUND`도 존재를 숨기고 이 이유로 처리 |
| `stale` | revision·hash·index revision 불일치, Runtime 만료 | `SOURCE_CHANGED`, `EXPIRED`, `INDEX_NOT_READY`(후보 단위) |
| `no_match` | 대상·심볼이 현재 없음, 범위가 비어 있음 | `NOT_FOUND`(같은 범위), 빈 결과 |
| `in_history` | 5절 | — |
| `duplicate` | 5절. `duplicate_of`·`ref` 필수 | — |
| `large_fragment` | 나눌 수 없는 후보가 fragment 상한(16,384바이트·16,384자)을 넘음 | — |
| `over_budget` | 남은 예산 부족(또는 남은 양이 최소 부분 크기 미만) | `BUDGET_EXCEEDED`(후보 단위) |

요청 단위 오류(계획 없음):

- 고정 비용 초과 → `BUDGET_EXCEEDED`
- 계수기 없음 → `TOKENIZER_UNAVAILABLE`
- 서비스·resolver 장애 → `SERVICE_UNAVAILABLE`
- 색인이 아직 없거나 요청 revision이 현재와 다르면 R0 후보 없이 계획한다(3.6 변경: 색인 전에도 명시·current_task 선택으로 run을 만들 수 있다). 색인 상태는 host `GET /workspaces/:id/index`가 보여 준다
- 필수 메타데이터만으로 응답 256 KiB 초과 → `PAYLOAD_TOO_LARGE`

**run 생성 규칙**: 명시 선택은 조용히 빠지지 않는다. run 요청의 명시 선택 중 하나라도 위 이유(`in_history`·`duplicate` 제외)로 빠지면 run을 만들지 않는다. 처리 순서상 첫 번째 명시 누락이 오류를 정하며, `details.reason`에 누락 이유를 넣는다.

| 첫 명시 누락 이유 | run 생성 오류 |
| --- | --- |
| `over_budget`, `large_fragment` | `BUDGET_EXCEEDED` |
| `stale` | `SOURCE_CHANGED` |
| `unauthorized` | `FORBIDDEN` |
| `no_match` | `NOT_FOUND` |

미리보기는 같은 누락을 보여 주고 사용자가 범위를 줄이거나 빼게 한다.

토큰이 부족할 때 하지 않는 것:

- 요약하지 않는다.
- 파일 전체로 대체하지 않는다.
- 이력을 자르지 않는다.
- tool-call/result 쌍을 깨지 않는다.

대신 다음을 안내한다.

- 명시 범위 줄이기
- 프롬프트 줄이기
- 새 세션 시작(이력 초기화)

## 7. Materialize 계약

| 후보 | resolver | 호출 상한 | fragment 원문·출처 |
| --- | --- | --- | --- |
| R0 심볼 | `symbols.read_bundle` (3.4) | `max_tokens` = min(fragment 상한, 남은 예산), `max_bytes` ≤ 32 KiB 계약 | Bundle 원문. 출처는 `SymbolLocation`(경로·줄·`content_sha256`) |
| Source 포인터 | `SourceReader.read` (4.6) `/internal/v1/source/read` | `max_bytes` ≤ 16,384, `max_tokens` = min(fragment 상한, 남은 예산), selector = 확인 범위 또는 자동 범위 | 반환 `content`와 `provenance.selection`(revision·원본 SHA-256·실제 바이트 구간) |
| Runtime 포인터 | `RuntimeReader.read` (4.3) `/internal/v1/runtime/read` | 같음 | 같음(revision 1, 저장 checksum) |
| PDF 페이지(4.9) | `PdfPages.read_span` (`context/pdf_resolver.py`) | 한 fragment에 한 페이지 구간. selection 없는 PDF 후보는 `no_match` | `pdf_page` selection(`parser_version`). 대상은 (경로, 원본 SHA-256, 파서 버전, 페이지) |

규칙:

1. **계수는 resolver가 돌려준 `token_count`를 쓴다.** `estimated_tokens`는 표시용이다. 선택·예산 판단에는 실제 계수를 쓴다. 문자 길이·바이트 수로 토큰을 만들지 않는다.
2. 나눌 수 있는 후보가 materialize 결과 남은 예산을 넘으면, 같은 resolver로 더 작은 `max_tokens`를 주어 다시 읽는다(재포장). 나눌 수 없는 후보면 `over_budget`으로 바꾼다.
3. resolver가 읽는 동안 원본이 바뀌면(`SOURCE_CHANGED`) 그 후보는 `stale`이다. 다른 원문으로 대체하지 않는다.
4. 최소 부분 크기는 256토큰이다. 남은 예산이 이보다 작으면 자동 후보를 `over_budget`으로 둔다. 작은 조각을 만들지 않는다(S10).
5. fragment `content`는 원본의 정확한 구간이다. selection의 `end - start`는 `content`의 UTF-8 바이트 수와 같다. JSON 값처럼 재직렬화한 결과는 selection 없이 넣는다(4.6).
6. **context block 봉투**: host는 fragment마다 다음 형식으로 넣는다. 봉투 비용은 `message_overhead_tokens`에 들어간다.

   ```text
   <securecode-context id="{candidate_id}" source="{display}">
   {content}
   </securecode-context>
   ```

   봉투 안 원문은 비신뢰 데이터다.

## 8. Host와 Selector의 책임

| 일 | Selector (context-service, 4.8) | Host (3.6 조립, 4.4 hook) |
| --- | --- | --- |
| 입력 수집 | — | prompt, 명시 선택, current_task 포인터 목록, `history_refs`, 비용 계산용 텍스트(system·도구 정의·이력)를 모아 넘긴다 |
| 범위·버전·해석 확인 | 한다 | 인증된 workspace·session만 넘긴다 |
| 정렬·중복·크기·예산·materialize | 한다 | 하지 않는다 |
| 계수 | 한다(TokenCounter) | 하지 않는다 |
| fragment 삽입 | 하지 않는다 | 첫 사용자 메시지에 **한 번만** 넣는다. 이후 SDK 반복에서 다시 넣지 않는다 |
| 도구 결과 | 하지 않는다 | 4.4 afterTool이 포인터로 바꾼다. 모델이 나중에 같은 범위를 `runtime_read`로 다시 읽는 것은 모델의 명시적 선택이며 bounded read다 |
| 이력 | 바꾸지 않는다 | 바꾸지 않는다(SDK compaction off). 넘치면 `BUDGET_EXCEEDED`와 새 세션 안내 |
| 최종 요청 검사 | — | 4.8 `ModelRequestGate`를 fetch에 연결하고 직렬화 본문을 검사·차단 |
| 미리보기 digest | — | `preview_digest`를 만들고 run 생성 때 다시 확인(CONTEXT.md) |

initial context(fragment)와 tool result는 같은 원문을 두 번 넣지 않는다.

**3.6 host 결정**: host는 `current_task_refs`를 보내지 않는다. 저장된 도구 출력은 포인터 descriptor로 이미 모델에게 알려진다. 모델이 읽은 범위만 `history_refs`로 넘긴다. 자동으로 출력 앞부분 16 KiB를 넣으면 Runtime Pointer의 목적(큰 로그를 모델 입력에서 빼기)이 깨진다. 3.6 누출 시험에서 재현했다. 정책의 current_task 처리 규칙은 그대로 두며, 명시 선택(`context_refs`)으로 포인터 범위를 넣을 수 있다.

- fragment는 run 시작 때 한 번 들어간다.
- 도구 결과는 포인터 descriptor로 들어간다.
- 같은 세션의 다음 run은 이전 fragment·읽기 결과를 `history_refs`로 넘겨 `in_history`로 거른다.

## 9. 기본값

| 값 | 기본 | 근거 |
| --- | --- | --- |
| fragment 상한 | 16,384바이트(계약 `content` 16,384자, pointer read `max_bytes` 상한) | 0.7, read.schema.json |
| 최소 부분 크기 | 256토큰 | 작은 조각 방지 |
| 후보 상한 | explicit 32 / current_task 16 / r0 16 | 계약 `context_refs` 32, 계획 행 64 |
| R0 관련도 하한 | 점수 ≥ max(0.05, 1위 × 0.25) | 3.6 live 재현 |
| 계획 행 | selected·fragments·omitted 각 64. 넘는 누락은 `omissions_truncated=true` | context.schema.json |
| 응답 크기 | JSON 256 KiB. fragment 본문은 JSON 인코딩 기준 합 192 KiB까지 넣고, 넘는 후보는 `over_budget` | CONTEXT.md, host loopback 응답 상한 |
| 안전 마진 | `exact` 아님: `max(1024, ceil(limit × 2%))` | 3.1 |

시나리오 파일은 손계산을 위해 fragment 상한 100, 최소 부분 크기 10으로 줄여 같은 규칙을 적용한다. 토큰 수 = 바이트 수(시험 계수기)다.

## 10. 시나리오

| ID | 확인하는 정책 | 기대 |
| --- | --- | --- |
| S1 | 그룹 순서, current_task 최신 우선, 자동 Runtime 상한 자르기, 심볼은 자르지 않음 | 명시 60 + 최신 30 + 자동 100(`partial_size`), r0 두 개 `over_budget`, 사용 190/200 |
| S2 | 명시 선택은 자르지 않음, 뒤 자동 후보는 계속 평가 | 세 번째 명시 `over_budget`, r0 40 선택, run 생성 `BUDGET_EXCEEDED` |
| S3 | 0 예산 | 빈 계획, 모두 `over_budget` |
| S4 | 고정 비용 초과 | 계획 없음, `BUDGET_EXCEEDED` |
| S5 | 무결과·심볼 없음 | `no_match`, 빈 계획, run 생성 `NOT_FOUND` |
| S6 | 권한·버전 | `unauthorized`, `stale` ×3, 유효 r0만 선택, run 생성 `FORBIDDEN` |
| S7 | 대형 후보 | 명시·심볼 `large_fragment`, 자동 Runtime `partial_size` |
| S8 | 중복·이력 | 이력 안 Runtime 범위 `in_history`, 명시 범위 안 심볼 `duplicate`, 부분 겹침 Source 유지 |
| S9 | 동점 | 입력 순서와 무관하게 `candidate_id` 오름차순 |
| S10 | 최소 부분 크기 | 남은 5 < 10 → 자동 Runtime `over_budget` |

## 11. 4.8 구현 (2026-11-10)

| 정책 | 구현 |
| --- | --- |
| 순수 선택(정렬·선별·읽기 계획·포함 판정·run 오류) | `services/context-service/src/securecode_context/context/policy.py` |
| 실행(선별→상한 안 읽기→실계수→포함) | `context/selector.py`, 요청 단위 resolver 묶음 `context/reader.py` |
| 예산 식·계수 모드·안전 마진 | `context/budget.py` |
| Source·Runtime resolver | `context/pointer_resolvers.py` (4.6 `SourceReader`, 4.3 `RuntimeReader`) |
| R0 resolver | `context/symbol_resolver.py` (3.4 `R0SymbolService.search/read_bundle`). 앱 연결은 3.6 |
| 계획 응답 | `context/plan_wire.py`, 내부 경로 `POST /internal/v1/context/select` (`ContextSelectRequest/Response`) |
| 최종 요청 계수 | `POST /internal/v1/tokens/request`, framing 규칙 `common/tokens/request_framing.py` |
| 최종 요청 gate | host `apps/host/src/pointer-hooks/modelRequestGate.ts` → `ClineCoreOptions.fetch` |

Anthropic Messages framing만 검증했다.
- 입력 필드(`system`, `messages`, `tools`, `tool_choice`, `thinking`)는 그대로 센다.
- 출력·전송 설정과 3.1이 확인한 SDK 표준 외 필드(`fallbacks: "default"`, `cache_control`)는 뺀다.
- 그 밖의 필드가 있으면 `TOKENIZER_UNAVAILABLE`이다.
- hard-cap 모드는 `SECURECODE_REQUIRE_FINAL_TOKEN_COUNT=true`(기본)다. 이 모드는 `exact` 계수만 허용한다.

### 처음 인계 내용(4.7 작성)

- **내부 API**: `POST /internal/v1/context/select`. 입력은 `ContextPlanInput`에 host가 모은 비용 텍스트·`history_refs`·current_task 포인터를 더한 것이고, 출력은 `ContextPreviewPlan`이다.
  - 운영 경로에 남아 있는 미인증 `securecode_context.main` 앱(3.6 재현 P8)은 지우고, 인증 router(`app/factory.py`)에 둔다.
  - 기존 `context/policy.py`의 URI 단위 중복, 바이트 수 계수, `ContextPlan` 비계약 모양(P5·P6)은 이 문서로 대체한다.
- **resolver 연결**: `SourceAdapter.reader`, `RuntimeReader`, R0 `read_bundle`. 계수는 앱의 TokenCounter를 쓴다.
- **gate**: 3.5 포트 `ModelRequestGate.check(OutboundModelRequest, signal)`를 구현해 host `main.ts`의 `gate: null`을 대체한다. 3.2절의 모드 규칙을 지킨다. 매 turn 전 준비 확인은 4.4의 `checkTurnReady`에 붙인다.
- **시험**: `selector-scenarios.json` 10개를 실제 구현으로 돌려 같은 결과가 나와야 한다. 시험의 `select()`는 기준(oracle)일 뿐 제품 코드가 아니다.
