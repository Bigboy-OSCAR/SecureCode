# 화면별 표시·사용자 동작 상세 명세

> 작업: 2.2 · 담당: 김찬우 · 작성일: 2026-11-05 (Asia/Seoul)
>
> 상태: 작성 가능한 상세 설계 완료, **계약 보완 대기(BLOCKED)**. 실행 가능한 UI나 행동 시험 통과를 의미하지 않는다.
>
> 화면 배치·목적·지원 범위: [SCREEN_SPEC](SCREEN_SPEC.md) · 사례·fixture 대응: [UI_BEHAVIOR_CASES](UI_BEHAVIOR_CASES.md) · 계약 결함·해제 조건: [2.2 인계](../handoffs/2.2-ui-behavior-contract-gaps.md)

## 1. 읽는 방법과 적용 기준

SC-01~SC-09와 UI-01~UI-34는 2.1의 ID를 유지한다. 아래 요소 ID는 기존 와이어프레임의 라벨·버튼을 식별하기 위한 문서 ID이며 API 필드나 실행 타입이 아니다. 화면 구조는 SCREEN_SPEC, 표시·검증·버튼 규칙은 이 문서, 사전 상황→조작/응답→관찰 결과는 UI_BEHAVIOR_CASES를 정본으로 삼는다. 내부 상태 구조·상태 관리 코드·자동 행동 시험은 김민지 1.2/1.3의 책임이다. 이 문서는 별도 상태 전이 모델·machine/reducer·command 프로토콜을 정의하지 않는다.

계약 정본은 [JSON Schema](../../contracts/), [오류 표](../../contracts/common/error-codes.json)다. [API](../contracts/API.md), [EVENTS](../contracts/EVENTS.md), [POINTERS](../contracts/POINTERS.md), [CONTEXT](../contracts/CONTEXT.md)를 함께 사용한다. 생성 타입을 재선언하지 않는다. 확인한 모든 오류 코드는 현재 final이다.

**확정**은 필드가 실제 스키마에 있다는 뜻이고 **보완 대기 G-번호**는 필요한 계약이 없거나 모순된다는 뜻이다. 보완 대기 기능은 시각적인 설계만 제공한다. 없는 DTO·필드·API·fixture를 UI에서 만들어 실연결하거나 다른 동작으로 대체하지 않는다. 이 때문에 2.2와 이에 의존하는 1.2/1.3의 전체 착수 조건을 충족했다고 보고하지 않는다.

## 2. 공통 표시·조작 규칙

| 항목 | 모든 화면의 요구 |
| --- | --- |
| API 경계 | 아래 축약 경로는 모두 host `/api/v1`다. 같은 origin의 cookie로 요청하며 브라우저에서 내부 서비스·모델 제공자를 호출하지 않는다. 응답은 계약 검증 후 표시한다. |
| 로딩·빈값·실패 | 최초 조회는 “불러오는 중…”. 재조회 중에는 직전 결과를 “이전 조회 결과”로 표시한다. 실패는 “불러오지 못했습니다”와 복구 행동을 제공하고 빈 목록으로 덮지 않는다. 새 응답 확인 전 성공·삭제·취소를 확정하지 않는다. |
| 입력 길이 | schema의 문자열 길이는 Unicode 문자 수 기준이며 UTF-8 byte 상한과 구별한다. 빈 문자열 및 공백뿐인 이름·질문·검색어는 제출 불가. 질문·명령·경로를 조용히 잘라내거나 바꾸지 않는다. 잘못된 Unicode는 입력 오류로 처리한다. |
| 버튼 활성 | 표의 개별 조건 외에 유효한 현재 scope·인증·필요한 서비스 연결·입력 검증·동일 요청 처리 중 아님이 필요하다. 비활성 이유를 버튼 옆에 문장으로 표시한다. 읽기 전용 탐색·닫기·입력 수정은 가능한 한 유지한다. |
| 요청 유실·중복 | workspace/index/session/run 생성은 같은 본문과 같은 `idempotency_key`로 확인한다. 키는 8~128자 계약을 따르는 앱 생성값으로 화면에 입력받지 않는다. 응답 유실은 실패 확정이 아니다. 본문을 바꾼 새 작업은 기존 결과를 먼저 확인한 뒤 사용자가 시작한다. 승인·삭제·등록·파싱을 자동 반복하지 않는다. |
| 범위·늦은 응답 | workspace/session/run, 요청한 질의·범위·revision을 비교한다. 이전 프로젝트나 수정 전 입력에 대한 응답은 현재 화면을 덮지 않는다. 프로젝트 이동·창 닫기는 실행 취소가 아니다. 진행 중 작업으로 돌아가는 위치를 제공한다. |
| 원문·비밀값 | 코드·문서·로그·명령은 비신뢰 텍스트로 표시한다. 스크립트·도구 지시로 실행하지 않는다. 서버 절대경로·키·연결 코드·내부 토큰을 응답/로그/URL/영구 저장소에 남기지 않는다. 포인터 문자열을 파일 경로나 웹 링크로 해석하지 않는다. |
| 목록·다음 부분 | 일반 목록·심볼은 `page.limit` 1~100(기본 20), `page.has_more/next_cursor/truncated_by_bytes`를 사용한다. 포인터 검색은 별도 최상위 `limit/cursor`와 `truncated/next_cursor`다. cursor는 최대 512자 opaque 값으로 사용자에게 입력받거나 해석하지 않는다. 다음 페이지를 자동 끝까지 읽지 않는다. |
| 시간·크기 | 서버 RFC 3339 시각을 사용자 로컬 시각·시간대와 함께 표시한다. bytes와 tokens를 분리한다. 만료까지 남은 시간은 보조 표시이며 서버 판정이 최종이다. 총량·분모가 없으면 백분율·진행 완료를 추측하지 않는다. |
| 선택·미리보기 | 보기와 모델에 전달할 자료 선택은 별도 조작이다. 선택은 실제 범위·버전에 고정한다. 질문/선택/이력/색인/모델 설정이 바뀌면 이전 예산은 “갱신 필요”. 원문 변경·만료·등록 해제·삭제 후 선택을 무효화하며 새 본문으로 자동 치환하지 않는다. |
| 오류 | 4절 문구와 안전한 `error.message`, `error.request_id`를 사용한다. `details` 전체를 덤프하지 않는다. `retryable=true`는 같은 실행을 새로 만들라는 뜻이 아니다. 실제 응답의 retryable과 필요한 복구 조건을 우선한다. |
| 접근성 | 보이는 label, 입력 오류 연결, 본문 바로가기, 명확한 focus, 텍스트 상태 배지를 제공한다. 상태는 `aria-live=polite`, 제출 오류는 한 번 알린다. 대화상자는 제목·focus 가두기·닫은 뒤 시작점 복귀를 제공한다. Escape/닫기는 승인·거절·삭제가 아니다. |
| 화면 폭·스트림 | 1280px/768px 배치는 SCREEN_SPEC을 따른다. 긴 코드만 내부 스크롤한다. 승인·취소·오류를 접힌 패널 안에 숨기지 않는다. 스트림 글자마다 초점/스크롤/알림을 강제하지 않으며 사용자가 읽던 위치를 유지한다. |

## 3. 화면별 명세

<a id="sc-01"></a>

### SC-01 최초 연결

목적: 일회용 코드를 교환하고 기존 작업을 복구한다. 화면 배치는 SCREEN_SPEC의 SC-01, 사례는 UI-01/UI-02/UI-33이다.

