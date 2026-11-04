# 앱 이벤트·SSE·snapshot 계약 (schema_version "1")

> 작성: 박준형 (작업 3.2) · 작성일: 2026-11-04 (Asia/Seoul) · 정본 스키마: `contracts/events/app-event.schema.json`, `contracts/api/run.schema.json#RunSnapshot`
>
> 입력: 2.1 인계 3절(전달할 사실), 3.1 C-05/C-06(Core 이벤트·상태 실측)

## 1. 앱 이벤트와 SDK 이벤트의 분리

- Cline SDK의 `CoreSessionEvent`(`agent_event`, `chunk`, `ended`, `session_snapshot`, `status`, …)는 **host 내부에서만** 쓴다. UI·SSE·로그로 그대로 보내지 않는다.
- host의 SDK 이벤트 mapper(`apps/host/src/cline/events/`, 3.5)가 SDK 이벤트를 아래 `AppEvent`로 바꾼다. mapper는 크기 상한을 다시 적용한다. 3.1 C-06에 따르면 `agent_event.content_end`에는 hook이 처리한 뒤의 도구 출력이 실리므로, 교체가 없으면 원문이 그대로 남는다.
- `AppEvent`의 `type`은 우리 앱의 이름이며 SDK 이름이 아니다. 유효하지 않은 `type`(예: `agent_event`)은 스키마에서 거절한다(fixture `events/unknown-type.invalid`).

## 2. 봉투(envelope)

| 필드 | 의미 |
| --- | --- |
| `schema_version` | `"1"` |
| `event_id` | `evt_…`, 이벤트마다 고유 |
| `sequence` | **run 범위** 정수. 1부터 시작하고 이벤트마다 1씩 늘어난다. 전역 번호가 아니다 |
| `workspace_id`, `session_id`, `run_id` | 모든 이벤트는 run 범위다. 클라이언트는 현재 화면의 run과 다르면 버린다 |
| `type` | 아래 표 |
| `timestamp` | RFC 3339 UTC |
| `payload` | type별 스키마. 전체 도구 원문·코드 원문을 넣지 않는다 |

## 3. 이벤트 종류

| type | payload | 2.1 사실 / 화면 | 생성 담당 |
| --- | --- | --- | --- |
| `run.status_changed` | `status`, `previous_status`, 종료 시 `terminal{status,finished_at,reason_code,message}` | 실행 시작·진행·종료 / SC-03 | 3.5 |
| `run.output_delta` | `message_id`, `text`(≤4096자) | 답변 조각 / SC-03 | 3.5 |
| `run.tool_call_updated` | `tool_call: ToolCallSummary`(`phase`, `summary` ≤500, 큰 출력은 `output_pointer`) | 도구 상태 / SC-03 | 3.5 (+4.4 pointer) |
| `run.approval_requested` | `approval: ApprovalRequest` | 승인 요청 / SC-04 | 3.5 |
| `run.approval_resolved` | `approval_id`, `status`, `decided_at`, `reason_code` | 결정·만료·취소 / SC-04 | 3.5 |
| `run.pointer_created` | `pointer`, `kind`, `byte_size`, `tool_call_id` | 실행 결과 저장 / SC-03, SC-06 | 4.4 (3.5 전달) |
| `run.context_planned` | `selected_count`, `omitted_count`, `used_tokens`, `budget_tokens`, `count_mode`, `index_revision` | 컨텍스트 선택·예산 / SC-05, SC-09 | 4.8 (3.6 전달) |
| `stream.replay_unavailable` | `requested_after_sequence`, `oldest_available_sequence` | 재생 범위 초과 / SC-03 | 3.5 |

포인터 descriptor 전체와 ContextPlan의 fragments는 이벤트에 넣지 않는다. 4.2가 정하는 포인터·context API로 따로 읽는다(경계). 포인터 삭제·만료는 이벤트 없이도 목록·읽기 응답(`NOT_FOUND`/`EXPIRED`)으로 알 수 있어야 한다.

**이벤트가 아닌 것:** 색인 진행(`GET /workspaces/:id/index`), PDF job(`GET /pdf/jobs/:id`), health·settings·인증은 GET이 정본이다. 전역 이벤트 스트림은 MVP에 없다. run이 없는 작업에 가짜 `run_id`를 만들어 이벤트를 붙이지 않는다.

## 4. SSE 형식 (`GET /api/v1/runs/:run_id/events`)

