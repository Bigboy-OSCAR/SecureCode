"""FastAPI 앱 조립(DI). 라우터·미들웨어·오류 처리기·계수기를 연결만 하고 업무 로직은 두지 않는다."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from securecode_context.api.context_select import router as context_select_router
from securecode_context.api.error_responses import register_error_handlers
from securecode_context.api.health import SERVICE_VERSION
from securecode_context.api.health import router as health_router
from securecode_context.api.middleware import install_middleware
from securecode_context.api.pdf import router as pdf_router
from securecode_context.api.request_tokens import router as request_tokens_router
from securecode_context.api.runtime_pointers import router as runtime_pointers_router
from securecode_context.api.runtime_reads import router as runtime_reads_router
from securecode_context.api.runtime_stream import router as runtime_stream_router
from securecode_context.api.source_reads import router as source_reads_router
from securecode_context.api.sources import router as sources_router
from securecode_context.api.symbols import router as symbols_router
from securecode_context.api.tokens import router as tokens_router
from securecode_context.app.maintenance import sweep_forever
from securecode_context.app.settings import ServiceSettings
from securecode_context.common.tokens import (
    AnthropicTokenCounter,
    TokenCounter,
    UnavailableTokenCounter,
)
from securecode_context.common.tokens.anthropic_counter import DEFAULT_BASE_URL
from securecode_context.common.tokens.llama_cpp_counter import LlamaCppTokenCounter
from securecode_context.common.workspace_roots import WorkspaceRootRegistry
from securecode_context.context.service import ContextSelectService
from securecode_context.pdf.tools import PdfService
from securecode_context.pointers.runtime.reads import RuntimeReader
from securecode_context.pointers.runtime.store import RuntimeStore
from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.pointers.source.derived import DerivedCacheDirectory
from securecode_context.pointers.source.ports import SourceRootPort, UnconnectedWorkspaceRoots
from securecode_context.pointers.source.registry import SourceRegistry
from securecode_context.symbols.index import RevisionStore, SymbolIndexService
from securecode_context.symbols.symbol_service import R0SymbolService


def build_token_counter(settings: ServiceSettings) -> TokenCounter:
    """
    함수 이름: build_token_counter()
    기능: 설정에 맞는 TokenCounter를 만든다. llama-cpp를 고르면 로컬 llama.cpp server로 세고,
        키가 없거나 지원하지 않는 provider면 미설정 계수기를 쓴다.
    인자: settings -> 서비스 설정
    반환값: TokenCounter 구현
    작성 날짜: 2026/11/04
    """
    if settings.token_counter == "llama-cpp":
        if settings.provider_id != "openai-compatible" or settings.provider_base_url is None:
            return UnavailableTokenCounter("llama_cpp_needs_openai_compatible_base_url")
        return LlamaCppTokenCounter(
            settings.provider_base_url,
            settings.model_id,
            settings.api_key,
            settings.token_count_timeout_seconds,
        )
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


def build_source_adapter(
    settings: ServiceSettings, roots: SourceRootPort | None, counter: TokenCounter
) -> SourceAdapter:
    """
    함수 이름: build_source_adapter()
    기능: 데이터 폴더의 Source 등록부·파생 캐시와 부분 읽기·검색을 만든다.
        root 포트가 없으면 fail-closed 기본값이다.
    인자: settings -> 서비스 설정, roots -> 작업 공간 root 포트(3.6이 연결), counter -> TokenCounter
    반환값: SourceAdapter
    작성 날짜: 2026/11/10
    """
    data_dir = settings.data_dir
    registry = SourceRegistry(
        data_dir / "sources" / "registry.sqlite",
        roots or UnconnectedWorkspaceRoots(),
        DerivedCacheDirectory(data_dir / "derived"),
        forbidden_roots=(data_dir,),
    )
    return SourceAdapter(registry, counter)


def build_pdf_service(settings: ServiceSettings, adapter: SourceAdapter) -> PdfService:
    """
    함수 이름: build_pdf_service()
    기능: Source 등록부와 같은 파생 캐시 폴더를 쓰는 PDF 서비스를 만든다(작업 폴더도 같은 볼륨).
    인자: settings -> 서비스 설정, adapter -> SourceAdapter
    반환값: PdfService
    작성 날짜: 2026/11/10
    """
    data_dir = settings.data_dir
    derived = DerivedCacheDirectory(data_dir / "derived")
    return PdfService(adapter.registry, derived, adapter.counter, data_dir / "pdf-work")


def build_context_select(app: FastAPI) -> ContextSelectService:
    """
    함수 이름: build_context_select()
    기능: 앱의 Source·Runtime·R0·PDF·계수기로 Context Selector를 만든다.
    인자: app -> 상태가 준비된 앱
    반환값: ContextSelectService
    작성 날짜: 2026/11/10
    """
    state = app.state
    runtime = (state.pointer_store, state.runtime_reader)
    return ContextSelectService(
        state.source_adapter, runtime, state.token_counter, state.symbols, pdf=state.pdf.pages
    )


def build_state(
    app: FastAPI, settings: ServiceSettings, workspace_roots: SourceRootPort | None
) -> None:
    """
    함수 이름: build_state()
    기능: 계수기가 준비된 앱에 작업 공간 root 등록부·Runtime·Source·PDF·R0·Selector를 (없는 것만) 만든다.
        root 포트를 주지 않으면 데이터 폴더의 등록부(host가 /workspaces/register로 채움)를 쓴다.
    인자: app -> 앱, settings -> 서비스 설정, workspace_roots -> 시험용 root 포트
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    state, data_dir = app.state, settings.data_dir
    counter = state.token_counter
    if not hasattr(state, "workspace_roots"):
        state.workspace_roots = workspace_roots or WorkspaceRootRegistry(
            data_dir / "workspaces.json", (data_dir,)
        )
    if not hasattr(state, "pointer_store"):
        state.pointer_store = RuntimeStore(data_dir / "runtime")
        state.runtime_reader = RuntimeReader(state.pointer_store, counter)
    if not hasattr(state, "source_adapter"):
        state.source_adapter = build_source_adapter(settings, state.workspace_roots, counter)
    if not hasattr(state, "pdf"):
        state.pdf = build_pdf_service(settings, state.source_adapter)
    if not hasattr(state, "symbols"):
        index = SymbolIndexService(
            RevisionStore(data_dir / "symbols"), state.source_adapter.registry
        )
        state.symbols = R0SymbolService(index, counter, state.workspace_roots)
    state.context_select = build_context_select(app)


