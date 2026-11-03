# Cline SDK 호환성 — 설치 버전·필수 확장점 검증 결과

> 작업: 3.1 · 담당: 박준형 · 확인일: 2026-11-03 (Asia/Seoul)
> 검증기: [tools/sdk-probe](../../tools/sdk-probe/README.md) · 실행 증거: [artifacts/verification/3.1/sdk-probe-result.json](../../artifacts/verification/3.1/sdk-probe-result.json) · 작업 기록: [docs/progress/tasks/3.1.md](../progress/tasks/3.1.md)

이 문서는 **설치 가능한 `@cline/sdk@0.2.0`을 실제로 import·실행해 확인한 사실**과, 그 사실에서 나온 제품 설계 규칙을 구분해 적는다. 모든 실행 검증은 실제 SDK + scripted provider(HTTP fixture)로 수행했고 live API 키는 사용하지 않았다. live provider 검증은 3.6/4.8의 범위다.

## 1. 판정 요약

| 항목 | 결과 |
| --- | --- |
| 설치·import·실행 | `@cline/sdk@0.2.0`(npm `latest`)을 lockfile로 고정하고 `ClineCore` local backend 실행 성공 |
| 수명주기 | `create/start/send/subscribe/abort/stop/dispose` 실행 확인 |
| Runtime Pointer 교체 | `hooks.afterTool`의 `result` 교체 → 2번째 provider 요청·canonical history·저장 transcript·Core 이벤트에 sentinel 원문 0건, pointer만 존재 |
| beforeModel | messages/tools/options 관측, tool 제거·message projection 반영, `stop`으로 provider 호출 0회. **최종 요청이 아님**(뒤에 SDK 변환이 더 있음) |
| 최종 요청 차단 위치 | `ClineCoreOptions.fetch` wrapper. provider 변환·tool framing 이후의 실제 HTTP body를 계수·차단 가능 |
| 승인·취소 | 거절/승인/timeout/입력 digest 불일치 확인. **SDK는 abort/stop 때 대기 중 승인을 끝내지 않음** → 앱 승인 broker 필수 |
| hook 실패 | 저장 실패·저장 timeout 때 실행 실패, 원문 전송 0건. **SDK가 hook timeout을 강제하지 않음** → 앱 timeout 필수 |
| 도구 제한 | `enableTools: false` + `extraTools`가 허용 목록을 고정. `toolPolicies`만으로는 provider `web_search`가 남음 |
| checkpoint | `checkpoint.enabled: false`에서 `createCheckpoint` 호출 0회, fixture Git status/refs/stash 불변, 팀 저장소 refs/stash 불변 |
| 검증 수 | 8개 시나리오, 62/62 검사 통과 |

## 2. 고정 버전·다운로드 근거·Node 조건

| 패키지 | 고정 버전 | 근거 |
| --- | --- | --- |
| `@cline/sdk` | `0.2.0` | npm dist-tag `latest` = 0.2.0 (`nightly` = 0.2.0-nightly.1793312794). 게시 2026-10-26T03:34:32Z. tarball `https://registry.npmjs.org/@cline/sdk/-/sdk-0.2.0.tgz`, integrity `sha512-QQkX72+O5kppf9iPjG2in/ErGDT5nE/yC6IhKlY2SEY9UMOon65F6poAeQJj9CRxjvCfttkeqEiX47J+l83sag==`, shasum `69e8364012f2c28521a5c531735033610d116b58` |
| `@cline/core` | `0.2.0` | `@cline/sdk`의 유일한 의존성. `@cline/sdk`의 `index.d.ts`는 `export * from "@cline/core"` 한 줄 |
| `@cline/agents`, `@cline/llms`, `@cline/shared` | `0.2.0` | `@cline/core@0.2.0`의 고정 의존성 |
| `typescript` / `tsx` / `@types/node` | `6.0.3` / `4.23.15` / `22.20.5` | 검증기 개발 의존성(정확한 버전 고정) |

