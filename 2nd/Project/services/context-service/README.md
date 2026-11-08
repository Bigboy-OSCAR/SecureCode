# context-service

SecureCode의 Python 서비스다. 현재 인증된 loopback API `/internal/v1`에서 health와 토큰 계수를 제공한다. R0 로컬 인덱스는 아래 명령으로 생성한다. 브라우저는 이 서비스를 직접 호출하지 않는다.

## 실행

작업 루트에서 `npm run dev`로 실행한다. launcher가 내부 토큰을 만들어 넘겨 준다. 직접 실행할 때는 아래처럼 한다.

```bash
SECURECODE_INTERNAL_TOKEN=<32자 이상> SECURECODE_DATA_DIR=../../.securecode uv run python -m securecode_context.app
```

## R0 인덱스 생성

이 폴더에서 아래 명령을 실행한다. 첫 번째 인자에 색인할 프로젝트를 지정한다. 같은 출력 파일을 지정해 다시 실행하면 변경·이동·삭제된 소스를 반영한다.

```bash
uv run python -m securecode_context.symbols /path/to/project --out .securecode/r0-index.json
```

Python, C, C++, Java, JavaScript가 섞인 폴더도 한 번에 처리한다. JSON의 `nodes`에는 심볼별 언어·원문·위치·파일 해시·정적 참조가, `raw`에는 TF-IDF에 바로 넣을 단일 원문과 깊이 3의 참조 묶음이 들어간다. `diagnostics`에서 구문·인코딩 오류와 제외된 파일을 확인할 수 있다. 입력 소스는 UTF-8이며 로컬 생성에는 서버나 모델 키가 필요하지 않다. [언어별 심볼 범위와 서비스 연동 상태](../../INTEGRATED_SYSTEM_IMPLEMENTATION_ROADMAP.md#01-요구-해석과-이번-프로젝트의-완료-범위)

Python은 프로젝트 루트와 표준 `src/` 배치에서 로컬 import를 찾는다. 예를 들어 `src/pkg/run.py`의 `from pkg.shared import LIMIT`는 같은 프로젝트의 `src/pkg/shared.py`로 연결된다. 중첩 프로젝트는 패키징 파일 또는 독립된 `src/` 디렉터리를 기준으로 구분하며, 다른 프로젝트의 동명 선언은 별도로 취급한다.

파일 하나와 후보 하나의 상한은 각각 1 MiB다. 원문·import·위치가 선언마다 반복되어 한 파일의 단일 후보 텍스트 합이 16 MiB를 넘으면 해당 파일에 `too_large`를 기록한다. 참조 묶음은 최대 64개 심볼을 포함하며, 상한으로 참조를 생략하면 후보에 `truncated`를 표시한다. 작업 공간의 전체 단일 원문 텍스트 또는 전체 검색 후보 텍스트가 각각 128 MiB를 넘으면 생성을 중단한다. 이 경우 더 작은 소스 디렉터리를 지정해 다시 실행할 수 있다.

### 작업 공간 revision으로 생성

`--out` 대신 `--store`를 쓰면 작업 공간별 revision을 저장한다. 출력은 원문 없는 `IndexStatusResponse` JSON이다.

```bash
uv run python -m securecode_context.symbols /path/to/project --store ../../.securecode/workspaces --workspace-id ws_01J9Z6Q4TEST
```

실행할 때마다 `<store>/<workspace_id>/symbols/revisions/<번호>.json`을 완성한 뒤 `current.json`을 교체한다. 최근 2개 revision만 남긴다. 각 revision에는 파일 manifest와 크기·수정 시각, 이전 revision 대비 추가·수정·삭제·이동, 다시 만들 후보 ID와 bundle·IDF 재계산 필요 여부가 들어 있다. 검색 벡터는 3.4에서 준비하므로 상태는 `parsed`, `searchable=false`다. 이전 revision 번호로 요청하거나 색인 뒤 바뀐 파일의 원문을 요청하면 `SOURCE_CHANGED`를 반환한다.

## 레거시 Runtime Pointer API

기존 호스트 훅을 시험할 때는 이 폴더에서 별도로 실행한다. 기동 시 서버와 호스트에 동일한 `SECURECODE_INTERNAL_TOKEN`을 설정하고 서버의 `SECURECODE_DATA_DIR`에 전용 데이터 디렉터리를 지정한다.

```bash
uv run uvicorn securecode_context.api.main:app --host 127.0.0.1 --port 8000
```

`/api/v1/pointers/runtime`의 저장·목록·삭제 및 `/runtime/read` 부분 조회는 Bearer 인증을 요구한다. 새 포인터는 계약의 `ws_…`와 `ses_…` ID를 받아 `?v=1`이 붙은 URI를 반환한다. 기존 SQLite 데이터는 같은 디렉터리의 `runtime_pointers.db`에서 읽을 수 있다. 예전에 실행 디렉터리에 DB를 만들었다면, 서비스를 종료하고 그 파일의 디렉터리를 `SECURECODE_DATA_DIR`로 지정할 수 있다. 부분 읽기는 최대 16 KiB이며 응답의 `next_cursor`로 이어 읽는다. 다음 문자가 요청 상한보다 큰 경우 상한을 늘려 다시 요청한다.

## 검사 (이 폴더 기준)

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## 구조

| 경로 | 책임 |
| --- | --- |
| `src/securecode_context/app/` | 설정 검증(`settings.py`), 앱 조립(`factory.py`), 기동(`__main__.py`), 로그 설정 |
| `src/securecode_context/api/` | 내부 인증 미들웨어, 오류 응답, `health`, `tokens` router |
| `src/securecode_context/common/` | 오류 코드(`errors.py`), redaction, `tokens/`(TokenCounter 포트, Anthropic 계수기) |
| `src/securecode_context/symbols/` | R0 로컬 색인 생성, 정적 참조 그래프, 원문 후보 및 서비스 검색 포트 |
| `src/securecode_context/pointers/`, `api/pointers.py`, `api/main.py`, `api/schemas.py` | 세션별 Runtime 저장소, 파일 부분 조회용 Source 등록부 및 인증된 레거시 런타임 API |
| `tests/{unit,contract,integration}` | unit, 계약(`contracts/` 스키마), 실제 프로세스 시험 |

규약은 작업 루트의 `CODING_CONVENTIONS.md`를 따른다.