def create_app(
    settings: ServiceSettings,
    token_counter: TokenCounter | None = None,
    workspace_roots: SourceRootPort | None = None,
) -> FastAPI:
    """
    함수 이름: create_app()
    기능: 내부 API 앱을 만든다. 문서 UI(/docs)는 끄고 모든 경로에 내부 인증을 건다.
    인자: settings -> 검증된 서비스 설정
        token_counter -> 시험용 주입 계수기, None이면 설정으로 만든다
        workspace_roots -> 시험용 작업 공간 root 포트, None이면 데이터 폴더 등록부
    반환값: FastAPI 앱
    작성 날짜: 2026/11/04
    """
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """
        함수 이름: lifespan()
        기능: 실행마다 계수기를 구성하고 Runtime TTL 정리 작업을 돌리며, 앱이 생성한 provider 연결만 종료한다.
        인자: app -> 현재 FastAPI 인스턴스
        반환값: 서비스 수명 컨텍스트
        작성 날짜: 2026/11/05
        """
        if not hasattr(app.state, "token_counter"):
            app.state.token_counter = build_token_counter(settings)
        counter = app.state.token_counter
        build_state(app, settings, workspace_roots)
        sweeper = asyncio.create_task(sweep_forever(app.state.pointer_store.sweep_expired))
        try:
            yield
        finally:
            sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper
            if token_counter is None and isinstance(
                counter, AnthropicTokenCounter | LlamaCppTokenCounter
            ):
                counter.close()
                del app.state.token_counter
            app.state.pointer_store.close()
            del app.state.pointer_store
            del app.state.runtime_reader
            app.state.pdf.close()
            del app.state.pdf
            app.state.source_adapter.close()
            del app.state.source_adapter
            del app.state.symbols

    app = FastAPI(
        lifespan=lifespan,
        title="SecureCode Context Service",
        version=SERVICE_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.token_counter = (
        token_counter if token_counter is not None else build_token_counter(settings)
    )
    build_state(app, settings, workspace_roots)

    install_middleware(app, settings.internal_token)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(tokens_router)
    app.include_router(request_tokens_router)
    app.include_router(context_select_router)
    app.include_router(runtime_pointers_router)
    app.include_router(runtime_reads_router)
    app.include_router(runtime_stream_router)
    app.include_router(sources_router)
    app.include_router(source_reads_router)
    app.include_router(pdf_router)
    app.include_router(symbols_router)
    return app