| 요소·와이어프레임 라벨 | 표시 필드·API 출처 | 입력 규칙·버튼 활성·조작 |
| --- | --- | --- |
| SC-01-A 연결 코드 / 연결 | `BootstrapRequest.code` → `POST /auth/bootstrap`; `BootstrapResponse.authenticated/session_expires_at` | 영문 대소문자·숫자·하이픈 8~64자(`^[A-Za-z0-9-]+$`). 빈값·형식 오류·전송 중은 연결 불가. Enter는 연결 버튼과 동일하며 중복 제출하지 않는다. |
| SC-01-B 로컬 서비스 / 다시 확인 | `GET /health`: `status` | `ok` “응답 있음”, `degraded` “일부 기능 확인 필요”, `unavailable` 또는 전송 실패 “연결 불가”. 인증 전에는 components·모델 정보를 추측하지 않는다. 다시 확인은 GET만 수행한다. |
| SC-01-C 연결 결과·오류 | bootstrap 응답·`ErrorResponse.error` | 성공한 cookie 교환 뒤 코드 입력을 지우고 프로젝트/기존 세션을 조회한다. 인증 성공을 모델 설정 완료로 표시하지 않는다. 실패·화면 이탈 시에도 코드를 저장하지 않는다. |

| 상황 | 문구·허용 행동 |
| --- | --- |
| 초기/처리 중 | “실행 창에 표시된 일회용 코드를 입력하세요.” / “연결 확인 중…”. 연결 중 재제출 차단, 서비스 다시 확인은 진행 중 중복 GET만 제한. |
| 잘못됨·재사용 / 만료 | `BOOTSTRAP_CODE_INVALID`: “연결 코드를 다시 확인하세요.” / `BOOTSTRAP_CODE_EXPIRED`: “연결 코드가 만료됐습니다. 실행 창에서 새 코드를 확인하세요.” 새 코드 입력 후 연결. |
| 인증 만료·서비스 중지 | “연결 인증이 만료됐습니다” 또는 “로컬 서비스를 시작한 뒤 다시 확인하세요.” 진행 중 run을 취소/실패로 바꾸지 않고 재인증 후 snapshot으로 복구한다. |

접근성: 입력에 형식 안내와 오류를 연결하고 실패 시 코드 입력으로 초점을 돌린다. 성공 후 복구한 화면 제목으로 이동한다. 코드 값을 상태 알림으로 읽어 주지 않는다.

<a id="sc-02"></a>

### SC-02 프로젝트 등록·색인

목적: 프로젝트를 등록하고 검색 가능한 색인의 준비 여부를 확인한다. 사례 UI-03~UI-06/UI-12/UI-33.

| 요소·와이어프레임 라벨 | 표시 필드·API 출처 | 입력 규칙·버튼 활성·조작 |
| --- | --- | --- |
| SC-02-A 프로젝트 선택 / 다음 목록 | `GET /workspaces`, `GET /workspaces/:id`: `Workspace.display_name/index_status/index_revision/supported_languages`; 목록 `items/page` | 조회한 workspace만 선택한다. `index_revision=null`은 “색인 없음”. 다음 목록은 `has_more`와 cursor가 있을 때 활성. 새로고침 뒤 선택 ID를 GET으로 재확인한다. |
| SC-02-B 표시 이름·경로 / 등록 | `WorkspaceCreateRequest.display_name/root_path/idempotency_key` → `POST /workspaces` | 이름 1~120자, 경로 1~4096자. 브라우저가 서버 경로·symlink·권한을 검증했다고 가정하지 않는다. 요청 중 중복 등록 차단. 성공 후 입력 경로를 지우고 표시 이름으로 전환한다. |
| SC-02-C 색인 만들기·갱신 / 진행 | `POST /workspaces/:id/index`: `IndexRequest`; `GET /workspaces/:id/index`: `IndexStatusResponse` | 등록된 workspace에서 활성. POST 중·`queued/indexing`에는 중복 시작 금지, GET 상태 확인은 가능. 미확정 응답은 같은 키로 확인하며 SSE를 만들지 않는다. |
| SC-02-D 파일 수·버전·제외 목록 | `counts.discovered/indexed/skipped/failed`, `index_revision/pending_revision`, `diagnostics[].relative_path/reason_code/line`, `diagnostics_truncated` | 각각 발견/색인 성공/제외/실패 파일 수다. 심볼 개수·완료 백분율로 바꾸지 않는다. pending revision을 검색 중 revision으로 표시하지 않는다. 진단 50개 초과는 “진단 일부만 표시됨”. |
| SC-02-E 대화로 이동 | `IndexStatusResponse.searchable`와 확정 `index_revision` | 최신 상태에서 searchable=true와 revision이 있을 때 코드 질문 준비 가능. `ready` 문자열만으로 활성화하지 않는다. 모델/보호 기능 점검은 SC-09, 기존 이력 열람은 항상 별도 허용한다. |

| 서버 상황 | 표시·복구 |
| --- | --- |
| `not_indexed`, `queued`, `indexing`, `parsed` | “색인 없음”, “색인 대기 중”, “색인 중”, “분석 완료·검색 준비 중”. parsed를 준비 완료로 표시하지 않는다. |
| `ready`, `partial` | “색인 처리 완료”, “일부 파일 제외”. 항상 searchable를 함께 본다. `ready + searchable=false + indexed=0` fixture는 “검색할 코드 심볼이 없습니다”; 자료 등록/파일 확인 안내. partial은 성공·실패 수와 원인을 함께 표시한다. |
| `stale`, `failed` | “파일 변경·색인 갱신 필요”, “색인에 실패했습니다”. 기존 선택을 보류하고 파일 수정 후 갱신. 이전 revision은 서버가 searchable와 revision으로 유효성을 확인한 범위만 사용한다. |
| 진단 이유 | `syntax_error` 구문 오류, `encoding_error` 문자 해석 실패, `unsupported_language` 지원 언어 아님, `too_large` 크기 초과, `excluded` 제외 규칙, `path_rejected` 허용되지 않은 경로. 위치와 수정·등록 자료로 전환 행동을 표시한다. |
| 목록 없음·오류·연결 끊김 | “등록된 프로젝트가 없습니다”와 등록 버튼. 오류는 4절에 따라 입력 수정/다시 확인; 단절 중 이미 시작된 색인을 재시작하지 않고 GET으로 복구한다. |

접근성: 파일 수는 의미 있는 이름과 함께 읽고 총량이 없으면 무한 진행 표시를 쓴다. 진단 목록에 키보드로 진입할 수 있게 하고 완료 알림은 한 번 전달한다. 색인 지원 언어와 심볼 범위 안내는 SCREEN_SPEC을 재사용한다.

<a id="sc-03"></a>

### SC-03 대화·코드 작업

목적: 질문·실행·도구 결과를 보고 취소하거나 연결을 복구한다. 사례 UI-07~UI-12/UI-14/UI-17/UI-31/UI-34.

