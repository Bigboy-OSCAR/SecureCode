"""FastAPI 앱 조립(DI). 라우터·미들웨어·오류 처리기·계수기를 연결만 하고 업무 로직은 두지 않는다."""

from fastapi import FastAPI

from securecode_context.api.error_responses import register_error_handlers
from securecode_context.api.health import SERVICE_VERSION
from securecode_context.api.health import router as health_router
from securecode_context.api.middleware import install_middleware
from securecode_context.api.tokens import router as tokens_router
from securecode_context.app.settings import ServiceSettings
from securecode_context.common.tokens import (
    AnthropicTokenCounter,
    TokenCounter,
    UnavailableTokenCounter,
)
from securecode_context.common.tokens.anthropic_counter import DEFAULT_BASE_URL


def build_token_counter(settings: ServiceSettings) -> TokenCounter:
    """
    함수 이름: build_token_counter()
    기능: 설정에 맞는 TokenCounter를 만든다. 키가 없거나 provider가 다르면 미설정 계수기를 쓴다.
    인자: settings -> 서비스 설정
    반환값: TokenCounter 구현
    작성 날짜: 2026/11/04
    """
    if settings.provider_id != "anthropic":
        return UnavailableTokenCounter("provider_not_supported")
    if settings.api_key is None:
        return UnavailableTokenCounter("api_key_missing")
    return AnthropicTokenCounter(
        api_key=settings.api_key,
        model_id=settings.model_id,
        base_url=settings.provider_base_url or DEFAULT_BASE_URL,
        timeout_seconds=settings.token_count_timeout_seconds,
    )


def create_app(settings: ServiceSettings, token_counter: TokenCounter | None = None) -> FastAPI:
    """
    함수 이름: create_app()
    기능: 내부 API 앱을 만든다. 문서 UI(/docs)는 끄고 모든 경로에 내부 인증을 건다.
    인자: settings -> 검증된 서비스 설정
        token_counter -> 시험용 주입 계수기, None이면 설정으로 만든다
    반환값: FastAPI 앱
    작성 날짜: 2026/11/04
    """
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(
        title="SecureCode Context Service",
        version=SERVICE_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.token_counter = token_counter or build_token_counter(settings)

    install_middleware(app, settings.internal_token)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(tokens_router)
    return app
