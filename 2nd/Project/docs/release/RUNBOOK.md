# SecureCode 로컬 실행 RUNBOOK (3.7)

- 작성: 2026-11-11, 박준형(3.7)
- 대상: 다른 팀원, 1.6(UI end-to-end), 3.8(최종 인수)
- 명령은 모두 작업 루트(`2nd/Project`) 기준이다. 키와 개인 데이터는 이 문서와 저장소에 넣지 않는다.

## 1. 구성과 지원 범위

| 프로세스 | 위치 | 주소(기본) | 역할 |
| --- | --- | --- | --- |
| context-service (Python, FastAPI) | `services/context-service` | `127.0.0.1:8788` (내부 토큰 필수) | R0 색인·검색, Source/Runtime Pointer, Context Selector, PDF, 토큰 계수 |
| host (Node, Cline SDK 0.2.0) | `apps/host` | `127.0.0.1:8787` `/api/v1` | 브라우저 API, SDK 세션, 승인, 요청 예산 gate |
| UI (Vite + React) | `apps/ui` | `127.0.0.1:5173` | 브라우저 화면. `/api`를 host로 proxy |

- 적용 기법은 R0 원문 TF-IDF Symbol Bundle, Source Pointer, Runtime Pointer뿐이다. Context Selector와 PDF는 조정·추출 계층이다. 임베딩·요약 트리·LLM selector는 없고, `check:structure`가 이를 막는다.
- 모든 프로세스는 loopback에만 바인딩한다. 원격 배포는 범위 밖이다.
- 지원 형식, 상한, TTL은 [4.10 운용 안내](../handoffs/4.10-pointer-operations.md) 2·3절을 따른다.

### 검증된 버전 (2026-11-11, Windows 11 x64)

| 도구 | 검증한 버전 | 선언 범위 |
| --- | --- | --- |
| Node.js / npm | 26.13.0 / 11.20.0 | `engines`: `^22.12.0 \|\| ^24.0.0 \|\| ^26.0.0` (22·24는 이번에 실행하지 않음) |
| uv / Python | 0.13.7 / 3.14.10 | `requires-python >=3.14,<3.15` (uv가 설치) |
| @cline/sdk | 0.2.0 (lock 고정) | 바꾸면 `npm run probe:sdk` |
| 모델(live) | Qwen2.5-7B-Instruct Q4_K_M, llama.cpp b12242 (`openai-compatible`) | Anthropic live는 이번에 실행하지 않음 |

macOS·Linux(POSIX)에서는 실행하지 않았다. 코드에는 POSIX 경로가 있다(파일 열기 `O_NOFOLLOW`, 프로세스 그룹 종료, `bin/python`). 처음 실행하는 사람은 `npm run test:install`과 `npm run test:integration` 결과를 [3.7 기록](../progress/tasks/3.7.md)에 남긴다.

## 2. 설치

```bash
npm ci
```

```bash
uv sync --project services/context-service --locked
```

- `npm ci`는 `package-lock.json`만 따르고, `uv sync --locked`는 `uv.lock`과 `pyproject.toml`이 다르면 실패한다. lock을 바꾸려면 담당(박준형)에게 요청한다.
- `uv`가 PATH에 없으면 `UV_BIN`에 실행 파일 경로를 지정한다.
- 새 폴더에서 설치부터 재시작까지 한 번에 확인하려면 `npm run test:install`을 실행한다(5절).

## 3. 환경 변수와 모델 구성

`.env.example`을 `.env`로 복사해 값을 채운다. `.env`는 Git에서 제외되고 서버 프로세스만 읽는다. 비밀값에 `VITE_` 접두사를 붙이지 않는다(브라우저에 노출된다). `check:structure`는 저장소 파일에 키 모양 문자열이나 로컬 `.env`의 비밀값이 있으면 실패한다.

### Anthropic

```
SECURECODE_PROVIDER_ID=anthropic
SECURECODE_MODEL_ID=claude-sonnet-5-5
ANTHROPIC_API_KEY=<키>
SECURECODE_TOKEN_COUNTER=
```

