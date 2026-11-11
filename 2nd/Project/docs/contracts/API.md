# API 계약 (schema_version "1")

> 작성: 박준형 (작업 3.2) · 작성일: 2026-11-04 (Asia/Seoul)
>
> 정본은 `contracts/**/*.schema.json`(JSON Schema draft-07)이다. 이 문서는 사용 규칙과 의미를 설명한다. 둘이 다르면 스키마가 맞고, 이 문서를 고친다. 이벤트·SSE는 [EVENTS.md](EVENTS.md), Pointer/Context 세부는 4.2의 `docs/contracts/{POINTERS,CONTEXT}.md`가 소유한다.

## 1. 계약 파일·생성 타입·검증 경로

| 영역 | 스키마 | 소유 |
| --- | --- | --- |
| 공통 | `contracts/common/{primitives,api-error,pagination,token-count}.schema.json`, `error-codes.json` | 3.2 |
| 공개 API | `contracts/api/{system,workspace,session,run,approval}.schema.json` | 3.2 |
| 앱 이벤트 | `contracts/events/app-event.schema.json` | 3.2 |
| R0 심볼 | `contracts/symbols/symbol.schema.json` | 3.2(계약), 3.3/3.4(구현) |
| 포인터·컨텍스트 | `contracts/pointers/`, `contracts/context/` | **4.2** (3.2는 `PointerUri`·`PointerKind` 경계만 정의) |

- **TypeScript:** `npm run generate:contracts`가 모든 정의를 `contracts/generated/ts/contracts.ts` 하나로 생성한다(손으로 수정 금지). 소비자는 `import type { RunSnapshot } from "@securecode/contracts"`처럼 가져온다. 런타임 검증은 `ContractValidator.load().parse<T>(SCHEMA_REFS.runSnapshot, body)`로 한다(Ajv, 같은 스키마 파일). `check`와 `test:contracts`가 생성 파일이 최신인지 검사한다.
- **Python:** 같은 스키마 파일을 `jsonschema`(Draft7)로 검사한다(`tests/contract`). 서비스 응답과 모든 fixture를 검증한다. Python DTO를 따로 생성하지 않는다. 서비스 내부 모델(pydantic)은 계약 시험으로 스키마와 맞춘다.
- **Fixture:** `contracts/fixtures/<영역>/<이름>.<valid|invalid>.json` = `{schema_ref, expect, scenario, data}`. `scenario`는 2.1의 UI/H 번호 또는 작업 번호다. TS(Ajv)와 Python(jsonschema)이 모든 fixture에서 같은 판정을 내야 한다. fixture 수는 `contracts/fixtures`를 열거해 확인한다.
- **공용 벡터:** `tests/fixtures/token-unicode-cases.json`(tokens.count Unicode), `tests/fixtures/redaction-cases.json`(로그 redaction). TS와 Python 시험이 같은 파일을 쓴다.

## 2. 공통 규칙

- 공개 API는 host `/api/v1/*`, 내부 API는 context-service `/internal/v1/*`다. 내부 API에는 `Authorization: Bearer <내부 토큰>`이 필요하고 브라우저 `Origin`은 거절한다.
- JSON 필드는 snake_case다. 응답 최상위에는 `schema_version: "1"`이 있다.
- 모든 응답에 `X-Request-Id`(`req_…`)가 붙는다. host가 서비스로 같은 값을 넘기며, `ApiError.request_id`와 같다.
- ID는 접두사가 있는 opaque 문자열이다: `ws_`, `ses_`, `run_`, `apr_`, `req_`, `evt_`, `sym_`, `cand_`. 클라이언트는 비교만 하고 해석하지 않는다. 포인터는 `securecode://(source|runtime)/…` opaque URI이며 **URL path에 넣지 않는다**(본문으로 전달).
- 응답의 `RelativePath`는 작업 공간 기준 POSIX 상대경로다. 상위 경로 요소(`..`), 절대경로, 역슬래시, ASCII 제어 문자, 빈 경로 요소를 거절한다. `WorkspaceCreateRequest.root_path`는 입력 전용이다.
- 시간은 RFC 3339 UTC(`Timestamp`)다.
- `maxUtf8Bytes`는 문자열을 UTF-8로 인코딩한 바이트 수의 상한이다. 공유 Ajv 검증기와 Python 계약 검증기가 같은 규칙을 사용한다. `maxLength`와 함께 있으면 두 조건을 모두 만족해야 한다.

