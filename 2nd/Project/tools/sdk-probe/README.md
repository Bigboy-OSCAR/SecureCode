# tools/sdk-probe — Cline SDK 호환성 검증기 (작업 3.1)

실제 `@cline/sdk@0.2.0`을 import해 `ClineCore` local backend의 수명주기·hook·승인·도구 제한·checkpoint를 검증한다. **제품 코드가 아니다.** 최종 workspace 조립과 의존성 정리는 3.2가 맡는다. 결과 해석은 [SDK_COMPATIBILITY.md](../../docs/architecture/SDK_COMPATIBILITY.md)를 본다.

## 실행

작업 루트(`2nd/Project`)에서 실행한다. 의존성은 루트 workspace lockfile(`package-lock.json`)로 고정된다(3.2에서 통합).

```sh
npm ci
npm run probe:sdk                                   # 전체 8개 시나리오
npm run probe:sdk -- approval                       # 특정 시나리오만
npm run probe:sdk -- --no-evidence                  # 기존 검증 기록을 보존하며 전체 재검증
```

- Node 22 또는 24 LTS가 필요하다. API 키는 필요 없다.
- 증거는 `artifacts/verification/<작업>/sdk-probe-result.json`에 기록된다. 기본값은 `3.1`이고 `SDK_PROBE_TASK_ID=3.2`처럼 바꿀 수 있다. 부분 검증은 같은 폴더의 `sdk-probe-partial-result.json`에 기록한다. `--no-evidence`로 실행하면 파일을 쓰지 않는다. 절대경로·원문·키는 기록하지 않는다.
- 모든 검사가 통과하고 저장소의 Git refs/stash가 그대로일 때만 종료 코드 0이다.

## 구조

| 경로 | 책임 |
| --- | --- |
| `src/support/isolated-cline-home.ts` | `CLINE_DIR`/`CLINE_DATA_DIR`를 임시 폴더로 격리. 사용자 `~/.cline`을 읽거나 쓰지 않는다 |
| `src/fixtures/anthropic-sse.ts`, `scripted-fetch.ts` | `ClineCoreOptions.fetch`에 주입하는 scripted provider. SDK의 실제 `anthropic` adapter가 만든 최종 HTTP body를 캡처하고 차단할 수 있다 |
| `src/fixtures/probe-tools.ts` | 프로젝트 소유 local tool(64 KiB sentinel 로그, 승인 대상 fixture 명령) |
| `src/fixtures/memory-pointer-fixture.ts` | **정식 Runtime Store가 아닌** 메모리 pointer fixture |
| `src/probe/` | ClineCore 생성, 공통 start 설정, afterTool pointer hook, 승인 broker, 실행 helper |
| `src/scenarios/` | 시나리오별 검증 1개씩 |
| `src/support/` | 결과 기록, payload 검사, fixture Git workspace, 증거 기록 |

검증기는 임시 fixture 폴더에서 `git init`과 읽기 전용 Git 명령만 실행한다. checkpoint를 켜지 않으며 git commit/push를 실행하지 않는다.
