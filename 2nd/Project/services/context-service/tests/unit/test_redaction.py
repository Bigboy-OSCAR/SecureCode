"""tests/fixtures/redaction-cases.json 공용 벡터로 Python redaction을 검사한다(TS도 같은 파일 사용)."""

import logging

import pytest

from securecode_context.common.redaction import RedactingFilter, Redactor
from support.helpers import load_shared_vectors

VECTORS = load_shared_vectors("redaction-cases.json")


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda case: case["name"])
def test_redaction_vector(case: dict[str, object]) -> None:
    """
    함수 이름: test_redaction_vector()
    기능: 입력이 기대 문자열로 바뀌는지 확인한다.
    인자: case -> 공용 벡터 하나
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    redactor = Redactor(list(case["secrets"]), max_chars=VECTORS["max_chars"])  # type: ignore[call-overload]
    assert redactor.redact(str(case["input"])) == case["expected"]


def test_filter_redacts_formatted_arguments() -> None:
    """
    함수 이름: test_filter_redacts_formatted_arguments()
    기능: %s 인자로 들어온 비밀값도 최종 메시지에서 지워지는지 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "auth %s", ("Bearer abcdefghijkl",), None
    )
    RedactingFilter(Redactor()).filter(record)
    assert record.getMessage() == "auth Bearer [REDACTED]"
