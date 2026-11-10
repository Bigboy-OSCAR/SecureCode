"""내부 Source 읽기·검색 경로가 PointerReadResult·PointerSearchResult·ErrorResponse 계약을 지키는지 검사한다."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from support.helpers import TEST_TOKEN, ContractCheck, FixedTokenCounter
from support.source_fixtures import WS_A, FixedRoots

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
READ_REF = "pointers/read.schema.json#/definitions/PointerReadResult"
SEARCH_REF = "pointers/search.schema.json#/definitions/PointerSearchResult"
ERROR_REF = "common/api-error.schema.json#/definitions/ErrorResponse"
TEXT = "# 개요\r\n한글 본문 needle\r\n## 세부\r\n둘째 needle\r\n"
TEST_TEXT_BYTES = TEXT.encode("utf-8")


@pytest.fixture
def client(service_settings: ServiceSettings, tmp_path: Path) -> Iterator[TestClient]:
    """
    함수 이름: client()
    기능: 시험 root 포트와 시험 계수기를 주입한 앱 client를 만든다.
    인자: service_settings -> 시험 설정, tmp_path -> 임시 폴더
    반환값: TestClient
    작성 날짜: 2026/11/10
    """
    root = tmp_path / "project"
    root.mkdir()
    (root / "guide.md").write_bytes(TEST_TEXT_BYTES)
    app = create_app(
        service_settings,
        token_counter=FixedTokenCounter(),
        workspace_roots=FixedRoots({WS_A: root}),
    )
    with TestClient(app) as test_client:
        yield test_client


def _pointer(client: TestClient) -> str:
    """
    함수 이름: _pointer()
    기능: guide.md를 등록하고 포인터를 돌려준다.
    인자: client -> 앱 client
    반환값: Source Pointer URI
    작성 날짜: 2026/11/10
    """
    body = {
        "schema_version": "1",
        "idempotency_key": "register-0001",
        "operation": "register",
        "workspace_id": WS_A,
        "target": {"location": "workspace", "kind": "file", "path": "guide.md"},
    }
    response = client.post("/internal/v1/source/register", json=body, headers=AUTH)
    return str(response.json()["items"][0]["pointer"])


def _post(client: TestClient, route: str, **body: object) -> dict[str, object]:
    """
    함수 이름: _post()
    기능: workspace와 schema_version을 넣어 요청한다.
    인자: client -> 앱 client, route -> read/search, body -> 나머지 본문
    반환값: 응답 JSON
    작성 날짜: 2026/11/10
    """
    payload = {"schema_version": "1", "workspace_id": WS_A, **body}
    data: dict[str, object] = client.post(
        f"/internal/v1/source/{route}", json=payload, headers=AUTH
    ).json()
    return data


def test_read_results_match_contract(client: TestClient, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_read_results_match_contract()
    기능: line·section·cursor 읽기 응답이 계약을 지키고 selection이 원본 구간을 가리키는지 확인한다.
    인자: client -> 앱 client, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = _pointer(client)
    line = _post(client, "read", pointer=pointer, selector={"type": "line", "start": 2})
    assert contract_check(READ_REF, line) == []
    selection = line["provenance"]["selection"]  # type: ignore[index]
    start, end = selection["range"]["start"], selection["range"]["end"]
    assert TEST_TEXT_BYTES[start:end].decode() == line["content"] == "한글 본문 needle"
    section = _post(
        client, "read", pointer=pointer, selector={"type": "section", "section": "개요"}
    )
    assert contract_check(READ_REF, section) == []
    first = _post(client, "read", pointer=pointer, max_bytes=8)
    assert first["truncated"] is True and contract_check(READ_REF, first) == []
    following = _post(client, "read", pointer=pointer, max_bytes=8, cursor=first["next_cursor"])
    assert contract_check(READ_REF, following) == []


def test_search_results_match_contract(client: TestClient, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_search_results_match_contract()
    기능: 일치·무일치·cursor 검색 응답이 계약을 지키는지 확인한다.
    인자: client -> 앱 client, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = _pointer(client)
    found = _post(client, "search", pointer=pointer, query="needle", limit=1)
    assert contract_check(SEARCH_REF, found) == []
    assert found["truncated"] is True
    rest = _post(client, "search", pointer=pointer, query="needle", cursor=found["next_cursor"])
    assert contract_check(SEARCH_REF, rest) == []
    assert [match["line"] for match in rest["matches"]] == [4]  # type: ignore[union-attr]
    none = _post(client, "search", pointer=pointer, query="없는말")
    assert none["matches"] == [] and contract_check(SEARCH_REF, none) == []


def test_read_errors_use_envelope(client: TestClient, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_read_errors_use_envelope()
    기능: 잘못된 범위·selector 형식·변조 cursor가 계약 오류 envelope로 돌아오는지 확인한다.
    인자: client -> 앱 client, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = _pointer(client)
    cases = [
        ({"selector": {"type": "line", "start": 3, "end": 1}}, "INVALID_SELECTOR"),
        ({"selector": {"type": "line", "section": "x"}}, "VALIDATION_FAILED"),
        ({"selector": {"type": "json_path", "path": "/a"}}, "INVALID_SELECTOR"),
        ({"cursor": "tampered"}, "INVALID_POINTER"),
        ({"max_bytes": 20000}, "VALIDATION_FAILED"),
    ]
    for extra, code in cases:
        body = _post(client, "read", pointer=pointer, **extra)
        assert body["error"]["code"] == code, extra  # type: ignore[index]
        assert contract_check(ERROR_REF, body) == []
