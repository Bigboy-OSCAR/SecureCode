"""contracts/fixtures 전체를 jsonschema로 검사한다. TS(Ajv) 결과와 같아야 한다."""

import json

import pytest

from support.helpers import CONTRACTS_ROOT, ContractCheck

FIXTURE_PATHS = sorted((CONTRACTS_ROOT / "fixtures").rglob("*.json"))


@pytest.mark.parametrize(
    ("name", "field", "limit"),
    [
        ("api/approval-korean-content.valid.json", "content", 16384),
        ("pointers/pointer-descriptor-source.valid.json", "preview", 512),
    ],
)
def test_utf8_boundaries(name: str, field: str, limit: int, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_utf8_boundaries()
    기능: 한글 입력의 바이트 경계와 잘못된 유니코드를 검사한다.
    인자: name, field -> 예시 파일과 필드, limit -> 바이트 상한, contract_check -> 계약 검증기
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    example = json.loads((CONTRACTS_ROOT / "fixtures" / name).read_text(encoding="utf-8"))
    at_limit = "한" * (limit // 3) + "a" * (limit % 3)
    for value, valid in [(at_limit, True), (at_limit + "a", False), ("\ud800", False)]:
        errors = contract_check(example["schema_ref"], {**example["data"], field: value})
        assert (not errors) == valid


def test_fixture_set_is_not_empty() -> None:
    """
    함수 이름: test_fixture_set_is_not_empty()
    기능: fixture 디렉토리를 찾지 못해 시험이 0건으로 통과하는 일을 막는다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    assert len(FIXTURE_PATHS) >= 50


@pytest.mark.parametrize(
    "fixture_path", FIXTURE_PATHS, ids=lambda path: path.relative_to(CONTRACTS_ROOT).as_posix()
)
def test_fixture_matches_expectation(fixture_path: object, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_fixture_matches_expectation()
    기능: fixture의 expect(valid/invalid)와 스키마 검사 결과가 같은지 확인한다.
    인자: fixture_path -> fixture 파일 경로
        contract_check -> 계약 검사 함수
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    document = json.loads(fixture_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    errors = contract_check(document["schema_ref"], document["data"])
    if document["expect"] == "valid":
        assert errors == []
    else:
        assert errors != []
