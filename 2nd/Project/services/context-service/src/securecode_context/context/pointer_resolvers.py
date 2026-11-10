"""Source·Runtime 포인터 후보 resolver(4.8). 해석은 범위→버전→해석 순서이고, 읽기는 4.6/4.3 reader로만 한다.

같은 대상은 Source가 (파일 경로, 원본 SHA-256), Runtime이 (포인터 ID, checksum)이다.
"""

from dataclasses import dataclass, replace
from typing import Any

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.context.models import Candidate, Material, Span, Status, Wire
from securecode_context.context.pdf_resolver import PdfResolver, PdfTarget
from securecode_context.pointers.limits import MAX_READ_TOKENS
from securecode_context.pointers.models.runtime import RuntimeStoreError
from securecode_context.pointers.runtime.reads import RuntimeReader, pointer_id_of
from securecode_context.pointers.runtime.store import RuntimeStore
from securecode_context.pointers.source.adapter import SourceAdapter
from securecode_context.pointers.source.media import PDF_MEDIA
from securecode_context.pointers.text.models import ByteSpan, ReadRequest, Selector

MAX_FRAGMENT_READ_BYTES = 16 * 1024
_STATUS = {
    ErrorCode.FORBIDDEN: "unauthorized",
    ErrorCode.SOURCE_CHANGED: "stale",
    ErrorCode.EXPIRED: "stale",
}


@dataclass(frozen=True)
class PointerTarget:
    """
    클래스 이름: PointerTarget
    기능: 해석한 포인터 대상. selection에 쓸 revision·SHA-256과 표시 이름을 담는다.
    작성 날짜: 2026/11/10
    """

    pointer: str
    kind: str
    revision: int
    content_sha256: str
    object_key: tuple[str, ...]
    byte_size: int
    display: str


def status_of(error: ServiceError) -> Status:
    """
    함수 이름: status_of()
    기능: 해석 오류를 상태로 바꾼다. 범위 밖이면 unauthorized, 버전 불일치·만료면 stale, 나머지는 no_match.
    인자: error -> resolver 오류
    반환값: Status
    작성 날짜: 2026/11/10
    """
    if error.code in (ErrorCode.TOKENIZER_UNAVAILABLE, ErrorCode.SERVICE_UNAVAILABLE):
        raise error
    return _STATUS.get(error.code, "no_match")  # type: ignore[return-value]


def selection_wire(target: PointerTarget, start: int, end: int) -> Wire:
    """
    함수 이름: selection_wire()
    기능: 계약 PointerSelection(바이트 구간)을 만든다.
    인자: target -> 대상, start/end -> 반열린 바이트 구간
    반환값: PointerSelection 사전
    작성 날짜: 2026/11/10
    """
    return {
        "revision": target.revision,
        "content_sha256": target.content_sha256,
        "range": {"type": "byte", "start": start, "end": end},
    }


def resolve_span(candidate: Candidate, target: PointerTarget) -> Candidate:
    """
    함수 이름: resolve_span()
    기능: ref의 selection(없으면 전체)을 대상 구간으로 확인한다. revision·SHA-256이 다르면 stale,
        범위가 비었거나 크기 밖이면 no_match다.
    인자: candidate -> 후보, target -> 해석한 대상
    반환값: status·span·handle을 채운 후보
    작성 날짜: 2026/11/10
    """
    selection = candidate.ref.get("selection")
    start, end = 0, target.byte_size
    if selection is not None:
        if (selection["revision"], selection["content_sha256"]) != (
            target.revision,
            target.content_sha256,
        ):
            return replace(candidate, status="stale")
        if selection["range"]["type"] != "byte":
            return replace(candidate, status="no_match")
        start, end = selection["range"]["start"], selection["range"]["end"]
    if not 0 <= start < end <= target.byte_size:
        return replace(candidate, status="no_match")
    return replace(candidate, span=Span(target.object_key, start, end), handle=target)


