"""공용 pytest fixture: 계약 스키마 검사 함수, 시험용 서비스 설정."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator, ValidationError, validators

from securecode_context.app.settings import ServiceSettings
from support.helpers import CONTRACT_BASE_URI, TEST_TOKEN, ContractCheck, build_contract_registry


def _max_utf8_bytes(
    validator: object, limit: int, value: object, schema: object
) -> Iterator[ValidationError]:
    """
    함수 이름: _max_utf8_bytes()
    기능: 문자 수와 별도로 UTF-8 인코딩과 바이트 한도를 검증한다.
    인자: validator, schema -> 검증기 문맥, limit -> 바이트 상한, value -> 검사할 값
    반환값: 한도를 넘거나 UTF-8로 인코딩할 수 없을 때 발생하는 계약 오류
    작성 날짜: 2026/11/05
    """
    if isinstance(value, str):
        try:
            length = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            yield ValidationError("value must be valid UTF-8")
            return
        if length > limit:
            yield ValidationError(f"value exceeds {limit} UTF-8 bytes")


ContractValidator = validators.extend(Draft7Validator, {"maxUtf8Bytes": _max_utf8_bytes})


@pytest.fixture(scope="session")
def contract_check() -> ContractCheck:
    """
    함수 이름: contract_check()
    기능: (schema_ref, data)를 검사해 오류 메시지 목록을 돌려주는 함수를 만든다.
    인자: 없음
    반환값: 빈 목록이면 유효한 검사 함수
    작성 날짜: 2026/11/04
    """
    registry = build_contract_registry()

    def check(schema_ref: str, data: Any) -> list[str]:
        """
        함수 이름: check()
        기능: data를 schema_ref 정의로 검사한다.
        인자: schema_ref -> "api/run.schema.json#/definitions/RunSnapshot" 형식
            data -> 검사할 JSON 값
        반환값: 오류 메시지 목록
        작성 날짜: 2026/11/04
        """
        validator = ContractValidator(
            {"$ref": CONTRACT_BASE_URI + schema_ref},
            registry=registry,
            format_checker=Draft7Validator.FORMAT_CHECKER,
        )
        return [error.message for error in validator.iter_errors(data)]

    return check


@pytest.fixture
def service_settings(tmp_path: Path) -> ServiceSettings:
    """
    함수 이름: service_settings()
    기능: 임시 데이터 디렉토리와 시험 토큰을 쓰는 설정을 만든다.
    인자: tmp_path -> pytest 임시 경로
    반환값: ServiceSettings
    작성 날짜: 2026/11/04
    """
    return ServiceSettings(
        host="127.0.0.1",
        port=8788,
        internal_token=TEST_TOKEN,
        data_dir=tmp_path / "data",
        provider_id="anthropic",
        model_id="claude-sonnet-5-5",
        api_key=None,
        provider_base_url=None,
        token_count_timeout_seconds=1.0,
        log_level="info",
    )
