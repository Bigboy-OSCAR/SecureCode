# SecureCode (2nd/Project)

Cline SDK를 쓰는 로컬 코드 작업 도구다. 구성은 Node host(`apps/host`), Python context-service(`services/context-service`), 공통 계약(`contracts`)이며 UI(`apps/ui`)는 1.1에서 추가한다. 전체 계획은 [로드맵](INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md), 구조와 소유권은 [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md)에 있다.

## 준비

- Node.js 22 또는 24 LTS (`.nvmrc` = 24), npm
- [uv](https://docs.astral.sh/uv/). context-service는 Python 3.14를 쓰며 uv가 설치한다. `uv`가 PATH에 없으면 `UV_BIN`에 실행 파일 경로를 지정한다.

```bash
npm ci
```

```bash
uv sync --project services/context-service --frozen
```

`.env.example`을 `.env`로 복사해 필요한 값을 채운다. `.env`는 Git에서 제외된다. 키는 서버 환경에만 둔다.

## 명령

| 명령 | 내용 |
| --- | --- |
| `npm run dev` / `npm run stop` | context-service와 host를 127.0.0.1에서 시작하고 멈춘다 |
| `npm run check` | lint·format·타입·구조·규약·unit 시험 |
| `npm run test:contracts` | 계약 fixture(TS·Python)와 서비스 응답 검증 |
| `npm run test:integration` | 실제 프로세스 통합 시험 |
| `npm run test:e2e` | UI E2E (1.6) |
| `npm run test:live` | 실제 provider smoke (opt-in: `SECURECODE_LIVE_SMOKE=1`) |
| `npm run build` | 생성 타입·host 타입·Python wheel |
| `npm run generate:contracts` | 스키마에서 TS 타입 생성 |
| `npm run probe:sdk` | Cline SDK 호환성 검증기(3.1) |

`npm run stop`은 현재 데이터 디렉터리에 해당하는 launcher에게 종료를 요청하고 두 서버가 내려갈 때까지 기다린다. launcher가 비정상 종료됐거나 오래된 형식의 실행 기록이 남았으면, 먼저 두 서버가 종료됐는지 확인한 뒤 데이터 디렉터리의 `run/dev-processes.json`을 정리한다.

종료 코드 `0`은 모두 통과, `1`은 실패, `3`은 미완료(아직 없는 필수 검사, 기존 예외, 비밀값이 없어 건너뜀)다. 미구현 검사를 성공으로 표시하지 않는다.

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

git commit과 git push는 팀원이 직접 한다.
