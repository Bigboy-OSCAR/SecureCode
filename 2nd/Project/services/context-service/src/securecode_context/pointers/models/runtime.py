"""Runtime Pointer 저장소의 요청·descriptor·결과와 오류 코드.

오류 code는 contracts/common/error-codes.json의 ErrorCode 값이다.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from securecode_context.pointers.runtime.media import supported_selectors

# Bounded-read tool outputs are already capped; storing them again would wrap a pointer in a pointer.
BOUNDED_READ_ORIGINS = frozenset(
    {"runtime_read", "runtime_search", "source_read", "source_search", "pdf_read"}
)


class RuntimeStoreError(Exception):
    """
    클래스 이름: RuntimeStoreError
    기능: Runtime 저장소 오류의 기반 클래스. code와 선택적 reason을 API 오류로 옮긴다.
    작성 날짜: 2026/11/10
    """

    code = "INTERNAL_ERROR"

    def __init__(self, message: str, reason: str | None = None) -> None:
        """
        함수 이름: __init__()
        기능: 사용자에게 보여도 되는 메시지와 details.reason을 보관한다.
        인자: message -> 메시지, reason -> 세부 사유
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        super().__init__(message)
        self.reason = reason


class PointerNotFound(RuntimeStoreError):  # noqa: N818
    """
    클래스 이름: PointerNotFound
    기능: 없거나 삭제·세션 정리된 포인터.
    작성 날짜: 2026/11/06
    """

    code = "NOT_FOUND"


class PointerExpired(RuntimeStoreError):  # noqa: N818
    """
    클래스 이름: PointerExpired
    기능: TTL이 지난 포인터. 다시 돌아오지 않는다.
    작성 날짜: 2026/11/06
    """

    code = "EXPIRED"


class ScopeForbidden(RuntimeStoreError):  # noqa: N818
    """
    클래스 이름: ScopeForbidden
    기능: 작업 공간·세션 범위가 맞지 않거나 경로로 쓸 수 없는 범위.
    작성 날짜: 2026/11/06
    """

    code = "FORBIDDEN"


class QuotaExceeded(RuntimeStoreError):  # noqa: N818
    """
    클래스 이름: QuotaExceeded
    기능: 객체·세션 용량 또는 디스크 공간 부족. 오래된 자료를 지워 자리를 만들지 않는다.
    작성 날짜: 2026/11/06
    """

    code = "QUOTA_EXCEEDED"


class InvalidSelector(RuntimeStoreError):  # noqa: N818
    """
    클래스 이름: InvalidSelector
    기능: 범위·상한·TTL 같은 요청 값이 잘못됨.
    작성 날짜: 2026/11/06
    """

    code = "INVALID_SELECTOR"


class NotStorable(RuntimeStoreError):  # noqa: N818
    """
    클래스 이름: NotStorable
    기능: 이미 제한된 읽기 결과처럼 다시 포인터로 감싸면 안 되는 출력.
    작성 날짜: 2026/11/10
    """

    code = "VALIDATION_FAILED"


class BlobCorrupt(RuntimeStoreError):  # noqa: N818
    """
    클래스 이름: BlobCorrupt
    기능: 저장한 blob이 checksum과 다르다. 원문 대신 오류를 낸다.
    작성 날짜: 2026/11/10
    """

    code = "INTERNAL_ERROR"


class StorageUnavailable(RuntimeStoreError):  # noqa: N818
    """
    클래스 이름: StorageUnavailable
    기능: 공간 부족 이외의 디스크 오류. 재시도할 수 있다.
    작성 날짜: 2026/11/10
    """

    code = "SERVICE_UNAVAILABLE"


@dataclass(frozen=True)
class RuntimePut:
    """
    클래스 이름: RuntimePut
    기능: 계약 RuntimePutRequest의 내부 형태(본문은 bytes).
    작성 날짜: 2026/11/10
    """

    workspace_id: str
    session_id: str
    media_type: str
    content: bytes
    ttl_seconds: int = 86_400
    origin: str = "tool_output"
    truncated_before_storage: bool = False


@dataclass(frozen=True)
class RuntimeDescriptor:
    """
    클래스 이름: RuntimeDescriptor
    기능: 저장된 Runtime 객체의 메타데이터와 512바이트 이하 미리보기.
    작성 날짜: 2026/11/10
    """

    pointer: str
    workspace_id: str
    session_id: str
    media_type: str
    byte_size: int
    checksum: str
    created_at: datetime
    expires_at: datetime
    preview: str
    origin: str = "tool_output"
    truncated_before_storage: bool = False

    def to_dict(self) -> dict[str, Any]:
        """
        함수 이름: to_dict()
        기능: 계약 PointerListItem(kind=runtime) JSON 사전으로 바꾼다.
        인자: 없음
        반환값: 계약 JSON 사전
        작성 날짜: 2026/11/10
        """
        provenance: dict[str, Any] = {
            "created_at": _timestamp(self.created_at),
            "origin": self.origin,
        }
        if self.truncated_before_storage:
            provenance["truncated_before_storage"] = True
        return {
            "schema_version": "1",
            "pointer": self.pointer,
            "kind": "runtime",
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "revision": 1,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "preview": self.preview,
            "available_operations": ["read", "search"],
            "provenance": provenance,
            "expires_at": _timestamp(self.expires_at),
            "display_name": "output-" + self.pointer.rsplit("/", 1)[-1][:8],
            "supported_selectors": supported_selectors(self.media_type, self.byte_size),
        }


def _timestamp(value: datetime) -> str:
    """
    함수 이름: _timestamp()
    기능: UTC RFC 3339 문자열을 만든다.
    인자: value -> 시각
    반환값: Z로 끝나는 문자열
    작성 날짜: 2026/11/10
    """
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")
