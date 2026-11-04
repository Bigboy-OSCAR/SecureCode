"""시험 공용 도구: 작업 루트 경로, 계약 스키마 registry, 공용 벡터, 고정 계수기."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import CounterStatus, CountMode, TokenCount
from securecode_context.common.tokens.counter import measure_countable_text

WORK_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_ROOT = WORK_ROOT / "contracts"
CONTRACT_BASE_URI = "https://contracts.securecode.invalid/"
TEST_TOKEN = "t" * 40

ContractCheck = Callable[[str, Any], list[str]]


def build_contract_registry() -> Registry[Any]:
    """
    함수 이름: build_contract_registry()
    기능: contracts/*/*.schema.json을 TS 검증기와 같은 base URI로 등록한다.
    인자: 없음
    반환값: referencing Registry
    작성 날짜: 2026/11/04
    """
    resources = []
    for schema_path in sorted(CONTRACTS_ROOT.glob("*/*.schema.json")):
        relative = schema_path.relative_to(CONTRACTS_ROOT).as_posix()
        contents = json.loads(schema_path.read_text(encoding="utf-8"))
        resources.append((CONTRACT_BASE_URI + relative, Resource.from_contents(contents, DRAFT7)))
    return Registry().with_resources(resources)


class FixedTokenCounter:
    """
    클래스 이름: FixedTokenCounter
    기능: 시험용 계수기. UTF-8 바이트 수를 그대로 토큰 수로 돌려주며 provider 계수인 척하지 않도록
        count_mode를 provider_estimate로만 표시한다(계약 형식 시험 전용).
    작성 날짜: 2026/11/04
    """

    def count(self, text: str, model_id: str | None = None) -> TokenCount:
        """
        함수 이름: count()
        기능: 입력 검사를 실제 계수기와 똑같이 적용한 뒤 고정 규칙으로 계수한다.
        인자: text -> 본문
            model_id -> 설정 모델 이외는 거절
        반환값: TokenCount
        작성 날짜: 2026/11/04
        """
        text_bytes = measure_countable_text(text)
        if model_id not in (None, "claude-sonnet-5-5"):
            raise ServiceError(ErrorCode.TOKENIZER_UNAVAILABLE, "unsupported model")
        return TokenCount(
            token_count=text_bytes,
            count_mode=CountMode.PROVIDER_ESTIMATE,
            provider_id="anthropic",
            model_id="claude-sonnet-5-5",
            method="anthropic_count_tokens",
            framing="single_user_message",
            text_bytes=text_bytes,
        )

    def describe(self) -> CounterStatus:
        """
        함수 이름: describe()
        기능: 설정된 상태를 돌려준다.
        인자: 없음
        반환값: CounterStatus
        작성 날짜: 2026/11/04
        """
        return CounterStatus(configured=True)


def load_shared_vectors(file_name: str) -> dict[str, Any]:
    """
    함수 이름: load_shared_vectors()
    기능: 작업 루트 tests/fixtures의 TS/Python 공용 벡터 파일을 읽는다.
    인자: file_name -> 파일 이름
    반환값: JSON 사전
    작성 날짜: 2026/11/04
    """
    data: dict[str, Any] = json.loads(
        (WORK_ROOT / "tests" / "fixtures" / file_name).read_text(encoding="utf-8")
    )
    return data