| 요소·와이어프레임 라벨 | 표시 필드·API 출처 | 입력 규칙·버튼 활성·조작 |
| --- | --- | --- |
| SC-03-A 프로젝트/세션 / 새 대화 | workspace 표시 이름, `GET /workspaces/:id/sessions`, `GET /sessions/:id`: `Session.session_id/status/active_run_id/last_run_id/created_at`; `POST /sessions` | 세션 제목 필드는 없으므로 생성 시각과 짧은 식별 표시를 사용한다. 새 대화는 사용자 명시 조작, 현재 scope·SC-09 실행 준비 확인 후 1회 생성. 닫힌 세션은 열람만 가능. 세션 전환은 기존 실행 취소가 아니다. |
| SC-03-B 질문 / 전송 | `RunCreateRequest.prompt/idempotency_key/context_refs` → `POST /sessions/:id/runs` | 질문 1~32000자, 공백뿐이면 불가, refs 최대 32개. active 세션·동시 run 없음·검색 가능 색인·설정/보호 준비·유효 선택일 때 활성. 전송/응답 확인 중 재제출 차단. pointer의 범위 선택 전달은 **G-01** 해소 전 비활성. |
| SC-03-C 이력·답변 | `GET /sessions/:id/runs`의 `RunSummary`; `GET /runs/:id`의 `prompt_preview`, `answer.text/truncated`, `status/terminal`; `run.output_delta` | 복구된 질문은 원문 전체가 아닌 미리보기임을 표시한다. snapshot 답변은 최대 65536자. truncated면 “답변 일부만 표시됨”; 없는 전체 답변 조회 API를 호출하지 않는다. 출처 연결은 **G-07** 전 텍스트에서 임의 추출하지 않는다. |
| SC-03-D 도구 이력·저장된 결과 | `tool_calls[].tool_name/phase/summary/output_pointer/output_bytes`, `tool_calls_truncated`; `run.tool_call_updated`, `run.pointer_created` | 요약을 표시하고 output_pointer가 있으면 SC-06/SC-07 진입점을 제공한다. 작은 출력도 별도 raw 필드가 없으므로 요약만 표시한다. 50개 초과 이력은 “도구 이력 일부만 표시됨”. descriptor 조회 연결은 **G-02**. |
| SC-03-E 취소 요청 | `POST /runs/:id/cancel` → `RunSnapshot` | 확인된 `queued/running/awaiting_approval` 실행에서 활성. 클릭 즉시 중복 취소·전송·승인 차단. `cancelling`/종료 상태에서는 비활성. 응답 유실 시 “취소 결과 확인 필요”, 연결 후 snapshot 조회. |
| SC-03-F 연결 상태·복구 | SSE와 `GET /runs/:id`, `replay` | 단절 시 “연결이 끊겼습니다. 작업은 계속될 수 있습니다.” 새 실행/승인/변경 요청 차단, 입력 초안·기존 결과 유지. 복구 동작은 5절. |

| 서버 상황 | 표시·복구 |
| --- | --- |
| run `queued/running/awaiting_approval/cancelling` | “실행 대기 중” / “실행 중” / “승인 대기 중” / “취소 요청 중”. 로컬 클릭만으로 완료·취소됨으로 바꾸지 않는다. |
| run `completed/failed/cancelled` | “완료” / “실패” / “취소됨”. `terminal.status/finished_at/reason_code/message`와 일치해야 한다. 늦은 진행·답변 이벤트로 종료 상태가 돌아가지 않는다. 실패/취소 전 답변은 “중단 전 결과”. 이미 실행된 수정·명령의 자동 복원을 약속하지 않는다. |
| 도구 `requested/awaiting_approval/running/completed/failed/rejected/cancelled` | “요청됨” / “승인 대기” / “실행 중” / “완료” / “실패” / “거절됨” / “취소됨”. 도구 하나의 완료/거절을 run 종료로 확장하지 않는다. |
| 빈 대화·빈 답변·관련 코드 없음 | “질문을 입력해 시작하세요.” 종료됐지만 answer.text가 비어 있으면 “표시할 답변이 없습니다”와 도구 이력/종료 결과를 표시한다. 검색 NO_MATCH는 “관련 코드 근거 없음”; 새 실행·전체 파일 전송을 자동으로 하지 않는다. |
| 실행 오류·보호 실패 | 4절의 안전한 메시지와 request_id를 표시한다. 결과 확인→입력/설정 수정→사용자가 새 작업 시작 순서로 복구. 포인터 저장 실패 시 큰 원문 직접 전달로 우회하지 않는다. |

접근성: 질문 입력에서 한글 조합 중 Enter로 전송하지 않는다. 여러 줄 입력은 Shift+Enter, 전송은 조합 종료 후 Enter 또는 버튼으로 동일하게 처리한다. 새 답변은 묶어서 알리고 사용자가 위를 읽으면 자동 스크롤을 멈춘다. 취소 버튼은 키보드와 좁은 화면에서도 유지한다.

<a id="sc-04"></a>

### SC-04 실행 승인

목적: 요청한 한 건의 효과를 확인해 승인하거나 거절한다. 사례 UI-13/UI-14/UI-15/UI-33.

| 요소·와이어프레임 라벨 | 표시 필드·API 출처 | 입력 규칙·버튼 활성·조작 |
| --- | --- | --- |
| SC-04-A 종류·대상·내용 | `RunSnapshot.pending_approvals[]` 또는 `run.approval_requested.payload.approval`: `review.kind/summary/content/target_paths/content_truncated/reviewable` | command “명령 실행”, file_change “코드 수정”, other “기타 도구 요청”. 상대 대상 경로와 검토 텍스트만 표시. target_paths가 없으면 전체 프로젝트/경로를 추정하지 않는다. 효과를 확인할 수 없으면 승인 불가. |
| SC-04-B 남은 시간·결정 상태 | `approval_id/run_id/tool_call_id/status/requested_at/expires_at/decided_at` | pending “결정 대기”, approved “승인됨”, rejected “거절됨”, expired “승인 기한 만료”, cancelled “승인 요청 취소됨”. 승인됨은 실제 도구 완료와 다르다. |
| SC-04-C 이번 요청 승인 | `POST /runs/:id/approvals/:approval_id`, `ApprovalDecisionRequest.decision=approve`, 원본 `input_digest` | 현재 run·pending·미만료·연결 확인·결정 요청 중 아님·run 취소/종료 아님·reviewable=true·content_truncated=false 모두 필요. 입력 digest를 UI에서 재계산/수정하지 않는다. 검토 내용 상한은 schema의 16384자이며 bytes와 혼동하지 않는다(**G-06**). |
| SC-04-D 거절 / 닫기 | 같은 API의 `decision=reject`, 선택 `reason` 최대 500자; 닫기는 요청 없음 | 거절은 pending·현재 run·미만료·연결 확인 때 가능하며 검토 내용이 잘렸어도 허용한다. 응답 대기 중 두 결정 버튼 잠금. 닫기/Escape는 결정하지 않으며 대화 카드가 남는다. |

| 상황 | 문구·복구 |
| --- | --- |
| 조회 중·대기 요청 없음 | snapshot 확인 중에는 “승인 요청을 확인하는 중…”과 결정 버튼 잠금. 확인된 pending_approvals가 비었으면 “대기 중인 승인 요청이 없습니다”. 빈 목록을 이전 결정의 승인/거절 이력으로 해석하지 않는다. |
| 대기/결정 중 | “승인 전에는 실행되지 않습니다.” / “결정 결과 확인 중…”. 포괄 승인·항상 승인 옵션 없음. |
| 검토 불가 | “전체 작업 내용을 확인할 수 없어 승인할 수 없습니다.” 더 작은 작업 요청 안내, 거절 가능. “상세 확인”은 받은 content를 크게 볼 뿐 없는 추가 조회를 수행하지 않는다. |
| 만료·입력 변경·이미 처리됨 | “승인 기한이 지났습니다” / “작업 내용이 바뀌었습니다. 새 승인 요청을 확인하세요” / “이미 처리된 요청입니다”. 오래된 요청으로 실행하지 않는다. 새 snapshot으로 확인한다. |
| 단절·응답 유실·종료 | 결정 성공/실패를 추정하지 않고 두 결정 버튼을 잠근다. 복구 후 snapshot의 pending 요청만 다시 검토할 수 있다. pending에서 사라졌다는 이유만으로 “승인됨”으로 단정하지 않는다(**G-07**). |

