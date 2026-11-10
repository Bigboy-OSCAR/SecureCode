"""내부 PDF 경로(4.9): /internal/v1/pdf/parse|status|cancel. 페이지 본문은 /source/read(pdf_page)로만 읽는다.

host 공개 route(3.6)가 인증된 workspace를 넣어 호출한다. 응답은 계약 PdfJobStatus이며 추출 본문이 없다.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from securecode_context.pdf.tools import PdfService

router = APIRouter(prefix="/internal/v1/pdf", tags=["pdf"])
WorkspaceIdField = Annotated[str, Field(pattern=r"^ws_[A-Za-z0-9-]{8,64}$")]
JobIdField = Annotated[str, Field(pattern=r"^pdf_[A-Za-z0-9-]{8,64}$")]


class ParseBody(BaseModel):
    """
    클래스 이름: ParseBody
    기능: 계약 PdfParseRequest. idempotency_key는 형식만 확인하고 job은 원본 해시로 재사용한다.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    workspace_id: WorkspaceIdField
    pointer: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class JobBody(BaseModel):
    """
    클래스 이름: JobBody
    기능: job 상태 조회·취소 요청.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    workspace_id: WorkspaceIdField
    job_id: JobIdField


def _pdf(request: Request) -> PdfService:
    """
    함수 이름: _pdf()
    기능: 앱 수명 동안 공유하는 PDF 서비스를 꺼낸다.
    인자: request -> 인증된 요청
    반환값: PdfService
    작성 날짜: 2026/11/10
    """
    service: PdfService = request.app.state.pdf
    return service


@router.post("/parse")
async def parse_pdf(request: Request, body: ParseBody) -> dict[str, object]:
    """
    함수 이름: parse_pdf()
    기능: 등록된 PDF Source의 parse job을 제출하거나 같은 job 상태를 돌려준다.
    인자: request -> 인증된 요청, body -> PdfParseRequest
    반환값: PdfJobStatus
    작성 날짜: 2026/11/10
    """
    return await run_in_threadpool(_pdf(request).parse, body.workspace_id, body.pointer)


@router.post("/status")
async def pdf_status(request: Request, body: JobBody) -> dict[str, object]:
    """
    함수 이름: pdf_status()
    기능: job 상태를 돌려준다. 끝난 job은 원본 변경을 다시 확인한다.
    인자: request -> 인증된 요청, body -> job 요청
    반환값: PdfJobStatus
    작성 날짜: 2026/11/10
    """
    service = _pdf(request)
    return await run_in_threadpool(service.jobs.status, body.workspace_id, body.job_id)


@router.post("/cancel")
async def cancel_pdf(request: Request, body: JobBody) -> dict[str, object]:
    """
    함수 이름: cancel_pdf()
    기능: 진행 중 job을 취소한다(멱등). 이후 조회는 NOT_FOUND다.
    인자: request -> 인증된 요청, body -> job 요청
    반환값: {"cancelled": true}
    작성 날짜: 2026/11/10
    """
    service = _pdf(request)
    await run_in_threadpool(service.jobs.cancel, body.workspace_id, body.job_id)
    return {"cancelled": True}