```text
id: 42
event: run.output_delta
data: {"schema_version":"1","event_id":"evt_…","sequence":42,…}

```

- 같은 origin cookie로 인증한다(EventSource `withCredentials` 불필요, Vite proxy가 origin을 맞춤). 토큰을 query에 넣지 않는다.
- `id:`는 `sequence`의 10진수 문자열이다. 브라우저는 재연결할 때 마지막 값을 `Last-Event-ID`로 보낸다.
- 15초마다 `: keep-alive` 주석 줄을 보낸다(3.5). 연결이 끊긴 것은 실행 취소가 아니다. 서버의 run은 계속된다.

## 5. 재연결·replay

1. 클라이언트가 `Last-Event-ID: n`으로 다시 연결한다.
2. `n + 1 >= oldest_sequence`이면 서버는 `n+1`부터 보존된 이벤트를 순서대로 다시 보내고 실시간 이벤트를 이어 보낸다. 클라이언트는 `sequence <= 이미 반영한 값`인 이벤트를 무시한다(중복 제거).
3. 범위를 넘었으면 서버는 `stream.replay_unavailable`을 1번 보낸다. 이 이벤트는 저장되지 않는 안내라서 SSE `id:` 줄이 없고, `sequence`에는 현재 마지막 값을 넣는다. 클라이언트는 이 이벤트를 sequence로 중복 제거하지 않는다. 이어서 `GET /runs/:id` snapshot을 읽고 `replay.last_sequence`부터 다시 구독한다.
4. **보존 범위(3.5 구현 기준):** run마다 최근 이벤트 1,000개. run이 끝난 뒤에는 10분간 보존하고 이후 snapshot만 남긴다. 실제 범위는 snapshot의 `replay{oldest_sequence,last_sequence}`로 알린다.
5. 종료 상태(`completed/failed/cancelled`)를 담은 `run.status_changed` 뒤에는 그 run의 이벤트를 더 보내지 않는다. 늦게 도착한 SDK 이벤트가 종료 상태를 되돌리지 못한다.
6. 응답을 다시 재생한다고 명령·승인이 다시 실행되지 않는다. 승인 결정은 `approval_id` 단위로 한 번만 처리된다.

## 6. UI가 참조하는 서버 상태 snapshot

| 화면 상태 | 정본 | 필드 |
| --- | --- | --- |
| 작업 공간 목록·선택 복구 | `GET /workspaces` | `WorkspaceListResponse.items[]` |
| 색인 진행 | `GET /workspaces/:id/index` | `IndexStatusResponse` |
| 세션·활성 run 복구 | `GET /workspaces/:id/sessions`, `GET /sessions/:id` | `Session.active_run_id`, `last_run_id` |
| 대화 목록 | `GET /sessions/:id/runs` | `RunSummary[]` |
| run 진행·답변·도구·승인·종료 | `GET /runs/:id` + SSE | `RunSnapshot` + `AppEvent` 증분 |
| 서비스·보호 기능 상태 | `GET /health`, `GET /settings` | `HealthResponse`, `SettingsResponse.protections` |

UI는 이 값을 자체 상태 머신으로 다시 정의하지 않는다(로드맵 1절). 이전 workspace·session·run의 응답이 현재 화면을 덮어쓰지 않도록 ID를 비교한다.

## 7. SDK → AppEvent 매핑 (3.5 구현 기준)

| SDK (설치 0.2.0 실측) | AppEvent |
| --- | --- |
| Core status `running` | `run.status_changed{status: running}` |
| Core status `pending`(승인 대기) + broker 요청 생성 | `run.approval_requested` 다음 `run.status_changed{awaiting_approval}` |
| broker 결정·timeout·취소 | `run.approval_resolved`, 필요하면 `run.status_changed{running|cancelling}` |
| `chunk`(assistant text) | `run.output_delta` (4096자 단위로 나눔) |
| `agent_event` tool start/end | `run.tool_call_updated` (출력 원문 대신 summary·pointer) |
| afterTool에서 포인터 교체 | `run.pointer_created` |
| beforeModel/fetch gate 결과 | `run.context_planned` |
| `finishReason=completed` / `error` / `aborted` + Core `completed`/`cancelled` | `run.status_changed{completed|failed|cancelled, terminal}` |
| `session_snapshot`, `ended`, 기타 | 내부 상태 갱신에만 쓰고 전달하지 않음 |