접근성: 상세 대화상자를 열 때 제목이나 검토 내용에 초점을 두고 승인 버튼을 기본 선택하지 않는다. 만료 카운트다운을 초마다 읽지 않으며 만료 사실만 알린다. 결정 뒤 도구 실행 상태를 별도로 읽을 수 있어야 한다.

<a id="sc-05"></a>

### SC-05 관련 코드·출처

목적: 지원 언어의 관련 코드를 찾고 제한된 원문·정적 참조를 검토한다. 사례 UI-09/UI-16/UI-17/UI-22/UI-31.

| 요소·와이어프레임 라벨 | 표시 필드·API 출처 | 입력 규칙·버튼 활성·조작 |
| --- | --- | --- |
| SC-05-A 질문/식별자 / 찾기 | `SymbolSearchRequest.query/workspace_id/index_revision/page`; 결과 `SymbolSearchResponse.candidates/page/no_match` | query 1~2000자, 빈 검색 불가. 현재 searchable 색인·revision 필요. 공개 API 연결은 **G-04**; `/internal/v1/symbols/*`를 브라우저가 호출하지 않는다. |
| SC-05-B 후보 행 | `SymbolCandidate.primary.qualname/kind/relative_path/start_line/end_line`, `score/depth/index_revision`, `estimated_tokens.token_count/count_mode` | 함수/비동기 함수/클래스/상수 표시. 점수는 0~1의 동일 검색 내 관련도이고 정답 확률이 아니다. depth 최대 3. 예상 토큰은 숫자 단일 필드가 아닌 객체다. |
| SC-05-C 원문 / 범위 열기 | `SymbolBundle.fragments[].content/start_line/end_line/provenance.relative_path/content_sha256/pointer`; bundle `token_count` | bundle 요청은 candidate_id·index_revision·max_tokens, max_bytes≤32768. 실제 fragment 위치만 표시. provenance.pointer=null이면 자료 부분 읽기 링크 비활성; bundle 텍스트는 표시 가능. 공개 연결 **G-04**. |
| SC-05-D 선택·제외 이유 | `SymbolContextRef.kind/candidate_id/index_revision`; `SymbolBundle.omissions/unresolved_references` | 후보 선택은 현재 revision에 고정, refs 합계 32개 이하. “선택 요청”과 ContextPlan의 실제 반영은 구분. stale/삭제/권한 오류 후보는 선택 불가. |

| 상황 | 문구·복구 |
| --- | --- |
| 검색 중·초기 | “관련 코드를 찾는 중…” / “함수명이나 파일명을 포함해 검색하세요.” 기존 결과는 수정 전 질의에 대한 것임을 표시한다. |
| `no_match.hint` | try_identifier_or_file_name “관련 코드를 찾지 못했습니다. 함수명이나 파일명을 포함해 보세요”; index_not_ready “색인을 준비한 뒤 다시 검색하세요”; unsupported_language_only “색인할 수 있는 파일이 없습니다. 다른 파일은 자료로 등록하세요”와 지원 언어 목록. 정상 무결과이며 LLM 재검색 버튼 없음. |
| bundle 누락 | budget_exceeded “예산 부족”, depth_limit “참조 깊이 한도”, duplicate “중복”, too_large “원문 크기 초과”, stale_revision “이전 버전”. ContextPlan의 제외 enum과 혼합하지 않는다. |
| 참조 미확인 | dynamic_import “동적 가져오기”, dynamic_dispatch “실행 중 결정되는 호출”, not_found “정적 참조를 찾지 못함”, outside_workspace “프로젝트 밖 참조”, unsupported_language “지원 언어 아님”. 모두 “확인하지 못한 참조” 아래에 표시한다. |
| 버전 변경·오류 | 이전 원문은 “이전 버전·전달 불가”. 색인 갱신→다시 검색→사용자 재선택. 4절에 따라 읽기 불가·권한·예산 복구 제공. |

접근성: 체크박스 이름에 심볼·파일·줄을 포함한다. 원문은 읽기 가능한 텍스트이며 메서드가 클래스 단위로 반환될 수 있음을 함께 안내한다. 다음 결과 클릭 후 목록 시작으로 무조건 초점을 이동하지 않는다.

<a id="sc-06"></a>

### SC-06 등록 자료·실행 결과 목록

목적: 등록 자료와 세션의 저장 결과를 구별하고 부분 읽기·등록 해제·삭제로 이동한다. 사례 UI-18~UI-22/UI-24/UI-34.

| 요소·와이어프레임 라벨 | 표시 필드·API 출처 | 입력 규칙·버튼 활성·조작 |
| --- | --- | --- |
| SC-06-A 탭·필터·다음 목록 | `GET /workspaces/:id/pointers` 예정, `PointerDescriptor.kind/workspace_id/session_id` | 목록 envelope·kind/session/filter 입력·pagination은 **G-02**. 확정 전 필터 파라미터/목록 응답을 가정하지 않는다. runtime은 현재 세션만, source는 workspace 범위. |
| SC-06-B 자료 행·preview | `pointer/revision/media_type/byte_size/preview/available_operations`, runtime `expires_at`, `provenance.created_at/origin/truncated_before_storage` | 자료명·상대경로 필드가 없으므로 **G-02** 전 fixture 화면은 “등록 자료”/“실행 결과”와 구별용 순번 사용. origin은 경로가 아니다. 저장 전 잘림=true면 “저장되기 전 일부가 잘린 결과”. |
| SC-06-C 자료 등록 / PDF 등록 | `POST /workspaces/:id/sources` 예정; 응답 관련 `SourceRegistration` | 로컬 파일/디렉토리를 사용자가 직접 지정. 요청 스키마·경로 상한·외부 경로 허용·디렉토리 부분실패·갱신은 **G-02**. 현재 실제 등록 버튼 비활성, “자료 등록 연결 준비 중”. PDF는 SC-08로 이동. |
| SC-06-D 부분 읽기 | 현재 descriptor의 `available_operations` | read가 있고 유효 scope·revision·미만료이면 SC-07로 이동. 없으면 “이 자료는 부분 읽기를 지원하지 않습니다”. read/search 지원이 selector 목록을 뜻하지는 않는다(**G-02**). |
| SC-06-E 등록 해제 / 저장 결과 삭제 | `DELETE /pointers` 예정 | 확인 대화상자는 아래 문구. JSON body의 pointer+scope 및 성공 응답은 **G-02**. 확정 전 실행하지 않는다. 실패/응답 유실이면 행을 성공한 것처럼 지우지 않는다. |