토큰 수는 provider `count_tokens`의 추정값이다. 그래서 `SECURECODE_REQUIRE_FINAL_TOKEN_COUNT=true`(기본)에서는 모든 run이 `TOKENIZER_UNAVAILABLE`로 막힌다. 추정값을 허용하려면 `false`로 바꾼다. 그러면 여유분 max(1024, 창의 2%)를 둔다.

### 로컬 qwen-2.5 (llama.cpp, 정확 계수)

1. [llama.cpp](https://github.com/ggml-org/llama.cpp) 릴리스를 설치한다.
2. 임의의 비밀 문자열을 하나 정해 별도 터미널에서 서버를 켠다. 모델은 처음 실행할 때 내려받는다.
   ```bash
   llama-server -hf Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M --jinja -c 32768 --host 127.0.0.1 --port 8080 --api-key <비밀 문자열>
   ```
3. `.env`에 다음을 넣는다.
   ```
   SECURECODE_PROVIDER_ID=openai-compatible
   SECURECODE_MODEL_ID=qwen2.5-7b-instruct
   SECURECODE_PROVIDER_BASE_URL=http://127.0.0.1:8080/v1
   SECURECODE_PROVIDER_API_KEY=<같은 비밀 문자열>
   SECURECODE_TOKEN_COUNTER=llama-cpp
   SECURECODE_MODEL_CONTEXT_LIMIT=32768
   SECURECODE_MAX_OUTPUT_TOKENS=2048
   SECURECODE_REQUIRE_FINAL_TOKEN_COUNT=true
   ```
4. `curl http://127.0.0.1:8080/health`가 `{"status":"ok"}`인지 확인한다. 그다음 `SECURECODE_LIVE_SMOKE=1 npm run test:live`를 실행한다. 계수 단계에서 서버 `prompt_tokens`와 같은 값이 나와야 한다.

`SECURECODE_MODEL_CONTEXT_LIMIT`은 `-c`보다 크면 안 된다. CPU 생성 속도는 다른 무거운 프로그램(게임 등)이 돌면 초당 1토큰 아래로 떨어진다. 그러면 live smoke가 시간 초과로 실패한다.

### 그 밖의 설정

포트(`SECURECODE_HOST_PORT`, `SECURECODE_CONTEXT_SERVICE_PORT`, `SECURECODE_UI_DEV_PORT`), 데이터 폴더(`SECURECODE_DATA_DIR`), 시간 제한, 로그 수준 등은 `.env.example`의 주석을 따른다.

## 4. 실행과 중단

```bash
npm run dev
```

- 기동 순서는 context-service → host → UI다. 각 단계는 앞 단계가 준비된 뒤에 띄운다(service 내부 health `ok` → host `/api/v1/health` `ok` → UI 첫 화면).
- 시작 전에 세 포트를 모두 확인한다. 하나라도 쓰이고 있으면 아무것도 띄우지 않는다. 이때 어떤 설정을 바꿔야 하는지 출력하고 종료 코드 1로 끝낸다.
- 중간에 실패하면(예: UI가 뜨지 않음) 이미 띄운 service와 host를 멈춘다. 실행 중에 하나가 비정상 종료돼도 나머지를 멈추고 종료 코드 1로 끝낸다.
- 준비되면 UI 주소와 **1회용 launch code**(10분)를 출력한다. 브라우저에서 UI를 열고 그 code를 입력한다. code는 이 터미널에만 나온다.

멈추는 방법은 둘 중 하나다.
- 그 터미널에서 Ctrl+C (SIGINT·SIGTERM·SIGHUP 모두 처리)
- 다른 터미널에서 아래 명령
  ```bash
  npm run stop
  ```

`npm run stop`은 같은 데이터 폴더의 launcher 한 개에게 종료를 요청하고, 세 프로세스가 내려갈 때까지 최대 15초 기다린다. 파일에 적힌 PID로 직접 신호를 보내지 않는다.

같은 데이터 폴더로 launcher를 두 개 띄울 수 없다. 두 번째 launcher는 "run npm run stop first"를 출력하고 종료한다.

launcher가 강제 종료돼 `<데이터 폴더>/run/dev-processes.json`이 남은 경우:
1. 8787·8788·5173 포트를 쓰는 프로세스가 없는지 확인한다.
2. 그 파일을 지운다.

## 5. 빌드와 검사

| 명령 | 내용 | 네트워크·모델 |
| --- | --- | --- |
| `npm run check` | lint(eslint·ruff), format(prettier·ruff), 타입(tsc·mypy), 구조 검사, 생성 타입 최신 여부, Python docstring 규약, unit(host·UI·검사 규칙·service) | 없음 |
| `npm run check:structure` | 구조 검사만 | 없음 |
| `npm run test:contracts` | 계약 fixture(Ajv·Python)와 service 응답 | 없음 |
| `npm run test:integration` | 실제 프로세스: service pytest integration, 설치 SDK + 실제 service host 시험, dev launcher 수명주기(세 프로세스·포트 충돌·부분 실패 정리), host-service 연결·인증·degraded | 없음(scripted provider) |
| `npm run build` | 생성 타입, host 타입, UI 빌드, service wheel, **로컬 패키지 검사**(`dist/securecode-local/manifest.json`에 lock hash·wheel·UI asset SHA-256 기록) | 없음 |
| `npm run test:install` | 작업 트리를 새 임시 폴더에 복사 → `npm ci` + `uv sync --locked` → 새 데이터 폴더로 dev 기동 → UI proxy로 로그인·작업 공간 등록 → stop → 재시작 후 데이터 유지·health 확인 → stop. 사용자 `.securecode`는 건드리지 않는다 | npm·uv 내려받기(캐시가 있으면 빠름) |
| `SECURECODE_LIVE_SMOKE=1 npm run test:live` | 실제 provider. 토큰 계수 일치, R0 색인·답, 명령 승인 → Runtime Pointer → 부분 재조회, PDF 쪽 인용, 취소, 거절, 기록 검사 | 모델 서버 필요 |
| `npm run test:e2e` | UI 브라우저 E2E. 1.6이 작성할 때까지 PENDING | — |

- 종료 코드: `0` 모두 통과, `1` 실패, `3` 미완료다. 미완료는 다른 작업이 담당하는 기존 위반(KNOWN), 아직 없는 시험(PENDING), live opt-in 꺼짐을 뜻한다.
- 오프라인 검사(`check`, `test:contracts`, `test:integration`, `build`)는 모델과 네트워크 없이 돈다.
- live는 `SECURECODE_LIVE_SMOKE=1`일 때만 provider를 부른다.

### 구조 검사가 막는 것

| 규칙 | 내용 |
| --- | --- |
| `max-lines` | production 300줄, 시험 500줄 |
| `layout`, `test-in-src`, `temp-file`, `runtime-data` | 0.5 디렉터리 구조, src 안의 시험·임시 파일, 실행 데이터 커밋 |
| `import-cycle` | TypeScript 상대 import와 Python `securecode_context` 모듈 수준 import의 순환. 타입 전용 import와 `TYPE_CHECKING` 블록은 실행 시 순환이 아니므로 제외 |
| `forbidden-dependency` | `experiments/`·`1st/` import, `sys.path` 조작, 임베딩·RAPTOR·요약 트리·Self-Extend·LLM selector |
| `production-mock` | `apps/*/src`, `services/*/src` 안의 fixture/mock/fake 모듈, fixture·tests·mock import |
| `placeholder` | 제품 코드의 미완료 표시, 미구현 예외·status |
| `secret` | 키 모양 문자열(Anthropic·OpenAI·AWS·GitHub·Slack·개인 키)과 로컬 `.env` 비밀값 |
| `git-mutation`, `ui-boundary`, `env-secret` | 코드의 git commit/push, UI의 SDK·내부 API 직접 호출, `.env.example`의 값 있는 비밀 |

예외는 `scripts/check/structure-baseline.json`에 있다.
- `entries`: 다른 작업이 고칠 위반이다. KNOWN으로 보고되고 `check`가 미완료(종료 코드 3)로 남는다.
- `exceptions`: 근거가 있는 영구 예외다. 이유를 출력하고 PASS로 처리한다.

## 6. 데이터 폴더·정리·재시작

- 위치: `SECURECODE_DATA_DIR`(기본 `.securecode`, Git 제외). 하위 구조와 각 항목을 지워도 되는지는 [4.10 운용 안내](../handoffs/4.10-pointer-operations.md) 1절에 있다.
- 기간과 정리:
  - Runtime 출력은 기본 24시간(최대 7일) 뒤 만료된다. service가 시작할 때와 10분마다 지운다.
  - 세션을 닫으면 그 세션의 출력이 지워진다.
  - `pdf-work/`는 시작할 때 비운다.
- 재시작: `npm run stop` 뒤 `npm run dev`. 작업 공간, Source 등록, R0 색인, 포인터, SDK 기록은 같은 데이터 폴더에 남는다. `test:install`이 이를 확인한다.
- 전체 초기화:
  1. 서버를 모두 멈춘다.
  2. 데이터 폴더를 지운다. 사용자 원본 파일은 데이터 폴더에 없다.
  3. 다음 dev 기동 때 다시 만들어진다.
  4. 작업 공간과 색인은 다시 등록한다.
- 시험은 매번 새 임시 데이터 폴더를 만든다. 사용자의 `.securecode`를 쓰지 않는다.

## 7. 오류 대응

| 증상 | 원인·확인 | 조치 |
| --- | --- | --- |
| `127.0.0.1:<port> is already in use (SECURECODE_…_PORT)` | 다른 SecureCode 또는 다른 프로그램 | `npm run stop`, 또는 `.env`에서 해당 포트 변경 |
| `dev state already exists; run npm run stop first` | 같은 데이터 폴더의 launcher가 실행 중이거나 기록이 남음 | `npm run stop`. launcher가 없으면 4절의 수동 정리 |
| `context-service environment missing` | `.venv` 없음 | `uv sync --project services/context-service --locked` |
| `<name> did not become ready` / `exited during startup` | 그 프로세스의 출력(`[context-service]`·`[host]`·`[ui]` 접두사) 확인 | 설정 오류(`ConfigError`)면 `.env`를 고친다 |
| 세션 생성 503 `PROTECTION_UNAVAILABLE`, run `TOKENIZER_UNAVAILABLE`, `SERVICE_UNAVAILABLE`, `SOURCE_CHANGED`, PDF 오류 | 4.10 운용 안내 5절 | 같은 곳 |
| live 단계 시간 초과 | 모델 생성 속도(무거운 프로그램 실행 중) | 다른 프로그램을 닫고 다시 실행 |
| `npm run check`가 종료 코드 3, `KNOWN structure baseline [owner …]` | 다른 작업이 고칠 위반이 `structure-baseline.json` `entries`에 있음(2026-11-11 기준 비어 있음) | 해당 담당이 고친 뒤 항목 삭제 |
| `npm run test:e2e`가 종료 코드 3, `PENDING … [owner 1.6]` | 브라우저 runner가 아직 없음 | 1.6이 등록하고 `pendingSuites.ts` 항목 삭제 |

## 8. 실패하면 누가 어디를 고치나

| 실패한 단계 | 담당 | 수정할 곳 |
| --- | --- | --- |
| `lint`·`format`·`types: scripts`, `check:structure` 규칙 자체, `dev`/`stop`/`build`/`test:install` | 박준형 (3.2/3.7) | `scripts/**`, 루트 설정 파일 |
| `types: contracts`, `contracts: *`, 생성 타입 | 박준형 (3.2), 포인터·컨텍스트 계약은 4.2 | `contracts/**` (`npm run generate:contracts`) |
| `unit: host`, host SDK 시험, `chain: *` | 박준형 (3.5/3.6), 포인터 hook·gate는 4.4/4.8 | `apps/host/src/**` |
| `unit: context-service`, `ruff`/`mypy`, service integration | 박준형 (3.2/3.3/3.4), 포인터·selector·PDF는 4.3~4.9 | `services/context-service/src/securecode_context/**` |
| `unit: UI`, `types: apps/ui`, `build: UI`, `production-mock` (UI), `test:e2e` | 김민지 (1.1~1.6) | `apps/ui/**` |
| UI 명세·인수 표 불일치 | 김찬우 (2.1~2.3) | `docs/ui/**` |
| `test:live` 계수·도구 단계 | 박준형 (4.x 인수, 팀 합의 2026-11-10) | `scripts/lib/live*.ts`, provider 설정 |

4.x 담당은 원래 임우형이다. 2026-11-10 팀 합의로 박준형이 맡았다.