- **Node 조건:** 다섯 `@cline/*` 패키지 모두 `engines.node: ">=22"`. 공식 개요 문서도 "Node.js 22 or later"라고 적는다.
- 실제 실행 환경: Node v26.13.0, npm 11.20.0, Windows 11. 전이 의존성 `@sap/xsenv@6.2.2`(`@jerome-benoit/sap-ai-provider` 경유)가 `^20 || ^22 || ^24`만 허용해 EBADENGINE 경고를 냈다. 이번 시나리오에서 실행 오류는 없었다. **3.2는 제품 Node를 22 또는 24 LTS로 고정하고 이 검증기를 다시 실행한다.**
- 로드맵 0.4의 source ref `775d0398…`의 source version 0.2.0과 npm 배포 버전이 일치한다.
- 고정 lockfile: [tools/sdk-probe/package-lock.json](../../tools/sdk-probe/package-lock.json). 3.2는 최종 workspace로 옮길 때 같은 버전·integrity를 유지한다.
- 설치 시 `protobufjs`, `esbuild` postinstall이 npm `allowScripts` 정책 때문에 실행되지 않았다. 검증기 실행에는 영향이 없었다.

## 3. TypeScript 소비 조건 (중요)

설치된 `.d.ts`는 `./models`처럼 **확장자 없는 상대 import**를 사용한다.

| `moduleResolution` | 미해결 모듈 수(`tsc --traceResolution`) | 결과 |
| --- | --- | --- |
| `NodeNext` | 457 | SDK 타입 상당수가 `skipLibCheck` 아래에서 조용히 `any`로 바뀌었다. `execute(input, context)`가 implicit any로 보고됐다 |
| `Bundler` | 257, 모두 Node 내장 모듈(`node:*` 등, `@types/node` ambient 선언으로 해결) | SDK 타입이 모두 해결됐다. 타입 오류 0 |

규칙: SDK를 import하는 TypeScript 패키지는 `"module": "ESNext"`, `"moduleResolution": "Bundler"`, `strict`를 사용한다. 실행은 `tsx` 또는 bundler로 한다. `NodeNext`에서 통과한 타입 검사는 SDK 타입 검증으로 인정하지 않는다.

`@cline/sdk`가 export하지 않는 hook context 타입은 공개 타입에서 유도한다. 예: `Parameters<NonNullable<AgentHooks["afterTool"]>>[0]`. `extraTools`는 `AgentTool<unknown, unknown>[]`이므로 도구 입력은 `unknown`으로 받아 검증한다.

## 4. 확정한 호출 표면 (설치 `.d.ts` 기준)

| 용도 | 실제 이름·시그니처 | 위치 |
| --- | --- | --- |
| 생성 | `ClineCore.create(options?: ClineCoreOptions): Promise<ClineCore>`. 사용 필드: `clientName`, `distinctId`, `backendMode: "local"`, `automation: false`, `fetch`, `capabilities.{requestToolApproval, toolExecutors}`. `telemetry`를 생략하면 no-op | `core/dist/ClineCore.d.ts`, `cline-core/types.d.ts` |
| 시작 | `start(input: ClineCoreStartInput): Promise<StartSessionResult>`. 결과: `{ sessionId, manifest, manifestPath, messagesPath, result?: AgentResult, pluginIssues? }` | 같은 위치, `runtime/host/runtime-host.d.ts` |
| 후속 턴 | `send(input: SendSessionInput): Promise<AgentResult \| undefined>`. 입력: `{ sessionId, prompt, mode?, delivery?: "queue" \| "steer", timeoutMs? }` | `RuntimeHost["runTurn"]` |
| 중단·종료 | `abort(sessionId, reason?)`: 현재 턴만 중단하고 세션 유지. `stop(sessionId)`: 세션 종료. `dispose(reason?)`: 인스턴스 정리 | `RuntimeHost` |
| 이벤트 | `subscribe(listener: (event: CoreSessionEvent) => void, options?: { sessionId? }): () => void` | `types/events.d.ts` |
| canonical history | `readMessages(sessionId)`(저장본), `readLiveMessages(sessionId)`(상주 세션 우선), `readDisplayMessages`(UI 투영) | `ClineCore.d.ts` |
| hook | `config.hooks: AgentHooks` = `beforeRun/afterRun/beforeModel/afterModel/beforeTool/afterTool/onEvent` | `shared/dist/agent.d.ts` |
| afterTool | 반환 `{ result?: AgentToolResult, appendContext?, stop?, reason? }`. `result`가 있으면 결과를 교체 | 같은 위치 |
| beforeModel | context `{ snapshot, request: { systemPrompt?, messages, tools, modelTools?, options? } }`, 반환 `{ stop?, reason?, messages?, tools?, options? }` | 같은 위치 |
| 도구 정책 | `toolPolicies: Record<string, { enabled?: boolean; autoApprove?: boolean }>` (start input과 config 모두). 둘 다 기본값 true | `shared/dist/llms/tools.d.ts` |
| 승인 | `requestToolApproval(request: { sessionId, agentId, conversationId, iteration, toolCallId, toolName, input, policy }) => { approved, reason? }` | 같은 위치 |
| 내장 도구 교체 | `capabilities.toolExecutors: { readFile, search, bash, webFetch, editor, applyPatch, skills, askQuestion, submit }` | `core/dist/extensions/tools/types.d.ts` |
| provider 도구 끄기 | `setModelToolEnabledGlobally("web_search", false)` (`CLINE_DIR`의 global settings에 기록) | `core/dist/services/global-settings.d.ts` |
| 데이터 경로 | 환경변수 `CLINE_DIR`, `CLINE_DATA_DIR`(+ `CLINE_SESSION_DATA_DIR` 등)로 SDK 저장소 위치 지정 | 번들 코드 확인 |