### 2.1 오류

모든 실패는 `ErrorResponse = {schema_version, error: ApiError}`이다. `ApiError = {code, message(≤500, 표시 가능), retryable, request_id, details?}`이고 `details`는 스칼라 16개 이하다(경로·키·원문 금지). HTTP 상태와 기본 `retryable`은 `contracts/common/error-codes.json` 한 곳에서 정하며 TS(`loadErrorCodeTable`)와 Python(`ERROR_RULES`, 계약 시험으로 동기화)이 함께 쓴다.

| 범주 | 코드 (HTTP) | 확정 |
| --- | --- | --- |
| 로드맵 필수 16종 | `INVALID_POINTER` 400, `NOT_FOUND` 404, `EXPIRED` 410, `FORBIDDEN` 403, `SOURCE_CHANGED` 409, `INVALID_SELECTOR` 400, `UNSUPPORTED_FORMAT` 415, `UNSUPPORTED_LANGUAGE` 422, `PARSE_FAILED` 422, `NO_MATCH` (200 본문), `BUDGET_EXCEEDED` 413, `TOKENIZER_UNAVAILABLE` 503, `SDK_UNAVAILABLE` 503, `PROVIDER_ERROR` 502, `APPROVAL_REJECTED` 409, `CANCELLED` 409 | 3.2·4.2 확정. 표시 문구는 2.2 |
| 인증·origin | `UNAUTHENTICATED` 401, `BOOTSTRAP_CODE_INVALID` 401, `BOOTSTRAP_CODE_EXPIRED` 401, `ORIGIN_REJECTED` 403 | 3.2 final |
| 요청 | `VALIDATION_FAILED` 422, `PAYLOAD_TOO_LARGE` 413, `QUOTA_EXCEEDED` 507, `RATE_LIMITED` 429 | 3.2 |
| 실행·승인 | `RUN_ALREADY_ACTIVE` 409(retryable), `IDEMPOTENCY_CONFLICT` 409, `APPROVAL_EXPIRED` 410, `APPROVAL_DIGEST_MISMATCH` 409, `APPROVAL_ALREADY_DECIDED` 409, `PROTECTION_UNAVAILABLE` 503 | 3.2 final |
| 색인·서비스 | `INDEX_NOT_READY` 409, `SERVICE_UNAVAILABLE` 503, `NOT_IMPLEMENTED` 501, `INTERNAL_ERROR` 500 | 3.2 final |

`NO_MATCH`만 `transport: success_body`다. HTTP 200에서 심볼 검색은 빈 후보와 `no_match` 객체, 포인터 검색은 빈 `matches` 배열을 보낸다.

### 2.2 pagination·응답 상한

- 작업 공간·세션·run 목록 및 심볼 검색은 `page: PageRequest{limit 1..100(기본 20), cursor}`를 받고 `PageInfo{limit, next_cursor|null, has_more, truncated_by_bytes?}`를 돌려준다. `has_more=true`인 페이지에는 다음 cursor가 필요하며 마지막 페이지의 값은 null이다. 포인터 검색은 최상위에 `limit/cursor`를 받고 `truncated/next_cursor`를 반환한다.
- cursor는 서버가 scope·revision·연산에 묶어 발급하는 opaque 값(≤512자)이다. 다른 포인터·scope·query의 cursor는 `INVALID_POINTER`, 변경된 Source revision의 cursor는 `SOURCE_CHANGED`로 거절한다.
- 응답은 byte 상한을 지킨다. 상한 때문에 항목이 `limit`보다 적으면 `truncated_by_bytes: true`다. 조용히 잘라 성공으로 보이지 않는다.

### 2.3 idempotency

- 생성 요청(`POST /workspaces`, `/workspaces/:id/index`, `/sessions`, `/sessions/:id/runs`)은 `idempotency_key`(8~128자, `[A-Za-z0-9._:-]`)가 필수다.
- 같은 키와 같은 본문 → 처음 결과를 그대로 돌려준다(200). 같은 키와 다른 본문 → `IDEMPOTENCY_CONFLICT`. 키 보존은 workspace/session scope로 최소 24시간이며 3.5가 저장한다.
- 응답 유실 후 재전송은 같은 키로 한다. UI가 새 키를 만드는 경우는 사용자가 새 작업을 명시했을 때뿐이다.

