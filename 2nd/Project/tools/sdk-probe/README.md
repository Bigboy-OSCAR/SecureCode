# tools/sdk-probe — Cline SDK 호환성 검증기 (작업 3.1)

실제 `@cline/sdk@0.2.0`을 import해 `ClineCore` local backend의 수명주기·hook·승인·도구 제한·checkpoint를 검증한다. **제품 코드가 아니다.** 최종 workspace 조립과 의존성 정리는 3.2가 맡는다. 결과 해석은 [SDK_COMPATIBILITY.md](../../docs/architecture/SDK_COMPATIBILITY.md)를 본다.

## 실행

작업 루트(`2nd/Project`) 기준:

```sh
cd tools/sdk-probe
npm ci
npm run typecheck
npm run probe                     # 전체 8개 시나리오
npm run probe -- approval         # 특정 시나리오만
```

- Node 22 이상이 필요하다(`engines.node: ">=22"`). API 키는 필요 없다.
- 증거는 `artifacts/verification/3.1/sdk-probe-result.json`에 기록된다(절대경로·원문·키 제외).
- 모든 검사가 통과하고 저장소의 Git refs/stash가 그대로일 때만 종료 코드 0이다.

## 구조

| 경로 | 책임 |
| --- | --- |
| `src/env/isolated-cline-home.ts` | `CLINE_DIR`/`CLINE_DATA_DIR`를 임시 폴더로 격리. 사용자 `~/.cline`을 읽거나 쓰지 않는다 |
| `src/fixtures/anthropic-sse.ts`, `scripted-fetch.ts` | `ClineCoreOptions.fetch`에 주입하는 scripted provider. SDK의 실제 `anthropic` adapter가 만든 최종 HTTP body를 캡처하고 차단할 수 있다 |
| `src/fixtures/probe-tools.ts` | 프로젝트 소유 local tool(64 KiB sentinel 로그, 승인 대상 fixture 명령) |
| `src/fixtures/memory-pointer-fixture.ts` | **정식 Runtime Store가 아닌** 메모리 pointer fixture |
| `src/probe/` | ClineCore 생성, 공통 start 설정, afterTool pointer hook, 승인 broker, 실행 helper |
| `src/scenarios/` | 시나리오별 검증 1개씩 |
| `src/support/` | 결과 기록, payload 검사, fixture Git workspace, 증거 기록 |

검증기는 임시 fixture 폴더에서 `git init`과 읽기 전용 Git 명령만 실행한다. checkpoint를 켜지 않으며 git commit/push를 실행하지 않는다.