def material_of(target: PointerTarget, span: Span, outcome: Any, max_tokens: int) -> Material:
    """
    함수 이름: material_of()
    기능: reader 결과를 Material로 바꾼다. 실제 구간이 없거나 요청 구간 밖이면 no_match다.
    인자: target -> 대상, span -> 요청 구간, outcome -> ReadOutcome/RuntimeReadOutcome,
        max_tokens -> 읽기 토큰 상한
    반환값: Material
    작성 날짜: 2026/11/10
    """
    got: ByteSpan | None = outcome.span
    if got is None or not (span.start == got.start and got.end <= span.end):
        raise ServiceError(ErrorCode.NOT_FOUND, "선택 범위를 읽을 수 없습니다.")
    ref: Wire = {"kind": target.kind, "pointer": target.pointer}
    ref["selection"] = selection_wire(target, got.start, got.end)
    return Material(
        content=outcome.content,
        token_count=outcome.token_count,
        count_mode=outcome.count_mode,
        span=Span(target.object_key, got.start, got.end),
        citation={"ref": ref},
        complete=got.end == span.end or _boundary_trim(span, got, outcome.token_count, max_tokens),
    )


def _boundary_trim(span: Span, got: ByteSpan, token_count: int, max_tokens: int) -> bool:
    """
    함수 이름: _boundary_trim()
    기능: 토큰 상한이 아니라 UTF-8 문자 경계 때문에 구간 끝 3바이트 이내에서 멈췄는지 판단한다.
        이 경우는 구간을 끝까지 읽은 것으로 본다(바이트 상한으로 자른 자동 후보의 partial_size).
    인자: span -> 요청 구간, got -> 실제 구간, token_count -> 실제 계수, max_tokens -> 상한
    반환값: 경계 때문이면 True
    작성 날짜: 2026/11/10
    """
    return token_count < max_tokens and 0 < span.end - got.end < 4


def byte_request(pointer: str, span: Span, max_tokens: int) -> ReadRequest:
    """
    함수 이름: byte_request()
    기능: 구간·바이트·토큰 상한이 있는 읽기 요청을 만든다.
    인자: pointer -> URI, span -> 구간, max_tokens -> 토큰 상한
    반환값: ReadRequest
    작성 날짜: 2026/11/10
    """
    size = min(span.end - span.start, MAX_FRAGMENT_READ_BYTES)
    selector = Selector(kind="byte", start=span.start, end=span.end)
    tokens = min(max_tokens, MAX_READ_TOKENS)
    return ReadRequest(pointer=pointer, selector=selector, max_bytes=size, max_tokens=tokens)