## 3. 공개 API (`/api/v1`)

상태: **구현** = 동작(3.2 health, 3.5 실행 API), **501** = 계약 확정·route 등록, 지금은 `NOT_IMPLEMENTED`와 `details.owner_task` 반환. health·bootstrap 외 모든 경로(501 포함)는 bootstrap cookie가 필요하며 없으면 `UNAUTHENTICATED`(401)다.

| Method·Path | 요청 → 응답 스키마 | 상태 | 담당 |
| --- | --- | --- | --- |
| `GET /health` | → `system#HealthResponse` (bootstrap 전에는 `schema_version,status`만) | **구현** | 3.2 |
| `POST /auth/bootstrap` | `system#BootstrapRequest` → `BootstrapResponse` + `Set-Cookie` (HttpOnly, SameSite=Strict, Path=/api) | **구현** | 3.5 |
| `GET /settings` | → `system#SettingsResponse` (키 없음, `configured`만) | **구현** | 3.5 |
| `GET /workspaces` | `?limit&cursor` → `workspace#WorkspaceListResponse` | **구현** | 3.5 (H-02 목록 복구용, 3.2 추가) |
| `POST /workspaces` | `WorkspaceCreateRequest` → `Workspace` | **구현** | 3.5 |
| `GET /workspaces/:workspace_id` | → `Workspace` | **구현** | 3.5 |
| `POST /workspaces/:id/index` | `IndexRequest` → `IndexStatusResponse` (202) | **구현** | 3.6 (+3.3). 백그라운드 색인 |
| `GET /workspaces/:id/index` | → `IndexStatusResponse` | **구현** | 3.6 |
| `GET /workspaces/:id/sessions` | `?limit&cursor` → `session#SessionListResponse` | **구현** | 3.5 (H-04 세션 복구용, 3.2 추가) |
| `POST /sessions` | `SessionCreateRequest` → `Session` | **구현** | 3.5 |
| `GET /sessions/:session_id` | → `Session` (`active_run_id`로 재연결) | **구현** | 3.5 |
| `GET /sessions/:id/runs` | `?limit&cursor` → `run#RunListResponse` | **구현** | 3.5 |
| `POST /sessions/:id/runs` | `run#RunCreateRequest` → `RunSnapshot` (201, 재전송 200) | **구현** | 3.5 |
| `GET /runs/:run_id` | `run#RunSnapshotQuery` (선택 query) → `RunSnapshot` | **구현** | 3.5 |
| `GET /runs/:run_id/events` | SSE `AppEvent` ([EVENTS.md](EVENTS.md)) | **구현** | 3.5 |
| `POST /runs/:run_id/cancel` | → `RunSnapshot` (`cancelling` 또는 이미 종료된 상태) | **구현** | 3.5 |
| `POST /runs/:run_id/approvals/:approval_id` | `approval#ApprovalDecisionRequest` → `ApprovalDecisionResponse` | **구현** | 3.5 |
| `GET /workspaces/:id/pointers` | `PointerListQuery` (query) → `PointerListResult` | **구현** | 3.6 (runtime은 세션 소속 확인) |
| `POST /workspaces/:id/sources` | `SourceMutationRequest` → `SourceMutationResult` (등록·갱신) | **구현** | 3.6 |
| `POST /pointers/read`, `POST /pointers/search` | `PointerReadRequest` → `PointerReadResult`, `PointerSearchRequest` → `PointerSearchResult` | **구현** | 3.6. URI의 작업 공간·세션을 host가 확인, 상한은 서비스 |
| `DELETE /pointers` | `PointerDeleteRequest` (JSON 본문) → `PointerDeleteResult` | **구현** | 3.6 |
| `POST /context/preview` | `ContextPreviewRequest` → `ContextPreviewResponse`. `operation`은 `plan/search/bundle` 중 하나 | **구현** | 3.6. plan은 run 생성과 같은 입력이라 `preview_digest`가 같다 |
| `POST /pdf/parse`, `GET /pdf/jobs/:job_id` | | **구현** | 3.6 (서비스·도구 4.9) |

실제 route 목록은 `apps/host/src/routes/pendingRoutes.ts`다. 시험이 모든 항목의 501 응답과 `owner_task`를 검증한다. 담당 작업은 해당 항목을 지우고 실제 handler를 등록한다.

