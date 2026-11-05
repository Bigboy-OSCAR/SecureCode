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

파일 하나와 후보 하나의 상한은 각각 1 MiB다. 원문·import·위치가 선언마다 반복되어 한 파일의 단일 후보 텍스트 합이 16 MiB를 넘으면 해당 파일에 `too_large`를 기록한다. 참조 묶음은 최대 64개 심볼을 포함하며, 상한으로 참조를 생략하면 후보에 `truncated`를 표시한다. 작업 공간의 전체 단일 원문 텍스트 또는 전체 검색 후보 텍스트가 각각 128 MiB를 넘으면 생성을 중단한다. 이 경우 더 작은 소스 디렉터리를 지정해 다시 실행할 수 있다.

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
| `src/securecode_context/pointers/`, `api/pointers.py`, `api/main.py`, `api/schemas.py` | 3.2 이전 포인터 MVP(임우형, 4.3/4.4 재작업). baseline으로 관리 |
| `tests/{unit,contract,integration}` | unit, 계약(`contracts/` 스키마), 실제 프로세스 시험 |

규약은 작업 루트의 `CODING_CONVENTIONS.md`를 따른다.
