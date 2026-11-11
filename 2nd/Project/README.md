# LocalDesk / SecureCode (2nd/Project)

Cline SDK를 쓰는 로컬 코드 작업 도구다. 구성은 다음과 같다.

- Python context-service: `services/context-service`
- Node host: `apps/host`
- 브라우저 UI: `apps/ui`
- 공통 계약: `contracts`

설치·설정·실행·중단·데이터 정리·오류 대응은 [RUNBOOK](docs/release/RUNBOOK.md)에, 전체 계획은 [로드맵](INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md)에, 구조와 소유권은 [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md)에 있다.

## 현재 Mac에서 앱 실행

[LocalDesk.app](dist/LocalDesk.app)을 열면 로컬 서비스와 모델이 자동 준비된다. 앱은 현재 프로젝트 경로와 설치된 의존성을 사용하는 개인용 Mac 앱이다. 프로젝트 또는 Node 설치 경로를 옮겼다면 `npm run build:app`으로 다시 만든다.

Qwen3.8-27B MLX와 다운로드한 Qwen2.5-7B GGUF를 상단 모델 메뉴에서 교체할 수 있다. 대화·프로젝트·등록 자료는 `~/Library/Application Support/LocalDesk`에 보관하며, 앱 종료 시 직접 시작한 서비스를 정리한다. 기존 `.securecode` 데이터와 모델 파일은 보존한다.

로드맵27개 작업과 최종11개 조건을 완료했다. 현재 Mac의 자동 검사·실제 모델·직접 앱 조작 결과는 [최종 인수 보고서](docs/release/ACCEPTANCE_REPORT.md)에 있다.

## 빠른 시작

- 준비물:
  - Node.js와 npm. 현재 Mac은 Node.js 22.14.0 / npm 10.9.2에서 검증했다.
  - [uv](https://docs.astral.sh/uv/). context-service는 Python 3.14를 쓰며 uv가 설치한다. `uv`가 PATH에 없으면 `UV_BIN`에 실행 파일 경로를 지정한다.

```bash
npm ci
```

```bash
uv sync --project services/context-service --locked
```

`.env.example`을 `.env`로 복사해 모델 설정을 채운다(Anthropic 또는 로컬 llama.cpp: [RUNBOOK 3절](docs/release/RUNBOOK.md#3-환경-변수와-모델-구성)). `.env`는 Git에서 제외되고, 키는 서버 환경에만 둔다.

```bash
npm run dev
```

context-service → host → UI 순서로 127.0.0.1에 뜬다. 터미널에 나온 UI 주소를 브라우저에서 열고, 같이 나온 1회용 launch code를 입력한다. 멈출 때는 Ctrl+C를 누르거나 `npm run stop`을 실행한다.

## 명령

| 명령 | 내용 |
| --- | --- |
| `npm run dev` / `npm run stop` | 세 프로세스를 readiness 순서로 시작·중단. 포트 충돌은 시작 전에 알린다 |
| `npm run check` | lint·format·타입·구조(파일 길이·순환·mock·비밀값·금지 기법·미구현 표시)·규약·unit |
| `npm run test:contracts` | 계약 fixture(TS·Python)와 service 응답 |
| `npm run test:integration` | 실제 프로세스 통합 시험(오프라인, scripted provider) |
| `npm run build:app` | 현재 Mac용 `dist/LocalDesk.app` 빌드·서명 |
| `npm run build` | 생성 타입·host 타입·UI·Python wheel·로컬 패키지 manifest |
| `npm run test:install` | 새 임시 폴더에서 설치 → 기동 → 중단 → 재시작 smoke |
| `npm run test:live` | 실제 provider smoke (opt-in: `SECURECODE_LIVE_SMOKE=1`) |
| `npm run test:e2e` | 브라우저 E2E (1.6, fixture provider + 실제 stack, Edge/Chrome headless) |
| `npm run generate:contracts` | 스키마에서 TS 타입 생성 |
| `npm run probe:sdk` | Cline SDK 호환성 검증기(3.1) |

종료 코드는 세 가지다.
- `0`: 모두 통과
- `1`: 실패
- `3`: 미완료(다른 작업의 기존 위반, 아직 없는 시험, live opt-in 꺼짐)

미구현 검사를 성공으로 표시하지 않는다.

## R0 인덱스 생성

Python, C, C++, Java, JavaScript 소스에서 R0 원문 인덱스를 만드는 로컬 명령이다. 아래 예시는 프로젝트 루트 기준이다.

```bash
uv run --project services/context-service python -m securecode_context.symbols /path/to/project --out .securecode/r0-index.json
```

출력 형식과 지원 범위는 [context-service 실행 안내](services/context-service/README.md#r0-인덱스-생성)에서 확인할 수 있다.

## 규약

- Python: [CODING_CONVENTIONS.md](CODING_CONVENTIONS.md)
- TypeScript/React: [docs/conventions/TYPESCRIPT_REACT.md](docs/conventions/TYPESCRIPT_REACT.md)
- 계약: [docs/contracts/API.md](docs/contracts/API.md), [docs/contracts/EVENTS.md](docs/contracts/EVENTS.md)

최신 사용자 지시에 따라 완료 작업 단위를 commit하고 `codex/localdesk-macos-completion` 브랜치로 push했다.