### 3.5 구현 세부

- **bootstrap:** launcher(`npm run dev`)가 시작마다 일회용 코드를 만들어 host에 넘기고 로컬 터미널에만 표시한다. 코드는 10분 유효하며 한 번만 교환된다. 20회 틀리면 잠긴다(`RATE_LIMITED`). 성공하면 `Set-Cookie: securecode_session=…; HttpOnly; SameSite=Strict; Path=/api; Max-Age=43200`이다. 세션 토큰은 host 메모리에만 있으므로 host를 다시 시작하면 다시 bootstrap한다.
- **개발 proxy:** UI(1.1)는 `scripts/dev/viteProxy.ts`의 `createViteApiProxy()`를 Vite `server.proxy`로 쓴다. Host 헤더는 host 주소로 바뀌고 브라우저 Origin(UI 개발 origin, host가 허용)은 유지되어 cookie와 SSE가 same-origin으로 동작한다.
- **본문 상한:** JSON 본문은 64 KiB(run 생성은 256 KiB)를 넘으면 `PAYLOAD_TOO_LARGE`, JSON이 아니거나 계약과 다르면 `VALIDATION_FAILED`다.
- **작업 공간:** `root_path`는 존재하는 절대 디렉터리여야 하고 링크·정션·파일시스템 최상위는 거절한다(`FORBIDDEN`, `details.reason`). `SECURECODE_ALLOWED_WORKSPACE_ROOTS`가 있으면 그 아래만 허용한다. 같은 실제 경로를 다시 등록하면 처음 workspace를 돌려준다. `index_status`는 3.6이 색인 API를 연결하기 전까지 `not_indexed`다.
- **명시 컨텍스트 (3.6):** run 생성은 매번 `context.select`로 계획한다(R0 자동 후보 + `context_refs`). `preview_digest`가 다르면 422 `VALIDATION_FAILED(stale_preview)`, 쓸 수 없는 명시 선택은 계획의 `run_create_error`(예: `SOURCE_CHANGED`, `BUDGET_EXCEEDED`)로 모델 호출 전에 거절한다. fragment는 첫 사용자 메시지에 한 번만 넣는다. 예제는 [3.6 UI 연동 예제](../handoffs/3.6-ui-integration-examples.md).
- **도구 (3.6):** 모델은 `read_file`·`search_file`(Source adapter), `code_search`·`code_read`(R0), `list_files`, `runtime_read`·`runtime_search`, `pdf_parse`·`pdf_status`·`pdf_search`·`pdf_read_pages`(자동 승인), `write_file`·`run_command`(사용자 승인)만 본다. 목록은 `cline/tools/sessionTools.ts`의 `ALLOWED_TOOL_NAMES`이고 fetch gate가 같은 목록으로 막는다. host는 파일 본문을 직접 읽지 않는다. 경로는 작업 공간 밖·링크·`.git`·`.securecode`를 거절한다.
- **재시작:** host가 멈출 때 끝나지 않은 run은 다음 시작에서 `failed`(`reason_code=SERVICE_UNAVAILABLE`)가 된다. 세션의 `active_run_id`는 비워진다. idempotency 키는 디스크에 24시간 보존된다. 이전 SDK 대화 이력은 이어지지 않고 다음 run은 새 SDK 세션으로 시작한다.

## 4. 내부 API (`/internal/v1`, context-service)

