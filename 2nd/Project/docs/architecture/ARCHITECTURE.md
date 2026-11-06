# SecureCode 통합 아키텍처·소유권

> 작성: 박준형 (작업 3.2) · 작성일: 2026-11-04 (Asia/Seoul)
>
> 입력: [로드맵 0절](../../INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md), [SDK_COMPATIBILITY.md](SDK_COMPATIBILITY.md)(3.1), [2.1 UI 인계](../handoffs/2.1-ui-contract-requirements.md), [POINTER_DESIGN.md](POINTER_DESIGN.md)(4.1)
>
> 계약 상세: [API.md](../contracts/API.md), [EVENTS.md](../contracts/EVENTS.md) · 규약: [TYPESCRIPT_REACT.md](../conventions/TYPESCRIPT_REACT.md)

## 1. 프로세스 구조

```text
브라우저 UI (apps/ui, 1.1~)  ── same-origin HTTP JSON + SSE, cookie ──┐
                                                                     ▼
Node host (apps/host, 127.0.0.1:8787)                                │
  app/        서버 조립·수명주기                                      │
  security/   Host·Origin·Sec-Fetch-Site 검사 (3.2), bootstrap cookie (3.5)
  routes/     /api/v1 (3.5: auth·settings·workspaces·sessions·runs·approvals·SSE, 3.6 경로는 501 + owner_task)
              runs/ 상태 머신·이벤트 로그·snapshot·재시작 복구, shared/ 본문 상한·idempotency·페이지
  cline/      SDK 어댑터·tools·events·permissions (3.5). routes는 SDK 없는 AgentRuntime 포트만 사용
  context-client/ ContextServiceClient (bearer 내부 토큰)
  pointer-hooks/  ToolResultTransformer 구현 (4.4)
        │ http://127.0.0.1:8788  Authorization: Bearer <기동마다 새 토큰>
        ▼
Python context-service (services/context-service, FastAPI)
  app/      설정·DI·기동 (python -m securecode_context.app)
  api/      /internal/v1 (health, tokens/count 구현)
  common/   오류·redaction·tokens(TokenCounter)
  symbols/  R0 (3.3/3.4)   pointers/ runtime·source (4.3~4.6)
    parser/ graph/ index/  언어별 파서·참조 그래프·revision 저장 (3.3)
    retrieval/ bundle/     TF-IDF 검색·예산 안 원문 묶음 (3.4)
  context/  선택·예산 (4.7/4.8)   pdf/ (4.9)
```

- 두 서버 모두 `127.0.0.1`에만 바인딩한다. 설정에서 다른 주소를 거절한다(`hostConfig.ts`, `settings.py`).
- 브라우저는 context-service를 직접 부르지 않는다. context-service는 `Origin` 헤더가 있는 요청을 `ORIGIN_REJECTED`로 거절한다.
- `npm run dev`(`scripts/dev/start.ts`)가 기동마다 32바이트 내부 토큰을 만든다. 토큰은 두 자식 프로세스의 환경변수로만 전달하고, 파일·URL·로그에 쓰지 않는다.

## 2. 담당별 소유 파일 (고정)

공유 파일을 바꿔야 하면 소유자에게 `docs/handoffs/`로 요청한다. 소유자가 아닌 사람은 무단으로 함께 수정하지 않는다(로드맵 0.3).

