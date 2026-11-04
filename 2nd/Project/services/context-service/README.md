# context-service

SecureCode의 Python 서비스다. R0 심볼(3.3/3.4), 포인터(4.3~4.6), 컨텍스트 선택(4.7/4.8), PDF(4.9), 내부 공용 `tokens.count`(3.2)를 인증된 loopback API `/internal/v1`로 제공한다. 브라우저는 이 서비스를 직접 호출하지 않는다.

## 실행

작업 루트에서 `npm run dev`로 실행한다. launcher가 내부 토큰을 만들어 넘겨 준다. 직접 실행할 때는 아래처럼 한다.

```bash
SECURECODE_INTERNAL_TOKEN=<32자 이상> SECURECODE_DATA_DIR=../../.securecode uv run python -m securecode_context.app
```

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
| `src/securecode_context/symbols/` | R0 포트(3.3/3.4 구현) |
| `src/securecode_context/pointers/`, `api/pointers.py`, `api/main.py`, `api/schemas.py` | 3.2 이전 포인터 MVP(임우형, 4.3/4.4 재작업). baseline으로 관리 |
| `tests/{unit,contract,integration}` | unit, 계약(`contracts/` 스키마), 실제 프로세스 시험 |

규약은 작업 루트의 `CODING_CONVENTIONS.md`를 따른다.