내장 도구 이름(`DefaultToolNames`): `read_files`, `search_codebase`, `run_commands`, `fetch_web_content`, `apply_patch`, `editor`, `skills`, `ask_question`, `submit_and_exit`. provider 실행 도구: `web_search`, `image_generation`.

## 5. 검증된 필수 설정

```ts
const core = await ClineCore.create({
    clientName: "securecode-host",
    backendMode: "local",                 // fetch 차단 지점은 local 실행에서만 유효
    automation: false,
    fetch: finalRequestGateFetch,         // 최종 outbound payload 계수·차단 (4.8)
    capabilities: { requestToolApproval: approvalBroker.requestToolApproval, toolExecutors },
});
await core.start({
    prompt,
    interactive: true,                    // false면 첫 run 뒤 세션이 끝남
    toolPolicies,                         // 모든 허용 도구에 명시; 수정·명령은 autoApprove: false
    config: {
        providerId, modelId, apiKey, cwd, workspaceRoot, systemPrompt, mode: "act",
        enableTools: false,               // 내장 도구와 provider web_search 제거; extraTools는 유지
        extraTools: projectOwnedTools,    // 프로젝트 wrapper만 노출
        enableSpawnAgent: false, enableAgentTeams: false,
        disableMcpSettingsTools: true, mcpApps: false, yolo: false,
        hookErrorMode: "throw",
        hooks: { afterTool: pointerHook, beforeModel: requestObserver },
        checkpoint: { enabled: false },
        compaction: { enabled: false },   // 암묵 요약 금지 (로드맵 0.1)
        maxTokensPerTurn: reservedOutputTokens,
    },
    localRuntime: { configExtensions: [] },  // 사용자 rules/skills/workflows/plugins/file hooks 미적재
});
```

host는 SDK를 import하기 전에 `CLINE_DIR`/`CLINE_DATA_DIR`를 앱 전용 디렉토리(예: `.securecode/cline/`)로 설정한다. 그래야 사용자 `~/.cline`의 설정·플러그인·세션이 섞이지 않는다. 검증기는 임시 폴더로 격리했고, 실행 후 실제 `~/.cline`에 새 파일이 없음을 확인했다.

## 6. 요구별 실행 증거

| 요구 (로드맵 3.1) | 시나리오 → 검사 | 결과 |
| --- | --- | --- |
| create/start/send/subscribe/abort/stop/dispose | `lifecycle`: 첫 결과, 2번째 send, 진행 중 provider 요청 abort → `finishReason=aborted`, abort 뒤 재사용, stop 뒤 send 거부(`SessionNotFoundError`), dispose, 이벤트 타입 `agent_event/chunk/ended/session_snapshot/status` | 10/10 |
| 도구 실행 중 abort | `lifecycle`: 실행 중 도구에 `context.signal` 전달, 343 ms 안에 `aborted`, 이후 provider 요청 없음 | 포함 |
| 2회 요청·원문 제거·pointer 전달 | `pointer-replacement`: 요청 2회, 64 KiB sentinel 생성, afterTool 교체 1회, 요청 #2에 pointer 있음·sentinel 없음(1,040 bytes), tool_use→tool_result 쌍 유지, `readMessages`·`messages.json`·Core 이벤트 27건에 sentinel 0건 | 10/10 |
| beforeModel 관측·차단·순서 | `before-model`: 호출마다 messages/tools 관측, `text,tool-call,tool-result` 순서, tool 제거와 message projection이 outbound에 반영, projection은 canonical history를 바꾸지 않음, `stop` 시 provider 요청 0회 | 10/10 |
| 최종 payload 계수·차단 위치 | `outbound-gate`: fetch 경계에서 cap 초과 요청 #2 차단(재시도 0, 1회 시도), 차단 body는 scripted server에 도달하지 않음, run은 `error`로 종료, Core 이벤트에 `BUDGET_EXCEEDED` 표시 | 4/4 |
| 승인 요청/거절/timeout/취소 | `approval`: 거절 → 실행 0·모델에 `is_error` tool_result, 승인 → 실행 1, digest 불일치 거부, 300 ms timeout → 실행 0·늦은 결정 거부, raw abort 결함 재현, broker 취소+abort → 실행 0·늦은 승인 거부 | 10/10 |
| hook 저장 실패/timeout | `hook-failure`: 저장 실패·저장 timeout → run `error`, 요청 1회, 원문 누출 0. direct/object plugin hook의 SDK timeout 부재 기록 | 7/7 |
| provider 도구 비활성화·허용 목록·교체 | `tool-restriction`: `enableTools:false` → `probe_generate_log`만 노출. policies만 쓰면 `web_search`가 남음. 숨긴 `run_commands` 호출 → executor 0회·error 결과. `toolExecutors.readFile` 교체 → wrapper 1회. global web_search off 확인 | 7/7 |
| checkpoint 비활성화·Git 불변 | `checkpoint`: spy 0회, fixture status/refs/stash 불변. 전체 실행 전후 팀 저장소 refs/stash 동일 | 4/4 |