| Method·Path | 요청 → 응답 | 상태 |
| --- | --- | --- |
| `GET /health` | → `system#ServiceHealthResponse`. 구성요소별 `ok/not_configured/not_implemented(owner_task)` | **구현** |
| `POST /tokens/count` | `token-count#TokenCountRequest` → `TokenCountResult` | **구현** (live 미검증, 5절) |
| `POST /symbols/search`, `POST /symbols/bundle` | `symbol#SymbolSearchRequest/Response`, `SymbolBundleRequest/SymbolBundle` | 3.3/3.4 |
| `POST /source/register`, `/source/refresh` | 본문 `workspace_id` + `lifecycle#SourceMutationRequest`(operation별) → `SourceMutationResult` | **구현** (4.5). host가 인증한 workspace를 넣는다 |
| `POST /source/stat`, `/source/list`, `/source/unregister` | `{workspace_id, pointer}` → `PointerListItem` / `{workspace_id, limit?, cursor?}` → `PointerListResult` / `PointerDeleteRequest(kind=source)` → `PointerDeleteResult` | **구현** (4.5). workspace root 포트는 3.6이 연결하며, 연결 전에는 `NOT_FOUND(workspace_root_unconnected)` |
| `POST /source/read`, `/source/search` | 본문 `workspace_id` + `read#PointerReadRequest` → `PointerReadResult` / `search#PointerSearchRequest` → `PointerSearchResult` | **구현** (4.6). line/byte/section은 원본 구간을 seek로 읽고 `provenance.selection`(revision·원본 SHA-256·byte 구간)을 준다. json_path는 8 MiB 이하 전체 파싱이며 selection이 없다. 검색은 요청당 scan 8 MiB·2초 상한, 넘으면 `truncated`+`next_cursor`. 토큰 수는 `tokens.count`와 같은 TokenCounter로 세며 계수기가 없으면 `TOKENIZER_UNAVAILABLE` |
| `POST /runtime/pointers` | `{workspace_id, session_id, content, media_type?, origin?, truncated_before_storage?, run_id?}` → `{pointer_id, pointer_uri, byte_size, descriptor(PointerListItem)}` | **구현** (4.3). 객체 32 MiB·세션 128 MiB 초과는 `QUOTA_EXCEEDED`(오래된 출력을 지우지 않음). `origin`이 제한된 읽기 도구(`runtime_read` 등)이면 `VALIDATION_FAILED(bounded_read)` |
| `POST /runtime/read`, `/runtime/search`, `/runtime/list` | 범위 + `read#PointerReadRequest` / `search#PointerSearchRequest` / `PointerListQuery(kind=runtime)` → `PointerReadResult` / `PointerSearchResult` / `PointerListResult` | **구현** (4.3). Source와 같은 selector·상한·cursor 규칙. 읽는 64 KiB 청크마다 저장 checksum을 확인한다. 목록 응답은 100개·64 KiB 이하 |
| `POST /runtime/pointers/delete`, `/runtime/sessions/clear` | 범위 + pointer / 범위 → `{deleted}` | **구현** (4.3). 멱등. 이후 조회는 `NOT_FOUND(deleted|session_cleared)`, 만료는 `EXPIRED` |
| `POST /runtime/stream` | 헤더 `x-securecode-workspace-id`·`-session-id`·`-origin`·`-media-type`·`-truncated`·`-run-id`(선택) + `application/octet-stream` 청크 본문 → `/runtime/pointers`와 같은 응답 | **구현** (4.4). host 명령 executor가 출력을 받는 대로 보낸다. 연결이 끊기면 부분 객체를 남기지 않는다. `run_id`(1.5, 2026-11-11)는 출력을 만든 run이며 `provenance.run_id`로 목록·descriptor에 나온다. 스키마 v3에서 추가했고 v2 DB는 열만 더해 보존한다 |
| `POST /tokens/request` | `token-count#RequestTokenCountRequest`(outbound 요청 JSON 그대로) → `TokenCountResult`(`framing: provider_request`) | **구현** (4.8). host 요청 gate 전용. framing은 Anthropic Messages(`anthropic`)와 OpenAI 호환 chat(`openai-compatible`, 로컬 llama.cpp: `/apply-template`+`/tokenize`, `exact`) 두 가지다. 모르는 필드·계수기와 다른 provider는 `TOKENIZER_UNAVAILABLE`. 본문 16 MiB 상한 |
| `POST /context/select` | `context#ContextSelectRequest` → `ContextSelectResponse`(`ContextPreviewPlan` + `run_create_error`) | **구현** (4.8). 정책은 [CONTEXT_SELECTOR.md](../architecture/CONTEXT_SELECTOR.md). 비용 텍스트는 서비스가 세고, 음수 예산이면 `BUDGET_EXCEEDED`, 계수기가 없으면 `TOKENIZER_UNAVAILABLE`. R0 후보는 3.6이 색인을 연결한 뒤 생긴다 |
| `POST /pdf/parse`, `/pdf/status`, `/pdf/cancel` | `pdf-job#PdfParseRequest` → `PdfJobStatus` / `{workspace_id, job_id}` → `PdfJobStatus` / `{cancelled: true}` | **구현** (4.9). 응답에 추출 본문 없음. 같은 원본 해시·파서 버전은 같은 job(멱등). 끝난 job은 원본 변경 시 `stale`. 파싱은 격리 프로세스(50 MiB·500쪽·60초) |
| `POST /source/read` (`selector.type=pdf_page`), `/source/search` (PDF) | `read#PointerReadRequest` / `search#PointerSearchRequest` → `PointerReadResult` / `PointerSearchResult` | **구현** (4.9). 한 번에 한 페이지 구간, `pdf_page` selection(페이지·페이지 텍스트 바이트 구간·파서 버전). 파싱 전 `INDEX_NOT_READY(pdf_not_parsed)`, 범위 밖·제외 페이지 `INVALID_SELECTOR` |

