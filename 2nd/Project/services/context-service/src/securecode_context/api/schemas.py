"""기존 런타임 포인터 경로의 요청·응답 모델."""

from pydantic import BaseModel, Field, field_validator

from securecode_context.pointers.limits import MAX_READ_BYTES, MAX_TTL_SECONDS


class RuntimePointerCreate(BaseModel):
    """클래스 이름: RuntimePointerCreate
    기능: 세션 범위, 원문과 선택한 TTL을 검증한다.
    작성 날짜: 2026/11/05
    """

    workspace_id: str = Field(pattern=r"^ws_[A-Za-z0-9-]{8,64}$")
    session_id: str = Field(pattern=r"^ses_[A-Za-z0-9-]{8,64}$")
    content: str = Field(max_length=32 * 1024 * 1024)
    ttl_seconds: int | None = Field(default=None, ge=0, le=MAX_TTL_SECONDS)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """함수 이름: validate_content()
        기능: UTF-8 변환 후 단일 원문의 최대 바이트 크기를 확인한다.
        인자: value -> 요청 본문
        반환값: 유효한 문자열
        작성 날짜: 2026/11/05
        """
        if len(value.encode()) > 32 * 1024 * 1024:
            raise ValueError("runtime content exceeds 32 MiB")
        return value


class RuntimePointerCreated(BaseModel):
    """클래스 이름: RuntimePointerCreated
    기능: 저장된 ID, URI와 원문 바이트 수를 전달한다.
    작성 날짜: 2026/11/05
    """

    pointer_id: str
    pointer_uri: str
    byte_size: int


class RuntimePointerRead(BaseModel):
    """클래스 이름: RuntimePointerRead
    기능: 세션 범위와 허용된 바이트 위치·최대 읽기 크기를 검증한다.
    작성 날짜: 2026/11/05
    """

    pointer_id: str = Field(min_length=1, max_length=128)
    workspace_id: str
    session_id: str
    cursor: int = Field(default=0, ge=0, lt=2**63 - 1)
    max_bytes: int = Field(default=MAX_READ_BYTES, ge=1, le=MAX_READ_BYTES)


class RuntimePointerReadResult(BaseModel):
    """클래스 이름: RuntimePointerReadResult
    기능: 범위 원문과 후속 읽기에 사용할 바이트 커서를 전달한다.
    작성 날짜: 2026/11/05
    """

    content: str
    next_cursor: int | None
    truncated: bool
    byte_size: int