## 7. 공개 문서와 설치 API의 차이

| 주제 | 공개 문서(docs.cline.bot, 2026-11-03 조회) | 설치 0.2.0 실측 | 제품 대응 |
| --- | --- | --- | --- |
| hook timeout | 각 hook 호출 3초 timeout | direct `hooks`와 object-form `extensions` hook 모두 4.5초 대기를 끝까지 기다렸다. timeout 없음 | 앱 hook 안에서 자체 timeout으로 **throw**(검증: 500 ms 저장 timeout → 실패 차단) |
| `hookErrorMode: "ignore"` | 기본값. 실패를 기록하고 계속 진행 | direct/object plugin hook의 예외는 `ignore`에서도 run을 실패시켰다(fail-closed). 번들 코드에 `hookErrorMode`를 보는 guarded plugin 경로가 있으나, 어떤 형태에 적용되는지(file plugin 추정)는 미검증 | 그래도 `"throw"`를 명시한다. file plugin은 `configExtensions: []`로 적재하지 않는다 |
| `toolPolicies.enabled:false` | 모델이 도구를 보지 못함 | 내장 local 도구에는 적용된다. provider `web_search`는 `enableTools:true`이면 정책과 무관하게 추가된다 | `enableTools:false` + `extraTools`. 필요하면 global web_search off도 함께 적용 |
| tool policy 기본값 | 정책 없는 도구는 enabled+autoApprove | 일치(`ToolPolicy` 기본 true) | 모든 허용 도구에 명시 정책 |
| abort | 진행 중 도구 실행을 중단하고 세션 유지 | 일치. 단 **대기 중 `requestToolApproval`은 끝내지 않는다**. 늦게 approved가 오면 abort 뒤에도 도구가 실행됐다(raw 재현 1회). stop/dispose는 승인이 정리될 때까지 대기 | 3.5 승인 broker가 취소·종료·timeout 때 대기 승인을 먼저 거절하고 늦은 결정을 거부 |
| `toolPolicies` 위치 | `start()`에 전달 | `ClineCoreOptions.toolPolicies`, start input, `config.toolPolicies` 모두 존재. 검증기는 start input과 config에 같은 값을 전달 | 3.5가 한 곳(start input)으로 정하고 config에도 동일 값 |
| `beforeModel` options | 요청 options 변경 가능 | request 객체에는 병합되지만 Core model adapter는 `max_tokens`를 session config에서 읽는다. `options.maxTokensPerTurn=321` → outbound `max_tokens=1024` | 출력 예약은 `config.maxTokensPerTurn`. 최종 gate는 outbound `max_tokens`를 읽는다 |
| 요청 투영 | `prepareTurn`/`beforeModel`이 provider 요청을 정함 | beforeModel 뒤 Core message builder가 tool result를 **8,000자 head/tail로 자른다**(`...[truncated N chars]...`, env `CLINE_MESSAGE_BUILDER_MAX_TOOL_RESULT_CHARS`). 총 text 예산과 오래된 `read_files` 결과 치환 규칙도 있다. canonical history는 원문 전체(64 KiB)를 유지한다 | pointer 임계값을 SDK 자르기 한도보다 작게 둔다(8절 S-03). beforeModel 검사는 최종 cap이 아니다 |
| 이벤트 | `AgentRuntimeEvent` 예시만 | Core `subscribe`는 `CoreSessionEvent`(`agent_event/chunk/ended/session_snapshot/status/...`)를 준다. `agent_event.content_end`가 도구 output을 hook 이후 값으로 싣는다. status는 `running/pending(승인 대기)/idle/completed/cancelled` | AppEvent mapper가 output을 다시 cap(0.6). SDK 이벤트를 UI로 직접 전달하지 않음 |
| `interactive` | 설명 없음 | `false`면 start의 첫 run 뒤 세션이 끝나 `send`가 `SessionNotFoundError` | 대화형 세션은 `interactive:true` |
| 결과 | — | start/send는 실패·중단에도 대개 **resolve**하고 `finishReason`(`completed/aborted/error/...`)으로 알린다 | host는 예외가 아닌 `finishReason`으로 run 상태를 확정 |
| 설치·Node | `npm install @cline/sdk`, Node 22+ | 일치 | Node 22/24 LTS 고정 |