| 경로 | 소유 | 작업 | 다른 사람의 사용 방식 |
| --- | --- | --- | --- |
| `package.json`, `package-lock.json`, `tsconfig.base.json`, `eslint.config.js`, `.prettierrc.json`, `.prettierignore`, `.gitignore`, `.env.example`, `.nvmrc` | 박준형 | 3.2/3.7 | 의존성·검사 변경을 handoff로 요청 |
| `scripts/**` (dev/stop/check/test/build, 구조 검사, baseline) | 박준형 | 3.2/3.7 | 자기 `PENDING` 항목을 실제 단계로 교체할 때 PR에 포함 |
| `contracts/common`, `contracts/api`, `contracts/events`, `contracts/symbols`, `contracts/src`, `contracts/scripts`, `contracts/generated` | 박준형 | 3.2 | 생성 타입·validator 사용. 수정 요청은 handoff |
| `contracts/pointers`, `contracts/context`, 해당 fixtures | 임우형 | 4.2 | 3.2 경계 타입(`PointerUri`, `PointerKind`)을 참조 |
| `contracts/fixtures/{common,api,events,symbols}` | 박준형 | 3.2 | UI fixture로 사용(1.2) |
| `apps/host/src/{app,routes,config,security,logging,context-client}` | 박준형 | 3.2/3.5/3.6 | — |
| `apps/host/src/cline/**` (adapter·plugins·tools·events·permissions) | 박준형 | 3.5/3.6 | 포트 `cline/adapter/ports.ts`로 연결 |
| `apps/host/src/pointer-hooks/**` | 임우형 | 4.4 | `ToolResultTransformer` 구현 |
| `apps/host/src/cline/plugins/**`, `apps/host/tests/integration/**` | 임우형 | 4.4 | 설치된 SDK의 afterTool을 오프라인 검증한다. 운영 run 연결은 3.5/3.6에서 인수한다. |
| `services/context-service/{pyproject.toml,uv.lock,pytest.ini}`, `src/securecode_context/{app,common}`, `api/{health,tokens,middleware,error_responses}.py` | 박준형 | 3.2 | 새 router는 `app/factory.py`에 등록 요청 |
| `services/context-service/src/securecode_context/symbols/**` | 박준형 | 3.3/3.4 | Candidate 계약으로 사용 |
| `services/context-service/src/securecode_context/{pointers,context,pdf}/**`, `api/{pointers,schemas,main}.py` | 임우형 | 4.3~4.9 | — |
| `apps/ui/src/{features,hooks,components,api,styles}`, UI 시험·E2E | 김민지 | 1.1~1.6 | 생성 타입·fixture 사용 |
| `docs/ui/{SCREEN_SPEC,UI_BEHAVIOR,ACCEPTANCE}.md`, UI 검토 | 김찬우 | 2.1~2.3 | — |
| `docs/architecture/{ARCHITECTURE,SDK_COMPATIBILITY}.md`, `docs/contracts/{API,EVENTS}.md`, `docs/conventions/TYPESCRIPT_REACT.md` | 박준형 | 3.1/3.2 | — |
| `docs/architecture/{POINTER_DESIGN,CONTEXT_SELECTOR}.md`, `docs/contracts/{POINTERS,CONTEXT}.md` | 임우형 | 4.1/4.2/4.7 | — |
| `tools/sdk-probe/**` | 박준형 | 3.1 | SDK 버전 변경 시 `npm run probe:sdk` 재실행 |

host의 `security/`, `logging/` 디렉토리는 0.5 트리에 없지만 3.2가 추가한 host 공용 계층이다. `check:structure`의 허용 목록(`apps/host/src/{app,routes,cline,context-client,pointer-hooks,config,security,logging}`)과 context-service 패키지 허용 목록(`app,api,common,symbols,pointers,context,pdf`)이 이 표를 강제한다.

## 3. 앱 내부 포트

SDK와 독립된 TypeScript 인터페이스다. 구현 담당은 이 시그니처를 바꾸지 않고 구현만 추가한다. 바꿔야 하면 handoff로 요청한다.

| 포트 | 위치 | 구현 | 계약 |
| --- | --- | --- | --- |
| `ContextServiceClient` | `apps/host/src/context-client/ports.ts` | `HttpContextServiceClient` (3.2: health·tokens 구현) | `/internal/v1/*`, 응답은 `ContractValidator`로 검증 |
| `TokenCounter` | 같은 파일 | context-service `tokens.count` (3.2 구현) | `TokenCountRequest/Result`, 실패 `TOKENIZER_UNAVAILABLE` |
| `SymbolService` | 같은 파일 (+ Python `symbols/ports.py`) | Python `symbols/symbol_service.py`의 `R0SymbolService`(3.4). 내부 HTTP route와 host 연결 전까지 host는 `NOT_IMPLEMENTED`(owner 3.6) | `contracts/symbols` |
| `PointerService` | 같은 파일 | 4.3~4.6. 지금은 `NOT_IMPLEMENTED`(owner 4.3/4.6) | 연산 이름만 고정. payload는 4.2 `contracts/pointers` |
| `ToolResultTransformer` | `apps/host/src/cline/adapter/ports.ts` | 4.4 (`pointer-hooks/`) | afterTool `result` 교체. 실패 시 throw |
| `AgentRuntime` | `apps/host/src/cline/adapter/runtimePort.ts` | `ClineAgentRuntime`(3.5, 설치 `@cline/sdk` ClineCore) | run service가 쓰는 SDK 독립 포트. 시험은 `tests/support/fakeRuntime.ts` |
| `ModelRequestGate` | 같은 파일 | 4.8 | `ClineCoreOptions.fetch` 최종 gate. `BUDGET_EXCEEDED`/`TOKENIZER_UNAVAILABLE` |