| 상황 | 문구·복구 |
| --- | --- |
| 로딩·빈값·필터 무결과 | “자료 목록을 불러오는 중…” / “등록된 자료가 없습니다” / “이 세션에 저장된 실행 결과가 없습니다” / “조건에 맞는 자료가 없습니다”. 마지막은 필터 해제 제공. |
| Source 확인 | 제목 “자료 등록 해제”, 설명 “등록을 해제하고 파생 캐시를 지웁니다. 원본 파일은 유지됩니다.” 버튼 “등록 해제”와 “돌아가기”. |
| Runtime 확인 | 제목 “저장 결과 삭제”, 설명 “이 세션에 저장된 실행 결과를 삭제합니다. 이후 읽을 수 없습니다.” 버튼 “저장 결과 삭제”와 “돌아가기”. |
| 해제/삭제 성공 | 서버 성공 확인 후 행·열린 조회·선택·예산 preview를 무효화한다. 대화에는 “더 이상 읽을 수 없는 자료” 참조만 남긴다. 원본 파일 삭제나 실행 효과 취소를 의미하지 않는다. |
| 만료·삭제·권한·용량 | 4절 문구와 유효 자료 재선택/저장 공간 정리. 다른 세션 결과의 존재·preview·이름을 노출하지 않는다. TTL이 지난 runtime은 반복 조회로 복구되지 않는다. |

접근성: 탭 이름에 자료 종류, 삭제 버튼에 대상의 안전한 표시명을 포함한다. 확인 창의 기본 초점은 설명/돌아가기. 행 삭제가 확인되면 다음 행이나 목록 제목으로 초점을 복구한다.

<a id="sc-07"></a>

### SC-07 부분 읽기·검색

목적: 필요한 범위만 읽고 검색한 뒤 실제 반환 범위를 선택한다. 사례 UI-22~UI-26/UI-31/UI-33.

| 요소·와이어프레임 라벨 | 표시 필드·API 출처 | 입력 규칙·버튼 활성·조작 |
| --- | --- | --- |
| SC-07-A 범위 종류·범위 / 범위 읽기 | `POST /pointers/read`: `PointerReadRequest.schema_version/pointer/selector/max_bytes/max_tokens/cursor` | UI는 최초 읽기에 명시 selector·cap을 보낸다. line/pdf_page: 시작≥1·끝 포함, byte: 시작≥0·끝 제외. UI는 start/end를 모두 입력받고 정수·end≥start(line/page), end>start(byte)를 검사한다. 숫자 누락·NaN·무한대는 제출 불가. |
| SC-07-B section·JSON 경로 | `SectionSelector.section`, `JsonPathSelector.path` | 비어 있지 않은 문자열. JSON은 8 MiB 이하 구조 조회만 목표 범위. 지원 매체 조합·경로 문법·section 검색법은 **G-02** 전 비활성. 임의 JSON path 문법을 새로 정의하지 않는다. |
| SC-07-C 최대 크기·토큰 | read/search 스키마 | max_bytes 1~16384, max_tokens 1~32768. 현재 요청 가능한 byte 상한은 **16 KiB**이며 로드맵의 32 KiB와 차이가 있다(**G-06**). 단위를 분리하고 서버가 더 낮은 상한을 확정하면 작은 값 적용. 원문 전체로 기본 확대하지 않는다. |
| SC-07-D 원문·버전·출처 | `PointerReadResult.content/provenance.media_type/byte_size/revision/truncated/next_cursor/token_count/count_mode` | revision은 최상위가 아닌 provenance 안이다. 반환 범위·상대 파일·PDF page/hash/parser 정보는 없음(**G-03**). 요청 범위는 “요청한 범위”, 실제 범위는 “반환 범위 확인 불가”로 구별한다. byte_size를 실제 반환 bytes로 가정하지 않는다. |
| SC-07-E 검색 / 다음 결과 | `POST /pointers/search`: `PointerSearchRequest.query/limit/cursor/max_bytes/max_tokens`; `PointerSearchResult.matches[].line/content/byte_offset` | query 1~256자, limit 1~100(화면 기본 20). search 지원 자료에서 활성. 검색어는 문자 패턴으로 취급하고 명령으로 실행하지 않는다. 결과 line은 1부터, byte_offset은 0부터. 새 질의·범위·pointer에서는 이전 cursor 폐기. |
| SC-07-F 다음 부분 / 현재 범위를 전달할 자료에 선택 | read/search `next_cursor`; 실행의 `PointerContextRef` | 다음은 cursor가 있을 때만 활성, 동일 pointer·질의·revision·연산 유지. 한 번에 현재 부분을 교체하고 무제한 누적하지 않는다. 실제 범위 provenance와 실행 ref의 selector가 없으므로 **G-01/G-03** 해소 전 모델 선택 비활성. pointer만 선택해 파일 전체로 바꾸지 않는다. |

| 상황 | 문구·복구 |
| --- | --- |
| 로딩·빈 읽기·무결과 | “요청한 범위를 읽는 중…” / “이 범위에 표시할 텍스트가 없습니다” / “일치하는 내용을 찾지 못했습니다”. 검색 `matches=[]`는 정상 결과이며 no_match 객체를 요구하지 않는다. |
| 일부 반환 | truncated=true면 “일부 반환됨”. cursor 있음은 다음 부분 제공; cursor 없음은 “이 요청에서 더 읽을 수 없습니다”와 범위 수정. cursor만 있어도 다음 조작 표시. 반환량으로 파일 전체를 읽었다고 추측하지 않는다. |
| 원본 변경 | `SOURCE_CHANGED`: “원본이 변경됐습니다. 갱신 후 다시 읽고 선택하세요.” 이전 content를 최신으로 표시하지 않고 cursor·선택·preview 폐기. 갱신 API는 G-02. 서로 다른 revision을 이어 붙이지 않는다. |
| 범위·권한·만료·크기 오류 | 4절에 따라 입력 수정·유효 자료 선택·작은 범위 읽기. byte 범위가 UTF-8을 자르면 서버의 유효한 부분 결과와 truncated를 따르며 깨진 문자를 원문으로 표시하지 않는다. |

접근성: 시작/끝 입력에 단위·포함 여부를 별도 label로 제공한다. 원문 제목에 자료 종류·버전을 붙이고 복사/탐색은 텍스트 범위 안에서 가능하게 한다. 다음 부분 후 변경 사실을 한 번 알리되 초점을 빼앗지 않는다.

<a id="sc-08"></a>

### SC-08 PDF 등록·파싱

목적: 텍스트 PDF를 등록하고 페이지 추출 상태·부분 실패·페이지 읽기를 확인한다. 사례 UI-27/UI-28/UI-29/UI-33.

| 요소·와이어프레임 라벨 | 표시 필드·API 출처 | 입력 규칙·버튼 활성·조작 |
| --- | --- | --- |
| SC-08-A PDF 경로 / 등록 후 페이지 추출 | 자료 등록 후 `POST /pdf/parse` 예정 | 파일 경로를 사용자가 명시한다. source 등록과 parse 성공을 분리한다. 등록 요청은 G-02, parse 요청·중복 방지·job 응답은 **G-05**로 보완 대기. 실제 제출은 비활성, “PDF 처리 연결 준비 중”. |
| SC-08-B 문서명·진행·제외 페이지 | `GET /pdf/jobs/:job_id` 예정 | job ID·상태·진행·전체 페이지·부분 실패의 **스키마와 fixture가 없다**. UI 설계 라벨은 준비 중/추출 중/완료/일부 페이지 제외/실패이며 wire enum을 뜻하지 않는다. 확인된 총량만 분모로 사용한다. |
| SC-08-C 페이지 / 페이지 읽기 | 확정된 `PdfPageSelector.type=pdf_page/start/end` → SC-07 | 양끝 포함 1부터의 정수 범위. 추출 완료한 유효 페이지 확인 후 활성해야 하나 job·페이지 provenance는 G-03/G-05. 확인 전 추출 성공·실제 페이지 출처를 만들지 않는다. |
| SC-08-D 원본 확인 후 다시 처리 / 등록 해제 | job 재조회·재처리 및 Source 등록 해제 예정 | 응답 유실·새로고침은 같은 job 조회로 복구하는 것이 요구다. 자동 재파싱하지 않는다. 재시도 입력·중복 보장은 G-05, 해제는 G-02. |

