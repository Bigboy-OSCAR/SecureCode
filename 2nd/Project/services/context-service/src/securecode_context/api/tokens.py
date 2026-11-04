"""POST /internal/v1/tokens/count: 내부 공용 tokens.count. host의 TokenCounter 포트가 이 경로를 쓴다."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from securecode_context.common.tokens import TokenCounter

router = APIRouter(prefix="/internal/v1/tokens", tags=["tokens"])


class TokenCountBody(BaseModel):
    """
    클래스 이름: TokenCountBody
    기능: 계약 TokenCountRequest 본문. 정의되지 않은 필드는 거절한다.
    작성 날짜: 2026/11/04
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] | None = None
    text: str = Field(min_length=1)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)


@router.post("/count")
def count_tokens(body: TokenCountBody, request: Request) -> dict[str, object]:
    """
    함수 이름: count_tokens()
    기능: 주입된 TokenCounter로 본문 토큰 수를 센다. 동기 함수라 provider 호출이 이벤트 루프를 막지 않는다.
    인자: body -> 검증된 요청 본문
        request -> 현재 요청(app.state.token_counter 사용)
    반환값: TokenCountResult 사전
    작성 날짜: 2026/11/04
    """
    token_counter: TokenCounter = request.app.state.token_counter
    return token_counter.count(body.text, body.model_id).to_wire()