## 8. 발견 사항과 후속 설계 규칙

- **S-01 승인 대기 취소 부재 (3.5):** 앱 broker가 승인 ID·입력 digest(sha256)·만료시각을 만든다. timeout, run 취소, 세션 종료 때 `{ approved:false }`로 먼저 정리하고, 이미 정리된 승인에 대한 늦은 결정은 거부한다. 순서: `broker.cancelSession(sessionId)` → `core.abort/stop`. 검증기 [approval-broker.ts](../../tools/sdk-probe/src/probe/approval-broker.ts)는 검증용 최소 구현이다.
- **S-02 provider 도구 유입 (3.5):** `enableTools:false`로 내장 도구·`web_search`를 함께 제거하고 프로젝트 wrapper를 `extraTools`로만 등록한다. 내장 executor 재사용이 필요하면 `enableTools:true` + 단일 도구 허용 정책 + `toolExecutors` wrapper + global `web_search` off를 함께 적용하고, 첫 요청의 tools 목록을 시작 시 검증한다.
- **S-03 SDK의 tool result 자르기 (4.1/4.4):** 8,000자(문자 단위) 초과 tool result는 provider 요청에서만 잘리고 history에는 원문이 남는다. 따라서 Runtime Pointer 임계값은 `min(16 KiB, 8,000자 미만의 안전값)`으로 정한다. 그래야 SDK 자르기가 일어나지 않는다. afterTool은 원문 전체를 받는다(64 KiB 저장 확인). 최종 gate는 outbound tool_result에 SDK 자르기 표식이 있으면 정책 위반으로 기록한다.
- **S-04 hook timeout (4.4):** SDK에 기대지 않는다. pointer hook 내부에서 저장 크기·시간 제한을 적용하고 실패 시 throw한다. `hookErrorMode:"throw"`를 명시하고, 필수 hook을 등록하지 못하면 세션 시작을 차단한다.
- **S-05 최종 요청 계산 (4.8):** `beforeModel`(관측·조기 차단)과 fetch gate(최종 hard cap)를 분리한다. fetch gate는 실제 body의 `system/tools/messages/tool_choice/max_tokens`로 계산한다. body에는 표준 외 필드 `fallbacks: "default"`와 `cache_control`도 있으므로 계수 요청에는 허용 필드만 복사한다.
- **S-06 이벤트 원문 (3.5):** afterTool 교체가 없으면 Core 이벤트·history에 원문이 그대로 남는다. AppEvent/SSE 변환에서도 크기 cap을 적용한다.
- **S-07 Windows 파일 잠금 (3.2):** `dispose` 뒤에도 같은 프로세스에서 SDK 데이터 폴더를 지우지 못했다(EPERM). 정리는 다음 시작 시 수행한다.

## 9. 최종 요청 계수·차단 위치와 tokenizer

요청 처리 순서(실측): `prepareTurn` → `beforeModel` hook → Core message builder(tool result 8,000자 자르기 등) → provider adapter(`anthropic`: system/tools/messages 직렬화, `cache_control`, `tool_choice`, `max_tokens`) → **`ClineCoreOptions.fetch`**.

