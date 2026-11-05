"""레거시 ASGI 진입점. 설정 검증과 데이터베이스 열기는 앱 기동 시 수행한다."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from securecode_context.api.error_responses import handle_validation_error
from securecode_context.api.middleware import install_middleware
from securecode_context.api.pointers import router
from securecode_context.app.settings import load_settings
from securecode_context.pointers.runtime.sqlite_store import SQLiteRuntimeStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """함수 이름: lifespan()
    기능: 명시적으로 설정한 내부 토큰과 저장 위치를 기동 전에 검증한다.
    인자: app -> 레거시 앱
    반환값: 서비스 수명 컨텍스트
    작성 날짜: 2026/11/05
    """
    settings = load_settings(os.environ)
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    app.state.runtime_store = SQLiteRuntimeStore(settings.data_dir / "runtime_pointers.db")
    app.state.settings = settings
    yield


app = FastAPI(
    title="SecureCode Legacy Pointer Service",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_exception_handler(RequestValidationError, handle_validation_error)
app.include_router(router)
install_middleware(app)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """함수 이름: health()
    기능: 레거시 서비스의 가동 상태를 알린다.
    인자: 없음
    반환값: 상태 객체
    작성 날짜: 2026/11/05
    """
    return {"status": "ok"}
