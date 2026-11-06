"""GET /internal/v1/health: 프로세스 생존과 구성요소별 준비 상태. 미구현 기능은 not_implemented로 숨기지 않는다."""

import os
from pathlib import Path

from fastapi import APIRouter, Request

from securecode_context.common.tokens import TokenCounter

SERVICE_VERSION = "0.1.0"
PENDING_COMPONENTS = (
    ("symbols", "3.6"),
    ("pointers", "4.3"),
    ("context_selector", "4.8"),
    ("pdf", "4.9"),
)

router = APIRouter(prefix="/internal/v1", tags=["system"])


def describe_data_dir(data_dir: Path) -> dict[str, object]:
    """
    함수 이름: describe_data_dir()
    기능: 데이터 디렉토리가 존재하고 쓰기 가능한지 확인한다(경로는 응답에 넣지 않는다).
    인자: data_dir -> 서비스 데이터 디렉토리
    반환값: ComponentHealth 사전
    작성 날짜: 2026/11/04
    """
    if data_dir.is_dir() and os.access(data_dir, os.W_OK):
        return {"name": "data_dir", "status": "ok"}
    return {"name": "data_dir", "status": "unavailable", "reason_code": "SERVICE_UNAVAILABLE"}


def describe_token_counter(token_counter: TokenCounter) -> dict[str, object]:
    """
    함수 이름: describe_token_counter()
    기능: 계수기 설정 여부를 구성요소 상태로 바꾼다.
    인자: token_counter -> 앱에 주입된 TokenCounter
    반환값: ComponentHealth 사전
    작성 날짜: 2026/11/04
    """
    status = token_counter.describe()
    if status.configured:
        return {"name": "token_counter", "status": "ok"}
    return {
        "name": "token_counter",
        "status": "not_configured",
        "reason_code": "TOKENIZER_UNAVAILABLE",
    }


@router.get("/health")
def read_health(request: Request) -> dict[str, object]:
    """
    함수 이름: read_health()
    기능: 서비스 상태와 구성요소 목록을 ServiceHealthResponse 형식으로 돌려준다.
    인자: request -> 현재 요청(app.state에서 설정과 계수기를 읽는다)
    반환값: ServiceHealthResponse 사전
    작성 날짜: 2026/11/04
    """
    data_dir_health = describe_data_dir(request.app.state.settings.data_dir)
    components: list[dict[str, object]] = [
        data_dir_health,
        describe_token_counter(request.app.state.token_counter),
    ]
    components.extend(
        {"name": name, "status": "not_implemented", "owner_task": owner_task}
        for name, owner_task in PENDING_COMPONENTS
    )
    return {
        "schema_version": "1",
        "service": "context-service",
        "status": "ok" if data_dir_health["status"] == "ok" else "degraded",
        "version": SERVICE_VERSION,
        "components": components,
    }