내부 포트 이름(로드맵 0.6)과 경로의 대응: `symbols.search/read_bundle` → `/symbols/search|bundle`, `tokens.count` → `/tokens/count`, `tokens.request` → `/tokens/request`, `context.select` → `/context/select`, `source.register/stat/list/unregister` → `/source/register|refresh|stat|list|unregister`. `idempotency_key`는 형식만 검사하며, 같은 키 재전송의 결과 재생과 충돌 판정은 host 공개 route(3.6)가 맡는다. 등록·해제 자체는 같은 원본에 대해 멱등이다. 포인터·컨텍스트·PDF 경로는 4.2가 같은 규칙(`/internal/v1/<영역>/<연산>`, 본문 JSON)으로 정한다.

## 5. tokens.count (본문 계수)

- 3.1이 고른 모델은 provider `anthropic`, model `claude-sonnet-5-5`다. 공개 로컬 tokenizer가 없으므로 `POST https://api.anthropic.com/v1/messages/count_tokens`를 쓴다. 결과는 **`count_mode: provider_estimate`**다(공식 문서상 추정값). `exact`는 provider와 같은 로컬 tokenizer가 있을 때만 쓴다. 지금은 쓰지 않는다.
- `framing: single_user_message`: 사용자 메시지 1개·text 블록 1개로 감싼 수다. 대화 전체·도구 정의·system·출력 예약을 더한 최종 요청 계수와 hard cap은 **4.8**(`ModelRequestGate`, fetch gate) 범위다.
- 입력: 1 MiB(UTF-8) 이하의 빈 문자열이 아닌 텍스트. 외톨이 surrogate는 `VALIDATION_FAILED(reason=invalid_unicode)`로 provider 호출 전에 거절한다(TS는 `isWellFormed()`로 전송 전 거절). 1 MiB 초과는 `PAYLOAD_TOO_LARGE`, 다른 모델 요청은 `TOKENIZER_UNAVAILABLE(model_not_configured)`이다.
- 실패: 키 없음 `TOKENIZER_UNAVAILABLE(api_key_missing, retryable=false)`, 401/403 `provider_auth_failed`, 429/5xx/timeout은 retryable. 메시지에 원문과 키를 넣지 않는다.
- 같은 `(model, text)`는 프로세스 메모리 LRU(1024개)에서 `cached: true`로 돌려준다. 요청이 많으므로(rate limit) 호출자는 큰 본문을 묶어서 계수한다.
- 길이/4나 byte 수를 토큰 수라고 보고하지 않는다(로드맵 0.7). 계수할 수 없으면 오류다.

## 6. 실행·승인·snapshot 의미