| 설계 상황 | 표시·복구 요구(응답 계약 확정 후 연결) |
| --- | --- |
| 파일 미지정·상태 조회 중 | “텍스트가 포함된 PDF를 선택하세요.” 입력/계약 준비 전 제출 비활성. 기존 job 조회 중에는 “추출 상태를 확인하는 중…”과 직전 결과의 오래된 표시를 유지한다. |
| 스캔·빈 자료 | “추출할 텍스트가 없습니다. 텍스트가 포함된 PDF를 선택하세요.” 일부 빈 페이지는 사용 가능 페이지와 구분한다. OCR·외부 업로드 기능 없음. |
| 손상·암호화·상한 초과 | “PDF를 읽지 못했습니다” / “암호화된 PDF는 지원하지 않습니다” / “PDF 처리 한도를 초과했습니다”. 다른 자료 선택·원본 확인·자료 축소 안내. 실제 reason 값은 현재 `PARSE_FAILED` 하나로 세분화할 수 없음(G-05). |
| 부분 성공 | 파서가 사용 가능 페이지와 실패 페이지를 보장할 때만 “일부 페이지 제외”. 근거가 없으면 완료로 표시하지 않는다. 초기 설계 한도 50 MiB/500페이지는 서버 설정 키 확정 전 실행 중 실제 값으로 표시하지 않는다(G-06). |
| 원본/parser 변경·단절 | 이전 페이지 캐시·선택 무효화→현재 원본 재확인→명시적 재처리. 연결 복구는 job GET이며 가짜 run SSE를 만들지 않는다. |

접근성: 등록과 추출의 결과를 따로 읽어 주고 제외 페이지 목록은 키보드로 탐색한다. 진행률을 모르면 수치 대신 단계 문구를 사용한다. G-05 미해결 상태에서 사용 가능한 파서처럼 표시하지 않는다.

<a id="sc-09"></a>

### SC-09 전달할 자료·모델 설정 상태

목적: 선택한 자료와 실제 반영 내역·입력 예산·실행 준비 상태를 확인한다. 사례 UI-10/UI-17/UI-22/UI-24/UI-30/UI-31/UI-32.

| 요소·와이어프레임 라벨 | 표시 필드·API 출처 | 입력 규칙·버튼 활성·조작 |
| --- | --- | --- |
| SC-09-A 선택 목록·원문·제외 이유 | `ContextPlan.selected[].candidate_id/ref/score/explicit/estimated_tokens`, `fragments[].candidate_id/ref/content/token_count`, `omitted[].candidate_id/reason`, 선택적 `index_revision` | explicit=true는 “직접 선택”. false만으로 이번 작업 자료/R0 우선순위를 판별하지 않는다. selected에 있다는 이유만으로 대응 fragment가 없는 원문까지 전송됐다고 표시하지 않는다. 상세 provenance·우선순위·중복 이유는 **G-04**. |
| SC-09-B 입력 예산 | `ContextPlan.budget.budget_tokens/used_tokens/count_mode`; `run.context_planned`의 최상위 `budget_tokens/used_tokens/count_mode/selected_count/omitted_count/index_revision` | ContextPlan에는 최상위 used_tokens/count_mode가 없다. preview와 run 이벤트의 수치를 섞지 않는다. 0/0은 빈 예산 표기, 0으로 나누지 않는다. 합계·예산 불변식 위반 응답은 실행 가능 표시 금지. |
| SC-09-C 선택 해제·범위 줄이기 / 미리보기 갱신 | `POST /context/preview` 예정 | 질문·선택이 바뀌면 이전 preview는 갱신 필요. 선택 해제는 지역 조작, 범위 줄이기는 SC-07. preview 요청·scope·R0 후보 연결은 **G-04** 전 실제 제출 비활성. preview 성공은 실행 승인/최종 gate 통과가 아니다. |
| SC-09-D 모델·제공자 | `GET /settings`: `provider.provider_id/model_id/configured/reason_code` | 반환 식별자를 그대로 모델 표시명으로 사용. configured는 서버에 키가 있다는 뜻이며 연결 성공·지원 보장이 아니다. “설정됨”/“미설정”과 reason 문구를 분리한다. 키·모델 변경 입력란 없음. |
| SC-09-E 모델 한도·검증·보호 기능 | settings `budget.context_limit_tokens/max_output_tokens/safety_margin_tokens/body_count_mode/final_request_gate`, `protections[].name/ready/reason_code`; `GET /health.components` | 최종 gate enforced “전송 전 검사 적용”, not_verified “전송 전 검사 미검증”, unavailable “전송 전 검사 사용 불가”. 보호 5종이 빠짐없이 ready이고 provider 설정·관련 서비스·계수 지원이 확인돼야 실행 준비. gate 미검증/불가면 보호된 실행은 차단한다. |
| SC-09-F 제품 한도 / 설정 상태 다시 확인 / 실행 안내 | settings `limits`, health `status/components`; [실행 안내](../../README.md) | limits는 이름 없는 정수 map이므로 임의 키/단위/TTL을 해석하지 않는다(**G-06**). 설정 다시 확인은 GET만 수행, 서버에서 설정을 바꾼 뒤 재조회. 설정 실패를 0개 한도/설정됨으로 바꾸지 않는다. |

| 상황 | 문구·복구 |
| --- | --- |
| 로딩·빈 선택 | “전달할 자료를 확인하는 중…” / “직접 선택한 자료가 없습니다”. 빈 명시 선택은 오류가 아니다. 후보·이력·고정 입력 비용이 0이라는 뜻도 아니다. |
| 제외 enum | no_match “일치하는 자료 없음”, stale “버전 변경”, unauthorized “사용 권한 없음”, over_budget “예산 부족”. 중복 제외는 현 enum에 없으므로 UI에서 duplicate를 추가하지 않는다(G-04). |
| 계수 방식 | exact “동일 토크나이저로 계수”, provider_estimate “제공자 추정값”, provider_reported “제공자가 응답 후 보고한 값”. 본문 계수가 exact여도 최종 요청 전체 한도 보장을 뜻하지 않는다. 현재 계획은 provider_estimate 기준. |
| 예산 초과·계수 미지원 | “입력 한도를 초과했습니다. 자료 범위를 줄이거나 선택을 해제하세요.” 이력만 초과하면 새 대화 안내. 계수 미지원은 “이 모델의 입력 크기를 확인할 수 없습니다”와 서버 지원 설정 확인. 자동 요약·길이/4 대체·명시 선택 한도 우회 없음. |
| 고정 비용·누적 사용량 | 이력/system/tool schema/overhead 세부 비용·세션 누적 사용량은 현 ContextPlan에 없다. 도표를 임의 분해하지 않고 “세부 예산 제공 전”으로 안내(G-04). settings의 출력 예약·여유분은 plan의 실측 사용량과 따로 표시한다. |
| component 상태 | ok “사용 가능”, degraded “일부 기능 제한”, unavailable “사용 불가”, not_configured “설정 필요”, not_implemented “준비 중”. 미지원 기능을 활성화하지 않는다. 모델 미설정이어도 프로젝트·자료 준비는 각 서비스 준비 범위에서 가능하다. |

