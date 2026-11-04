"""Python ErrorCode·ERROR_RULES가 contracts/common/error-codes.json과 같은지 확인한다."""

import json

from securecode_context.common.errors import ERROR_RULES, ErrorCode
from support.helpers import CONTRACTS_ROOT


def test_error_rules_match_contract_table() -> None:
    """
    함수 이름: test_error_rules_match_contract_table()
    기능: 코드 목록·HTTP 상태·재시도 기본값이 계약 표와 완전히 같은지 검사한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    table = json.loads((CONTRACTS_ROOT / "common" / "error-codes.json").read_text("utf-8"))
    codes = table["codes"]
    assert sorted(codes) == sorted(code.value for code in ErrorCode)
    for code in ErrorCode:
        assert ERROR_RULES[code].http_status == codes[code.value]["http_status"], code
        assert ERROR_RULES[code].retryable == codes[code.value]["retryable"], code