- **최종 차단 위치:** local backend에서 `ClineCoreOptions.fetch`. 차단된 요청은 프로세스를 떠나지 않았고 SDK는 재시도하지 않았다(1회 시도). hub/remote backend에서는 이 fetch가 다른 프로세스에 있으므로 제품은 `backendMode: "local"`만 쓴다.
- **beforeModel 크기 ≠ outbound 크기:** 요청 #1은 beforeModel view 709 bytes, outbound 598 bytes였다. 요청 #2는 각각 67,496 / 8,891 bytes였다. beforeModel 검사만으로 최종 cap을 주장하지 않는다.
- **지원 모델:** provider `anthropic`, model `claude-sonnet-5-5`. SDK catalog 기준 context window 1,000,000, 최대 출력 128,000이다. 제품 cap은 이보다 작은 설정값을 쓴다.
- **tokenizer 결정:** Claude 모델용 공개 로컬 tokenizer는 없다. 최종 body에서 추린 `model/system/tools/messages/tool_choice`로 Anthropic `POST /v1/messages/count_tokens`를 호출해 계수한다. 공식 문서상 이 값은 **estimate**이고, 무료이며 RPM 제한이 있다. 따라서 `count_mode`는 `provider_estimate`, 응답 뒤 `usage.input_tokens`는 `provider_reported`로 기록하고 hard cap에는 safety margin을 둔다. 계수 endpoint를 쓸 수 없으면 hard-cap 보장 모드에서 `TOKENIZER_UNAVAILABLE`로 차단한다. 문자열 길이/4나 byte 수를 토큰 수라고 표시하지 않는다(검증기 gate는 **bytes 기준이며 token 계수가 아님**).
- **3.1에서 하지 않은 것:** live `count_tokens` 호출과 실제 provider 응답의 `usage` 대조. API 키가 필요하므로 4.8/3.6의 live 검증 항목이다.

## 10. `.env.example` 사양 (값 없이 이름·의미만, 작성은 3.2)

| 변수 | 의미 | 비고 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | provider 키. 서버 프로세스에만 둔다 | VITE_ 접두사 금지, 로그 redaction |
| `SECURECODE_PROVIDER_ID` | SDK `providerId` | 검증값 `anthropic` |
| `SECURECODE_MODEL_ID` | SDK `modelId` | 검증값 `claude-sonnet-5-5` |
| `SECURECODE_PROVIDER_BASE_URL` | 선택. 프록시/게이트웨이 base URL | 비우면 SDK 기본 |
| `SECURECODE_MODEL_CONTEXT_LIMIT` | 제품이 쓰는 입력 한도(token) | catalog 값 이하 |
| `SECURECODE_MAX_OUTPUT_TOKENS` | `config.maxTokensPerTurn` = 출력 예약 | beforeModel options로 바꾸지 않음 |
| `SECURECODE_CONTEXT_SAFETY_MARGIN_TOKENS` | estimate 오차 여유분 | 4.8 확정 |
| `SECURECODE_REQUIRE_FINAL_TOKEN_COUNT` | hard-cap 보장 모드. 계수 불가 시 차단 | 기본 true 권장 |
| `SECURECODE_CLINE_HOME` | host가 SDK import 전에 `CLINE_DIR`/`CLINE_DATA_DIR`로 설정할 앱 전용 경로 | 사용자 `~/.cline`과 분리 |
| `SECURECODE_APPROVAL_TIMEOUT_MS` | 승인 대기 만료 | broker가 강제 |
| `SECURECODE_HOOK_TIMEOUT_MS` | pointer/budget hook 자체 timeout | SDK timeout 없음(S-04) |

`CLINE_MESSAGE_BUILDER_MAX_TOOL_RESULT_CHARS`는 사용자 설정으로 노출하지 않는다. host는 pointer 임계값이 이 한도보다 작은지 시작 시 확인한다.

## 11. 제한

- live provider, live `count_tokens`, 실제 네트워크 오류와 재시도 동작은 검증하지 않았다.
- Node 26.13.0에서만 실행했다. Node 22/24 재검증은 3.2 lock 시점에 한다.
- checkpoint fixture 저장소에는 commit이 없다(검증기는 git commit을 실행하지 않는다). 대신 `createCheckpoint` spy로 checkpoint 경로가 호출되지 않음을 직접 확인했다. checkpoint를 켠 대조 실험은 금지 규칙에 따라 하지 않았다.
- file-form plugin(`pluginPaths`)의 guarded hook 경로와 MCP 서버 연결은 비활성화 대상이므로 동작을 검증하지 않았다.
- 메모리 pointer fixture와 승인 broker는 검증기 전용이다. 정식 Runtime Store는 4.3, 승인 API는 3.5가 구현한다.