class SourceResolver:
    """
    클래스 이름: SourceResolver
    기능: workspace 범위의 Source 포인터 후보를 해석하고 4.6 SourceReader로 상한 안에서 읽는다.
    작성 날짜: 2026/11/10
    """

    def __init__(
        self, adapter: SourceAdapter, workspace_id: str, pdf: PdfResolver | None = None
    ) -> None:
        """
        함수 이름: __init__()
        기능: Source adapter와 호출 범위를 저장한다.
        인자: adapter -> SourceAdapter, workspace_id -> 인증된 범위, pdf -> PDF 페이지 resolver(없으면 PDF는 no_match)
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._adapter = adapter
        self._workspace_id = workspace_id
        self._pdf = pdf

    def inspect(self, candidate: Candidate) -> Candidate:
        """
        함수 이름: inspect()
        기능: 등록부에서 현재 revision과 원본 SHA-256을 확인하고 구간을 정한다.
        인자: candidate -> Source 후보
        반환값: 상태와 구간을 채운 후보
        작성 날짜: 2026/11/10
        """
        try:
            record = self._adapter.registry.resolve(
                self._workspace_id, candidate.ref["pointer"]
            ).record
        except ServiceError as error:
            return replace(candidate, status=status_of(error))
        if record.media_type == PDF_MEDIA:
            if self._pdf is None:
                return replace(candidate, status="no_match")
            return self._pdf.inspect(candidate, record)
        path = str(record.relative_path)
        target = PointerTarget(
            record.pointer, "source", record.revision, record.fingerprint,
            ("file", path, record.fingerprint), record.byte_size, record.pointer,
        )  # fmt: skip
        return resolve_span(candidate, target)

    def read(self, candidate: Candidate, span: Span, max_tokens: int) -> Material:
        """
        함수 이름: read()
        기능: 바이트 구간을 4.6 reader로 읽는다. 읽는 사이 원본이 바뀌면 SOURCE_CHANGED다.
        인자: candidate -> 후보, span -> 구간, max_tokens -> 토큰 상한
        반환값: Material
        작성 날짜: 2026/11/10
        """
        if isinstance(candidate.handle, PdfTarget) and self._pdf is not None:
            return self._pdf.read(candidate, span, max_tokens)
        target: PointerTarget = candidate.handle
        outcome = self._adapter.reader.read(
            self._workspace_id, byte_request(target.pointer, span, max_tokens)
        )
        if outcome.record.fingerprint != target.content_sha256:
            raise ServiceError(ErrorCode.SOURCE_CHANGED, "원문 조회 중 파일이 바뀌었습니다.")
        return material_of(target, span, outcome, max_tokens)


class RuntimeResolver:
    """
    클래스 이름: RuntimeResolver
    기능: workspace·session 범위의 Runtime 포인터 후보를 해석하고 4.3 RuntimeReader로 읽는다.
    작성 날짜: 2026/11/10
    """

    def __init__(
        self, store: RuntimeStore, reader: RuntimeReader, workspace_id: str, session_id: str
    ) -> None:
        """
        함수 이름: __init__()
        기능: 저장소·reader와 호출 범위를 저장한다.
        인자: store -> RuntimeStore, reader -> RuntimeReader, workspace_id/session_id -> 범위
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._store = store
        self._reader = reader
        self._scope = (workspace_id, session_id)

    def inspect(self, candidate: Candidate) -> Candidate:
        """
        함수 이름: inspect()
        기능: URI 범위 → 저장 행(만료·삭제) 순서로 확인하고 checksum으로 대상을 정한다.
        인자: candidate -> Runtime 후보
        반환값: 상태와 구간을 채운 후보
        작성 날짜: 2026/11/10
        """
        pointer = candidate.ref["pointer"]
        try:
            pointer_id = pointer_id_of(pointer, *self._scope)
            row = self._store.load(*self._scope, pointer_id)
        except ServiceError as error:
            return replace(candidate, status=status_of(error))
        except RuntimeStoreError as error:
            return replace(candidate, status=_STATUS.get(ErrorCode(error.code), "no_match"))  # type: ignore[arg-type]
        checksum = row["checksum"]
        target = PointerTarget(
            pointer, "runtime", 1, checksum, ("runtime", pointer_id, checksum),
            row["byte_size"], "runtime output",
        )  # fmt: skip
        return resolve_span(candidate, target)

    def read(self, candidate: Candidate, span: Span, max_tokens: int) -> Material:
        """
        함수 이름: read()
        기능: 저장된 출력의 바이트 구간을 checksum 검증 읽기로 가져온다.
        인자: candidate -> 후보, span -> 구간, max_tokens -> 토큰 상한
        반환값: Material
        작성 날짜: 2026/11/10
        """
        target: PointerTarget = candidate.handle
        try:
            outcome = self._reader.read(
                *self._scope, byte_request(target.pointer, span, max_tokens)
            )
        except RuntimeStoreError as error:
            raise ServiceError(ErrorCode(error.code), str(error)) from error
        if outcome.row["checksum"] != target.content_sha256:
            raise ServiceError(ErrorCode.SOURCE_CHANGED, "저장된 출력이 바뀌었습니다.")
        return material_of(target, span, outcome, max_tokens)