- **세션당 활성 run 1개.** 활성 run이 있을 때 새 run은 `RUN_ALREADY_ACTIVE`(retryable, `details.active_run_id`)다.
- `RunStatus`: `queued → running ⇄ awaiting_approval → (cancelling) → completed | failed | cancelled`. 종료 3종은 한 번 정해지면 바뀌지 않는다. 취소는 `cancelling`을 거쳐 SDK 확인 뒤 `cancelled`가 된다. SDK `start/send`는 실패해도 대개 resolve하므로(3.1 C-05) 상태는 `finishReason`과 Core status로 정한다.
- **불변식(3.5가 시험):** `status`가 종료 상태이면 `terminal`은 null이 아니고 `terminal.status`와 같다. 그 외에는 `terminal`이 null이다. `pending_approvals`에는 `status=pending` 항목만 있다.
- `RunSnapshot`은 UI(1.3/1.4)가 새로고침이나 replay 범위 초과 뒤 그리는 서버 상태 전체다. 진행 상태, 답변(최대 65,536자, 넘으면 `truncated`), 도구 요약(원문 없음, 큰 출력은 `output_pointer`), 대기 승인, 종료 정보, `replay{oldest_sequence,last_sequence}`가 들어 있다. 이벤트는 이 snapshot 위의 증분이다.
- **승인:** host broker가 `approval_id`, 입력 digest(`sha256:` + canonical JSON의 sha256), 만료를 만든다(3.1 S-01). 결정 요청의 `input_digest`가 다르면 `APPROVAL_DIGEST_MISMATCH`, 만료면 `APPROVAL_EXPIRED`, 이미 결정·취소·세션 종료면 `APPROVAL_ALREADY_DECIDED`다. `review.reviewable=false`(내용이 16 KiB 검토 상한을 넘음)이면 approve를 거절한다. 자동 승인 기본값은 없다. 프로젝트 도구는 commit/push를 실행하지 않는다.
- **보호 기능:** `runtime_pointer_hook`, `model_request_gate`, `approval_broker`, `tool_allowlist`, `checkpoint_disabled` 중 하나라도 준비되지 않으면 세션·run 시작을 `PROTECTION_UNAVAILABLE`로 막는다(3.1 S-04). settings의 `protections`에 상태가 보인다.

### 명시 선택과 미리보기 확인

실행과 계획 미리보기는 `ExplicitContextRef`를 받는다. 심볼은 `candidate_id/index_revision`, 포인터는 `kind/pointer/selection`을 전달한다. `selection`은 읽기 결과의 `provenance.selection`을 그대로 복사한다. 표시한 UTF-8 바이트 구간, 원본 해시, revision이 포함되며 PDF는 해당 페이지 번호와 파서 버전도 포함한다. 과거 응답에서 `selection`을 얻을 수 없으면 부분 읽기를 다시 요청한다. 서비스는 인증 범위·revision·해시·반환 범위를 재검사하고, 오래된 자료는 `SOURCE_CHANGED`로 거절한다.

`RunCreateRequest.preview_digest`는 사용자가 확인한 미리보기 결과에 있을 때 그대로 돌려주는 SHA-256 값이다. 선택·질문·이력·예산 설정 등이 바뀌어 해당 계획이 만료되면 `VALIDATION_FAILED`와 `details.reason=stale_preview`로 거절한다. UI는 예전 결과를 폐기하고 새 미리보기를 확인받는다. 미리보기를 거치지 않은 요청도 실행 전 서버에서 권한·자료 버전·예산을 검증한다. 응답 유실 시에는 기존 `idempotency_key`와 처음 보낸 본문으로 같은 실행을 확인한다.

### 재연결 후 출처·승인 이력

`GET /runs/:id`의 첫 응답은 최신 `replay.last_sequence`까지를 담는다. `answer.citations`에는 응답에 사용된 근거만 온다. 심볼 항목의 `ref`와 `location`에는 revision 및 파일·줄·해시가, 포인터 항목의 `ref.selection`에는 읽기에서 확인한 범위가 있다. 클라이언트는 자료를 열기 전에 권한·현재 버전을 다시 확인한다. `approval_history`에는 결정된 요청의 `approval_id,tool_call_id,tool_name,status,decided_at`이 있다. `approved/rejected/expired/cancelled`을 구별하고, 도구 실행 결과는 해당 tool call의 상태로 표시한다.

각 목록에는 `citations_page` 또는 `approval_history_page`가 함께 오며 한 번에 최대 50개다. 새 응답은 목록이 비어도 빈 배열과 종료 페이지를 보낸다. 기존에 저장된 snapshot에 두 필드가 함께 없으면 UI는 “이 기록에서 확인할 수 없음”으로 표시한다. `has_more`가 참이면 같은 run의 GET에 `citation_cursor` 또는 `approval_cursor` 중 하나만 query로 보내 그 목록의 다음 페이지를 읽는다. cursor는 사용자 범위·run·목록 종류·최초 조회 시점의 sequence에 묶이며 당시 순서로만 이어간다. 처음부터 재조회하면 현재 snapshot으로 돌아간다. 특정 목록의 이전 페이지를 열어도 현재 run 상태와 SSE 구독 위치는 되돌리지 않는다. 다른 run·목록의 cursor나 만료된 cursor는 `VALIDATION_FAILED`로 거절한다. UI는 현재 snapshot의 첫 페이지부터 다시 조회한다. [복구 응답 예시](../../contracts/fixtures/api/run-snapshot-recovered-evidence.valid.json)

