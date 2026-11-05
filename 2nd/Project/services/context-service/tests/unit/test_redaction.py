"""tests/fixtures/redaction-cases.json 공용 벡터로 Python redaction을 검사한다(TS도 같은 파일 사용)."""

import logging
import sys

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


def test_traceback_and_stack_are_redacted() -> None:
    """
    함수 이름: test_traceback_and_stack_are_redacted()
    기능: handler가 나중에 붙이는 traceback, stack_info로 비밀이 유출되지 않는지 검사한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    secret = "registered" + "_sample_value"
    try:
        raise ValueError(secret + " private-source-marker")
    except ValueError:
        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1, "failure", (), sys.exc_info()
        )
    record.stack_info = "stack " + secret
    RedactingFilter(Redactor([secret])).filter(record)
    output = logging.Formatter().format(record)
    assert secret not in output and "private-source-marker" not in output
    assert "ValueError" in output