보호 기능 표시명은 runtime_pointer_hook “큰 실행 결과 보관”, model_request_gate “입력 예산 검사”, approval_broker “실행 승인”, tool_allowlist “허용 도구 제한”, checkpoint_disabled “자동 Git 변경 방지”다. 구현 식별자는 기본 화면 문구로 사용하지 않는다. 계수·보호 정보가 없는 경우 준비 완료로 추측하지 않는다.

접근성: 예산 막대에는 사용량·한도·계수 방식을 텍스트로 함께 제공한다. 제외 이유를 색상만으로 표시하지 않는다. 설정 탭을 열 때 API 키가 아닌 설정 여부만 읽어 준다.

## 4. 오류 문구·HTTP·복구 대응

아래 HTTP/기본 retryable은 `error-codes.json`과 대응한다. **재시도 가능**은 동일 요청이 성공할 가능성에 관한 서버 정보다. POST 실행·승인·삭제를 자동 반복하지 않는다. 응답의 `retryable=false`나 입력/설정 변경 필요 조건을 우선한다. `TOKENIZER_UNAVAILABLE`은 키 미설정 등 사유에 따라 false가 올 수 있다. 서버 연결 자체가 실패해 ApiError가 없으면 request_id를 만들어 내지 않는다.

| code | HTTP | 기본 retryable | 사용자 문구·다음 행동 | 주 화면 |
| --- | --- | --- | --- | --- |
| INVALID_POINTER | 400 | false | “이 자료 참조를 사용할 수 없습니다.” 목록에서 유효 자료를 다시 선택하고 이전 cursor를 버린다. | SC-06, SC-07 |
| NOT_FOUND | 404 | false | “요청한 항목을 찾을 수 없습니다.” 목록/실행 상태 재확인, 없어진 자료 선택 해제. 삭제됐다고 단정하지 않는다. | SC-02, SC-03, SC-06, SC-07 |
| EXPIRED | 410 | false | “실행 결과의 보관 기한이 지났습니다.” 읽기·선택 차단, 다른 자료 선택. 자동 재실행 없음. | SC-06, SC-07, SC-09 |
| FORBIDDEN | 403 | false | “이 항목에 접근할 수 없습니다.” 현재 프로젝트·세션의 자료 선택. 다른 scope의 내용·존재 정보는 숨긴다. | SC-02, SC-04, SC-06, SC-07 |
| SOURCE_CHANGED | 409 | false | “원본이 변경됐습니다. 갱신 후 다시 선택하세요.” cursor·선택·preview 무효화, 색인/등록 자료 갱신. | SC-02, SC-05, SC-07, SC-08, SC-09 |
| INVALID_SELECTOR | 400 | false | “읽을 범위를 확인하세요.” 단위·시작/끝·지원 연산을 수정하고 새 cursor 없이 읽는다. | SC-07 |
| UNSUPPORTED_FORMAT | 415 | false | “이 형식은 해당 읽기 작업을 지원하지 않습니다.” 지원 형식/연산 선택. PDF 상세 원인은 G-05. | SC-06, SC-07, SC-08 |
| UNSUPPORTED_LANGUAGE | 422 | false | 작업 공간의 색인 지원 언어를 표시하고 다른 언어의 파일은 자료 등록으로 안내. | SC-02, SC-05 |
| PARSE_FAILED | 422 | false | “문서를 해석하지 못했습니다.” 원본 확인·다른 자료 선택. details.reason 자유 문자열을 성공/지원 enum으로 해석하지 않는다. | SC-02, SC-08 |
| NO_MATCH | 200 | false | “일치하는 내용을 찾지 못했습니다.” 식별자·파일명/검색어 변경. ErrorResponse가 아닌 정상 검색 결과. | SC-03, SC-05, SC-07 |
| BUDGET_EXCEEDED | 413 | false | “요청 범위나 입력 예산 한도를 초과했습니다.” 범위 축소·선택 해제, 이력 초과면 새 대화. | SC-03, SC-05, SC-07, SC-08, SC-09 |
| TOKENIZER_UNAVAILABLE | 503 | true | “입력 크기를 확인할 수 없습니다.” 설정 확인 또는 retryable인 일시 오류만 다시 확인. 계수 없이 전송 금지. | SC-03, SC-09 |
| SDK_UNAVAILABLE | 503 | true | “코드 작업 도구를 사용할 수 없습니다.” 로컬 서비스 확인, 기존 실행 조회 후 명시적 재시도. | SC-01, SC-03, SC-09 |
| PROVIDER_ERROR | 502 | true | “모델 요청에 실패했습니다.” 설정·연결 및 기존 실행 결과 확인 후 새 요청 판단. | SC-03, SC-09 |
| APPROVAL_REJECTED | 409 | false | “이 도구 요청을 거절했습니다.” 도구 거절 표시, run 최종 결과는 별도 확인. | SC-03, SC-04 |
| CANCELLED | 409 | false | “요청이 취소됐습니다.” 해당 요청 취소 표시, run 종료는 snapshot과 대조. | SC-03, SC-04 |
| UNAUTHENTICATED | 401 | false | “연결 인증이 만료됐습니다.” SC-01 재인증 후 기존 작업 복구. | 모든 화면 |
| BOOTSTRAP_CODE_INVALID | 401 | false | “연결 코드를 다시 확인하세요.” 재입력; 재사용 코드도 이 문구. | SC-01 |
| BOOTSTRAP_CODE_EXPIRED | 401 | false | “연결 코드가 만료됐습니다.” 실행 창의 새 코드 입력. | SC-01 |
| ORIGIN_REJECTED | 403 | false | “허용된 로컬 실행 주소에서 열어 주세요.” 실행 안내의 같은 origin으로 접속. | SC-01, SC-09 |
| VALIDATION_FAILED | 422 | false | “입력 내용을 확인하세요.” 확인 가능한 해당 입력에 오류 연결, 불명확하면 폼 상단 표시. 임의 details 필드명에 의존하지 않는다. | 모든 입력 화면 |
| PAYLOAD_TOO_LARGE | 413 | false | “요청 크기가 너무 큽니다.” 질문/선택/범위 축소. 조용히 잘라 재제출하지 않는다. | SC-03, SC-06, SC-07, SC-08 |
| QUOTA_EXCEEDED | 507 | false | “저장 공간 한도를 초과했습니다.” 불필요한 저장 결과 정리 또는 더 작은 자료 선택. 원본 삭제 안내 없음. | SC-03, SC-06, SC-08 |
| RUN_ALREADY_ACTIVE | 409 | true | “이 대화에 진행 중인 작업이 있습니다.” 검증한 active_run_id 또는 session GET으로 기존 run 복구. 새 키 자동 발급 금지. | SC-03 |
| IDEMPOTENCY_CONFLICT | 409 | false | “이전 요청과 내용이 다릅니다.” 기존 요청 결과를 확인한 뒤 사용자가 새 작업 시작. | SC-02, SC-03 |
| APPROVAL_EXPIRED | 410 | false | “승인 기한이 지났습니다.” 결정 잠금·snapshot 확인·새 요청 대기. | SC-04 |
| APPROVAL_DIGEST_MISMATCH | 409 | false | “작업 내용이 바뀌었습니다.” 기존 승인 폐기·새 요청 내용 검토. | SC-04 |
| APPROVAL_ALREADY_DECIDED | 409 | false | “이미 처리되거나 종료된 승인 요청입니다.” snapshot/이벤트 확인, 성공으로 추정하지 않음. | SC-04 |
| PROTECTION_UNAVAILABLE | 503 | true | “안전한 실행을 위한 준비가 끝나지 않았습니다.” SC-09 설정 상태 확인, 새 실행 차단. | SC-03, SC-09 |
| INDEX_NOT_READY | 409 | true | “검색할 색인이 아직 준비되지 않았습니다.” SC-02 상태 확인/색인. | SC-03, SC-05 |
| RATE_LIMITED | 429 | true | “요청이 많습니다. 잠시 후 다시 확인하세요.” 같은 요청 연속 클릭 차단, 지연 후 명시적 재확인. | 모든 조회·입력 화면 |
| SERVICE_UNAVAILABLE | 503 | true | “로컬 서비스에 연결할 수 없습니다.” 서비스 확인·재연결, 기존 작업 자동 재시작 없음. | 모든 화면 |
| NOT_IMPLEMENTED | 501 | false | “이 기능은 아직 준비 중입니다.” 관련 버튼 비활성, 재시도 반복 없음. owner_task는 개발 인계 정보이며 기본 사용자 화면에서 숨긴다. | 모든 화면 |
| INTERNAL_ERROR | 500 | false | “요청을 처리하지 못했습니다.” request_id와 상태 확인 제공, 실행 결과 미확정이면 재실행하지 않는다. | 모든 화면 |