### 화면에 표시할 설정 한도

인증된 `GET /settings`의 `limits`는 해당 host가 제공하는 실제 적용값이다. 숫자는 양의 정수이며 이름에 단위를 붙인다. 제공하지 않은 값은 “미제공”으로 표시한다. 지원되는 기능은 관련 한도를 모두 반환해야 한다. 미구현 기능을 설계 목표값으로 채우지 않는다.

| 기능 | 한도 키 |
| --- | --- |
| 도구 결과 보관·보존 | `runtime_pointer_threshold_bytes`, `runtime_object_max_bytes`, `runtime_session_max_bytes`, `runtime_ttl_seconds` |
| 미리보기·부분 읽기·승인 | `pointer_preview_bytes`, `pointer_read_max_bytes`, `pointer_read_max_tokens`, `approval_review_max_bytes` |
| 원본·JSON·PDF | `source_file_max_bytes`, `json_parse_max_bytes`, `pdf_max_bytes`, `pdf_max_pages` |

텍스트 바이트는 UTF-8로 센다. 승인 검토 본문의 최대값은 16,384바이트다. 전체 입력이 더 크면 서버는 UTF-8 경계에서 끊고 `content_truncated=true, reviewable=false`로 반환한다. 승인할 때는 서버가 보낸 전체 도구 입력의 digest를 그대로 돌려준다. 서버는 원래 요청과의 digest 일치, 미만료, 결정 대기, 검토 가능 여부를 함께 확인한다. [설정 응답 예시](../../contracts/fixtures/api/settings-effective-limits.valid.json)

## 7. 색인·작업 공간 의미

- `IndexState`: `not_indexed | queued | indexing | parsed | ready | partial | stale | failed`. `partial`은 파일별 진단이 있지만 검색할 수 있는 상태, `parsed`는 3.4 검색기가 준비되기 전 상태, `stale`은 마지막 revision 이후 파일이 바뀐 상태다.
- 색인은 run이 아니므로 SSE가 없다. `GET /workspaces/:id/index`가 정본이다. 새 revision은 준비가 끝난 뒤 원자적으로 `index_revision`이 된다(그 전에는 `pending_revision`). 진단은 50개까지이고 그 이상은 `diagnostics_truncated`로 표시한다.
- `Workspace.supported_languages`는 색인기가 지원하는 언어의 목록이다. Python, C, C++, Java, JavaScript의 계약 값은 각각 `python`, `c`, `cpp`, `java`, `javascript`다. 실제 색인 결과는 `counts`, `diagnostics`, `searchable`로 확인한다. 검색 응답에 `no_match{reason_code: NO_MATCH, hint}`가 있으면 UI가 식별자·파일명 검색을 안내한다. TF-IDF가 한국어 질문을 번역한다고 가정하지 않는다.
- 고정한 `index_revision`이 더 이상 제공되지 않으면 `SOURCE_CHANGED`(`details.current_revision`)를 돌려준다.

## 8. 버전·변경 절차

- 첫 릴리스(3.8) 전까지 `schema_version`은 `"1"`로 유지한다. 그 전의 **추가형 변경**(선택 필드, 새 정의)은 같은 버전에서 하되 fixture·생성 타입·이 문서를 함께 바꾼다. 필드 삭제·의미 변경은 소유자 handoff와 영향 작업 목록을 남긴다. 릴리스 뒤의 호환성 깨짐은 `"2"`로 올린다.
- 2.2 인계에 따라 공개 run의 명시적 포인터 선택에는 읽기 결과의 확정 범위가 필요하다. 이전의 pointer-only 참조는 기존 계획을 표시할 때 읽을 수 있다. 새로운 실행을 제출하려면 원문 일부를 다시 읽고 선택한다. 출처·승인 페이지가 없는 이전 snapshot은 기존대로 읽을 수 있다. 화면 명세와 영향 범위는 [2.2 인계](../handoffs/2.2-ui-behavior-contract-gaps.md)에 기록한다.