TokenCounter는 Python 한 곳에만 구현한다. TypeScript는 `ContextServiceClient.tokens`로 같은 구현을 재사용하므로, 두 언어가 서로 다른 계수 결과를 내지 않는다. 3.1이 고른 모델(`claude-sonnet-5-5`)에는 공개 로컬 tokenizer가 없다. 그래서 provider `count_tokens`를 호출하고 `count_mode: provider_estimate`로 표시한다. 키가 없으면 `TOKENIZER_UNAVAILABLE`을 돌려주며 길이/4 같은 추정은 하지 않는다. 계수에는 사용자 메시지 1개의 최소 framing이 포함된다(`framing: single_user_message`). 요청 전체의 provider framing과 총 요청 gate는 4.8 범위다.

## 4. 보안 정책

| 항목 | 정책 | 구현 위치 / 상태 |
| --- | --- | --- |
| loopback | host·service는 127.0.0.1(또는 ::1)에만 바인딩. 다른 주소 설정은 기동 거절 | `config/hostConfig.ts`, `app/settings.py` (구현) |
| 내부 인증 | 기동마다 새로 만든 bearer 토큰. 32자 미만 거절. `hmac.compare_digest`로 상수 시간 비교. health도 인증 필요 | `api/middleware.py` (구현) |
| 브라우저 차단 | context-service는 `Origin` 헤더 요청을 거절 | 같은 파일 (구현) |
| same-origin | host가 `Host` 허용 목록(DNS rebinding 방지), `Sec-Fetch-Site: cross-site` 거절, 허용 목록 밖 `Origin` 거절, 상태 변경 요청에 `Origin` 필수 | `security/originGuard.ts` (구현) |
| 허용 origin | host origin + Vite dev origin(`SECURECODE_UI_DEV_PORT`) + `SECURECODE_ALLOWED_ORIGINS`(loopback만) | `hostConfig.ts` (구현) |
| bootstrap | launcher가 일회용 코드를 표시하고, `POST /api/v1/auth/bootstrap`이 이를 HttpOnly·SameSite=Strict cookie로 교환. 코드·키를 URL query나 `VITE_*`에 두지 않음 | 계약 `api/system.schema.json` 확정. 구현 3.5 (지금은 501) |
| 로그 redaction | 등록 비밀값(내부 토큰·API 키) → `sk-ant-*` → Bearer → key=value → 홈 경로 순서로 지우고 2000 code point로 자름. debug 레벨도 적용 | `logging/redaction.ts`, `common/redaction.py`, 공용 벡터 `tests/fixtures/redaction-cases.json` (구현) |
| 오류 응답 | `ErrorResponse`만 반환. FastAPI 기본 검증 응답(입력 echo)을 쓰지 않음. 경로·키·원문 없음 | `api/error_responses.py`, `routes/responses.ts` (구현) |
| 키 위치 | `ANTHROPIC_API_KEY`는 서버 환경에만 둔다(`.env`, Git 제외). settings API는 `configured` 불리언만 반환 | `.env.example` (구현), settings 3.5 |
| SDK 데이터 | host가 SDK import 전에 `CLINE_DIR`/`CLINE_DATA_DIR`를 `<data>/cline`로 설정(3.1 C-02) | launcher가 `SECURECODE_CLINE_HOME` 전달 (구현). host 적용 3.5 |

## 5. 데이터 디렉토리

