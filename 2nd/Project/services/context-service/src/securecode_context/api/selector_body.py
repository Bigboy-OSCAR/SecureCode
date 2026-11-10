"""계약 PointerSelector 요청 본문과 내부 Selector 변환(Source·Runtime 읽기 경로 공용)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.text.models import Selector

_JSON_POINTER = r"^(?:/(?:[^~/\x00-\x1f\x7f]|~[01])*)+$"
_RANGE = frozenset({"start", "end"})
# Selector type -> (fields it may carry, field it must carry).
_SELECTOR_FIELDS: dict[str, tuple[frozenset[str], str]] = {
    "line": (_RANGE, "start"),
    "byte": (_RANGE, "start"),
    "pdf_page": (_RANGE, "start"),
    "section": (frozenset({"section"}), "section"),
    "json_path": (frozenset({"path"}), "path"),
}


class SelectorBody(BaseModel):
    """
    클래스 이름: SelectorBody
    기능: 계약 PointerSelector. 종류별 필수 필드는 _selector()가 확인한다.
    작성 날짜: 2026/11/10
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["line", "byte", "section", "json_path", "pdf_page"]
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    section: str | None = Field(default=None, min_length=1, max_length=256)
    path: str | None = Field(default=None, min_length=1, max_length=512, pattern=_JSON_POINTER)


def to_selector(body: SelectorBody | None) -> Selector | None:
    """
    함수 이름: to_selector()
    기능: 종류에 맞는 필드만 쓴 selector인지 확인하고 내부 값으로 바꾼다.
    인자: body -> 요청 selector
    반환값: Selector 또는 None
    작성 날짜: 2026/11/10
    """
    if body is None:
        return None
    allowed, required = _SELECTOR_FIELDS[body.type]
    present = {
        name for name in ("start", "end", "section", "path") if getattr(body, name) is not None
    }
    if not present <= allowed or required not in present:
        raise ServiceError(
            ErrorCode.VALIDATION_FAILED,
            "selector 형식이 올바르지 않습니다.",
            {"reason": "selector_shape"},
        )
    if body.type in ("line", "pdf_page") and (body.start or 0) < 1:
        raise ServiceError(
            ErrorCode.INVALID_SELECTOR,
            "줄·페이지는 1부터 시작합니다.",
            {"reason": "start_below_one"},
        )
    return Selector(body.type, body.start, body.end, body.section, body.path)
