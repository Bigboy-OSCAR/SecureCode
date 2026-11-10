"""내부 Runtime 계약형 경로(descriptor·read·search·list)와 오류 envelope가 4.2 계약을 지키는지 검사한다."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from support.helpers import TEST_TOKEN, ContractCheck, FixedTokenCounter

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
SCOPE = {"workspace_id": "ws_12345678", "session_id": "ses_12345678"}
LIST_ITEM = "pointers/lifecycle.schema.json#/definitions/PointerListItem"
LIST_RESULT = "pointers/lifecycle.schema.json#/definitions/PointerListResult"
READ = "pointers/read.schema.json#/definitions/PointerReadResult"
SEARCH = "pointers/search.schema.json#/definitions/PointerSearchResult"
ERROR = "common/api-error.schema.json#/definitions/ErrorResponse"
LOG = "# 빌드\n시작\n## 오류\nFAILED test_a 한글\nFAILED test_b\n# 끝\n"


@pytest.fixture
def client(service_settings: ServiceSettings) -> Iterator[TestClient]:
    """
    함수 이름: client()
    기능: 시험 계수기를 주입한 앱 client를 만든다.
    인자: service_settings -> 시험 설정
    반환값: TestClient
    작성 날짜: 2026/11/10
    """
    with TestClient(create_app(service_settings, token_counter=FixedTokenCounter())) as test:
        yield test


def _post(client: TestClient, route: str, **body: object) -> dict[str, object]:
    """
    함수 이름: _post()
    기능: 범위를 넣어 내부 Runtime 경로를 호출한다.
    인자: client -> 앱 client, route -> 경로 끝부분, body -> 나머지 본문
    반환값: 응답 JSON
    작성 날짜: 2026/11/10
    """
    response = client.post(f"/internal/v1/runtime/{route}", headers=AUTH, json={**SCOPE, **body})
    data: dict[str, object] = response.json()
    return data


def test_runtime_reads_match_contract(client: TestClient, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_runtime_reads_match_contract()
    기능: 저장 descriptor·line/section 읽기·cursor·검색·목록 응답이 계약을 지키는지 확인한다.
    인자: client -> 앱 client, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    stored = _post(client, "pointers", content=LOG, origin="run_command")
    assert contract_check(LIST_ITEM, stored["descriptor"]) == []
    pointer = stored["pointer_uri"]
    line = _post(
        client, "read", schema_version="1", pointer=pointer, selector={"type": "line", "start": 4}
    )
    assert line["content"] == "FAILED test_a 한글" and contract_check(READ, line) == []
    section = _post(
        client, "read", schema_version="1", pointer=pointer,
        selector={"type": "section", "section": "빌드"}, max_bytes=16,
    )  # fmt: skip
    assert section["truncated"] is True and contract_check(READ, section) == []
    following = _post(
        client, "read", schema_version="1", pointer=pointer,
        selector={"type": "section", "section": "빌드"}, max_bytes=16, cursor=section["next_cursor"],
    )  # fmt: skip
    assert contract_check(READ, following) == []
    found = _post(client, "search", schema_version="1", pointer=pointer, query="FAILED", limit=1)
    assert found["matches"][0]["line"] == 4 and contract_check(SEARCH, found) == []  # type: ignore[index]
    rest = _post(
        client,
        "search",
        schema_version="1",
        pointer=pointer,
        query="FAILED",
        cursor=found["next_cursor"],
    )
    assert [m["line"] for m in rest["matches"]] == [5]  # type: ignore[union-attr]
    listed = _post(client, "list", limit=10)
    assert contract_check(LIST_RESULT, listed) == []


def test_runtime_errors_use_envelope(client: TestClient, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_runtime_errors_use_envelope()
    기능: 다른 세션·삭제된 포인터·제한된 읽기 재저장이 계약 오류로 돌아오는지 확인한다.
    인자: client -> 앱 client, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    pointer = _post(client, "pointers", content="data")["pointer_uri"]
    other = client.post(
        "/internal/v1/runtime/read",
        headers=AUTH,
        json={**SCOPE, "session_id": "ses_87654321", "schema_version": "1", "pointer": pointer},
    ).json()
    assert other["error"]["code"] == "FORBIDDEN" and contract_check(ERROR, other) == []
    _post(client, "pointers/delete", pointer=pointer)
    deleted = _post(client, "read", schema_version="1", pointer=pointer)
    assert deleted["error"]["code"] == "NOT_FOUND"  # type: ignore[index]
    assert deleted["error"]["details"]["reason"] == "deleted"  # type: ignore[index]
    assert contract_check(ERROR, deleted) == []
    wrapped = _post(client, "pointers", content="x", origin="runtime_read")
    assert wrapped["error"]["code"] == "VALIDATION_FAILED"  # type: ignore[index]
    assert contract_check(ERROR, wrapped) == []


def _stream(client: TestClient, chunks: list[bytes], **headers: str) -> dict[str, object]:
    """
    함수 이름: _stream()
    기능: 청크 본문으로 스트리밍 저장 경로를 호출한다.
    인자: client -> 앱 client, chunks -> 보낼 청크, headers -> 추가·덮어쓸 헤더
    반환값: 응답 JSON
    작성 날짜: 2026/11/10
    """
    base = {
        **AUTH,
        "content-type": "application/octet-stream",
        "x-securecode-workspace-id": SCOPE["workspace_id"],
        "x-securecode-session-id": SCOPE["session_id"],
        "x-securecode-origin": "run_command",
    }
    response = client.post(
        "/internal/v1/runtime/stream", headers={**base, **headers}, content=iter(chunks)
    )
    data: dict[str, object] = response.json()
    return data


def test_stream_store_matches_contract(client: TestClient, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_stream_store_matches_contract()
    기능: 한글이 청크 경계에서 갈라져도 그대로 저장되고, 잘림 표시·오류가 계약대로인지 확인한다.
    인자: client -> 앱 client, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    text = "출력 줄 한글\n".encode() * 2000
    chunks = [text[index : index + 1001] for index in range(0, len(text), 1001)]
    stored = _stream(client, chunks, **{"x-securecode-truncated": "true"})
    descriptor = stored["descriptor"]
    assert contract_check(LIST_ITEM, descriptor) == []
    assert stored["byte_size"] == len(text)
    assert descriptor["provenance"]["truncated_before_storage"] is True  # type: ignore[index]
    line = _post(
        client, "read", schema_version="1", pointer=stored["pointer_uri"],
        selector={"type": "line", "start": 2000},
    )  # fmt: skip
    assert line["content"] == "출력 줄 한글"
    wrong_type = _stream(client, [b"x"], **{"content-type": "application/json"})
    bounded = _stream(client, [b"x"], **{"x-securecode-origin": "runtime_read"})
    broken = _stream(client, [b"ok \xff"])
    for body in (wrong_type, bounded, broken):
        assert body["error"]["code"] == "VALIDATION_FAILED"  # type: ignore[index]
        assert contract_check(ERROR, body) == []
    assert len(_post(client, "list", limit=100)["items"]) == 1  # type: ignore[arg-type]