`SECURECODE_DATA_DIR`(기본 `.securecode/`, Git 제외)를 `npm run dev`가 만든다.

```text
.securecode/
├── workspaces/<workspace_id>/   registry·index·PDF 파생 캐시 (3.3, 4.5, 4.9)
├── runtime/<workspace_id>/<session_id>/  Runtime blob (4.3)
├── cline/                       SDK CLINE_DIR/CLINE_DATA_DIR (3.5)
├── logs/                        redaction된 로그 (선택)
└── run/dev-processes.json       개발 실행 인스턴스 ID·launcher PID (종료 요청은 해당 인스턴스가 직접 처리)
```

3.1 S-07: Windows에서는 SDK `dispose` 뒤에도 같은 프로세스가 `cline/` 폴더를 지우지 못한다. 그래서 정리는 다음 기동 때 한다(3.5).

## 6. 의존성 lock

| 범위 | lock | 고정 내용 |
| --- | --- | --- |
| Node workspace (`contracts`, `apps/host`, `tools/sdk-probe`) | 루트 `package-lock.json` 하나 | `@cline/sdk@0.2.0`(integrity `sha512-QQkX72+…l83sag==`, 3.1과 동일), typescript 6.0.3, tsx 4.23.15, @types/node 22.20.5, ESLint 10.13.0, typescript-eslint 8.71.2, Prettier 3.9.10, Ajv 8.20.0 |
| Python | `services/context-service/uv.lock` | Python 3.14, FastAPI 0.162.0, uvicorn 0.54.0, httpx 0.28.x, pytest 9.2.0, ruff 0.15.22, mypy 2.4.1, jsonschema 4.26.0 |

`apps/host/package-lock.json`과 `tools/sdk-probe/package-lock.json`은 workspace lock으로 합쳐 삭제했다. 3.1의 SDK probe는 합친 구조에서 다시 실행해 62/62로 통과했다(`artifacts/verification/3.2/sdk-probe-result.json`).

## 7. 개발 명령

| 명령 | 하는 일 | 검증 상태(2026-11-05) |
| --- | --- | --- |
| `npm run dev` / `npm run stop` | service + host 기동(.env 로드, 토큰 생성, 데이터 폴더) / 시작한 launcher가 두 자식 종료 | 동작. UI·bootstrap은 PENDING 출력 |
| `npm run check` | lint·format·types·structure·생성 타입·Ruff·mypy·docstring·unit | 구현된 검사 통과, exit 3 (PENDING UI) |
| `npm run test:unit` | host·service unit | exit 3 (PENDING UI 1.3) |
| `npm run test:contracts` | fixture Ajv+jsonschema, 서비스 응답, 생성 타입 | exit 0 (포인터·컨텍스트 포함 계약 검증 통과) |
| `npm run test:integration` | 서비스 인증·상태, 개발 서버 기동/종료, SDK 도구 결과 교체 | exit 3 (PENDING 3.3~4.9) |
| `npm run test:e2e` | UI E2E | exit 3 (PENDING 1.6) |
| `npm run test:live` | opt-in live: tokens.count 실제 provider | exit 3 (SKIPPED 키/opt-in 없음, PENDING 3.6) |
| `npm run build` | 생성 타입, host 타입, Python wheel | exit 3 (PENDING UI 빌드 1.1, 패키징 3.7) |
| `npm run probe:sdk` | 3.1 SDK 호환성 검증기 | 62/62 PASS |

종료 코드: 0 = 모두 PASS, 1 = FAIL, 3 = INCOMPLETE(KNOWN/PENDING/SKIPPED). 명령별 후속 작업은 `scripts/lib/pendingSuites.ts`에 있다. 해당 명령의 검사와 인수가 모두 통과하면 0이다. 구조·코딩 규약의 기존 예외 목록은 비어 있다.

## 8. 4.1 설계와의 정합 (3.2 판단)

4.1 문서의 일부 값은 로드맵 0.4/0.7, 3.1 실측과 맞지 않는다. 3.2의 공통 계약·포트는 **로드맵과 3.1 실측을 따랐다.** 차이 목록과 4.2/4.4 결정 요청은 [3.2 인계](../handoffs/3.2-skeleton-contracts.md) 3절에 있다.