알 수 없는 코드·schema_version·잘못된 응답은 “응답을 확인할 수 없습니다”로 표시하고 변경/실행 조작을 막는다. 원문 응답·stack trace를 UI에 덤프하거나 새 오류 코드를 wire에 추가하지 않는다. 다른 자료·scope·query의 pointer cursor는 INVALID_POINTER, 이전 Source revision의 cursor는 SOURCE_CHANGED로 처리하고 새 범위를 선택한다.

## 5. 이벤트·연결 복구의 관찰 가능한 요구

모든 AppEvent는 `schema_version/event_id/sequence/workspace_id/session_id/run_id/type/timestamp/payload`를 검증한다. 일반 이벤트 sequence는 run 안에서 1부터 증가한다. `event_id` 중복·이미 반영한 sequence는 같은 내용으로 다시 표시하지 않는다. scope가 다르면 현재 화면에 섞지 않는다.

| AppEvent.type | 표시하는 실제 payload | 사용자에게 보여야 하는 결과 |
| --- | --- | --- |
| run.status_changed | status, previous_status, terminal | 실행 상태와 종료 사실. 종료 3종 확정 후 진행 중으로 돌아가지 않음. |
| run.output_delta | message_id, text(최대 4096자) | 해당 run의 답변 조각을 한 번 표시. 원문 도구 출력으로 취급하지 않음. |
| run.tool_call_updated | tool_call | 같은 tool_call_id 행을 갱신. summary·pointer만 표시, raw output 없음. |
| run.approval_requested | approval | 해당 run의 승인 카드 1개, 중복 수신으로 카드/실행이 늘지 않음. |
| run.approval_resolved | approval_id, status, decided_at, reason_code | 해당 카드 결정 확정·버튼 잠금. 도구 완료 또는 run 종료로 대신 표시하지 않음. |
| run.pointer_created | pointer, kind, byte_size, tool_call_id | 저장 사실·결과 진입점. descriptor·원문은 이벤트에 없음. |
| run.context_planned | selected_count, omitted_count, used_tokens, budget_tokens, count_mode, index_revision | 현재 run의 개수·예산 요약. 전체 ContextPlan이나 출처 목록으로 확장하지 않음. |
| stream.replay_unavailable | requested_after_sequence, oldest_available_sequence | “최신 실행 상태를 확인하는 중…”. 일반 sequence 중복 규칙으로 버리지 않고 snapshot 확인. |

1. 단절 시 기존 결과에 연결 경고를 표시한다. 새 실행·승인·등록/삭제/파싱 요청을 막고 작업이 계속될 수 있음을 알린다. GET 실패를 빈 결과나 취소로 바꾸지 않는다.
2. 같은 origin SSE 재연결의 `Last-Event-ID`는 **SSE id에 실린 sequence의 10진수**다. JSON의 evt_ 형식 event_id와 다르다. replay로 요청·도구·승인을 다시 실행하지 않는다.
3. 순서 공백이 확인되면 불완전한 답변/승인을 최신으로 표시하지 않고 snapshot으로 재확인한다. 이미 반영된 늦은 이벤트는 중복으로 무시한다. 종료 확정 뒤의 늦은 이벤트도 종료를 되돌리지 않는다.
4. replay_unavailable에는 SSE id 줄이 없고 sequence는 현재 마지막 값이다. sequence가 작거나 같아도 복구 안내를 처리한다. `GET /runs/:id`의 snapshot으로 화면을 맞추고 `replay.last_sequence` 이후로 다시 구독한다. 새 구독은 같은 origin cookie를 사용하는 fetch 기반 SSE 소비에서 기존 계약의 `Last-Event-ID` 헤더로 이어 갈 수 있다. 기본 EventSource의 자동 재연결과 새 인스턴스 생성은 구별하며, 임의 query 이름을 추가하지 않는다. 라이브러리·구독 수명 구현은 1.3/1.4가 담당한다.
5. 새로고침은 workspace→session의 active_run_id(없으면 last_run_id)→run snapshot 순서로 복구한다. 새 run을 POST하지 않는다. snapshot 로딩이 끝나기 전 전송·승인 비활성. 대기 승인 목록에서 사라진 결정의 이력은 G-07 범위다.
6. 색인/PDF/설정은 각 GET으로 복구하며 run SSE에 얹지 않는다. 현재 PDF job 계약은 G-05로 막혀 있다. 조회 재시도 간격·구독 수명 등 구현 선택은 1.3이 정하며 중복 요청 방지·인증 실패 시 중지·scope 격리를 시험한다.

## 6. 구현 인계·검증 범위

1.2는 기존 계약 fixture의 **data**로 화면을 구성하고 UI_BEHAVIOR_CASES의 기대값과 대조한다. invalid fixture는 정상 화면 데이터가 아니라 검증 거부 시험의 입력이다. fixture의 scenario 메타데이터에는 2.1과 다른 번호가 있어 파일 경로를 식별자로 사용한다(G-08). 없는 PDF·등록/삭제·preview 요청 fixture는 존재한다고 기록하지 않는다.

1.3은 응답 지연·유실·중복·역순·다른 scope·종료 뒤 늦은 이벤트를 자동 행동 시험으로 구현한다. 유효 fixture 여러 개를 조합할 때 ID·시각·revision의 일관성을 유지하고 현재 날짜에 이미 만료된 승인 fixture는 고정 시험 시각을 사용한다. UI-13/14/15의 실제 도구 실행 횟수, UI-23/24의 범위 I/O, UI-27의 PDF Skill, UI-31/34의 provider/history/SSE 검증은 후속 통합 작업의 증거가 별도로 필요하다.

모든 화면의 목적·표시·입력·버튼·오류·접근성·사례를 작성했지만 G-01~G-08은 계약 인계에 열려 있다. 계약 보완과 재대조 전에는 전체 UI 구현 준비 완료로 판정하지 않는다. 앱 코드·스키마·생성 타입·다른 담당 체크는 이 작업에서 수정하지 않는다.
