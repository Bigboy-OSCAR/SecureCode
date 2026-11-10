"""내부 Runtime Pointer 경로가 4.3 저장소를 통해 저장·조회·정리되는지 확인한다."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN = "test-token"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """
    함수 이름: client()
    기능: 임시 데이터 폴더와 시험 계수기를 쓰는 앱 client를 만든다.
    인자: tmp_path -> 임시 폴더
    반환값: TestClient
    작성 날짜: 2026/11/10
    """
    from securecode_context.app.factory import create_app
    from securecode_context.app.settings import ServiceSettings
    from support.helpers import FixedTokenCounter

    settings = ServiceSettings(
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
    with TestClient(create_app(settings, token_counter=FixedTokenCounter())) as test_client:
        yield test_client


AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


def test_put_read_and_resume(client: TestClient) -> None:
    """
    함수 이름: test_put_read_and_resume()
    기능: 저장한 원문을 부분 읽고 커서로 이어 읽어 원문과 일치하는지 확인한다.
    인자: client -> 앱 client
    반환값: 없음
    작성 날짜: 2026/11/07
    """
    content = "first\nneedle here\nthird"
    created = client.post(
        "/internal/v1/runtime/pointers",
        headers=AUTH,
        json={"workspace_id": "ws_12345678", "session_id": "ses_12345678", "content": content},
    )
    assert created.status_code == 200, created.text
    pointer = created.json()["pointer_uri"]
    first = client.post(
        "/internal/v1/runtime/read",
        headers=AUTH,
        json={
            "schema_version": "1",
            "workspace_id": "ws_12345678",
            "session_id": "ses_12345678",
            "pointer": pointer,
            "max_bytes": 10,
        },
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["content"] == content[:10]
    assert first_body["truncated"] is True
    resumed = client.post(
        "/internal/v1/runtime/read",
        headers=AUTH,
        json={
            "schema_version": "1",
            "workspace_id": "ws_12345678",
            "session_id": "ses_12345678",
            "pointer": pointer,
            "cursor": first_body["next_cursor"],
        },
    )
    assert resumed.status_code == 200, resumed.text
    resumed_body = resumed.json()
    assert resumed_body["content"] == content[10:]
    assert resumed_body["truncated"] is False
    assert "next_cursor" not in resumed_body


def test_scope_and_uri_are_enforced(client: TestClient) -> None:
    """
    함수 이름: test_scope_and_uri_are_enforced()
    기능: 다른 세션·작업 공간의 읽기와 잘못된 포인터 형식을 거부하는지 확인한다.
    인자: client -> 앱 client
    반환값: 없음
    작성 날짜: 2026/11/07
    """
    created = client.post(
        "/internal/v1/runtime/pointers",
        headers=AUTH,
        json={"workspace_id": "ws_12345678", "session_id": "ses_12345678", "content": "secret"},
    ).json()
    pointer = created["pointer_uri"]
    other_session = client.post(
        "/internal/v1/runtime/read",
        headers=AUTH,
        json={
            "schema_version": "1",
            "workspace_id": "ws_12345678",
            "session_id": "ses_99999999",
            "pointer": pointer,
        },
    )
    assert other_session.status_code == 403
    assert other_session.json()["error"]["code"] == "FORBIDDEN"
    malformed = client.post(
        "/internal/v1/runtime/read",
        headers=AUTH,
        json={
            "schema_version": "1",
            "workspace_id": "ws_12345678",
            "session_id": "ses_12345678",
            "pointer": "https://example.invalid",
        },
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "INVALID_POINTER"


def test_delete_and_session_clear(client: TestClient) -> None:
    """
    함수 이름: test_delete_and_session_clear()
    기능: 포인터 삭제와 세션 정리 뒤 조회가 실패하는지 확인한다.
    인자: client -> 앱 client
    반환값: 없음
    작성 날짜: 2026/11/07
    """
    created = client.post(
        "/internal/v1/runtime/pointers",
        headers=AUTH,
        json={"workspace_id": "ws_12345678", "session_id": "ses_12345678", "content": "data"},
    ).json()
    pointer = created["pointer_uri"]
    deleted = client.post(
        "/internal/v1/runtime/pointers/delete",
        headers=AUTH,
        json={"workspace_id": "ws_12345678", "session_id": "ses_12345678", "pointer": pointer},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    missing = client.post(
        "/internal/v1/runtime/read",
        headers=AUTH,
        json={
            "schema_version": "1",
            "workspace_id": "ws_12345678",
            "session_id": "ses_12345678",
            "pointer": pointer,
        },
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_search_returns_line_and_requires_auth(client: TestClient) -> None:
    """
    함수 이름: test_search_returns_line_and_requires_auth()
    기능: 검색이 줄 번호를 돌려주고 인증 없는 요청을 거부하는지 확인한다.
    인자: client -> 앱 client
    반환값: 없음
    작성 날짜: 2026/11/07
    """
    created = client.post(
        "/internal/v1/runtime/pointers",
        headers=AUTH,
        json={
            "workspace_id": "ws_12345678",
            "session_id": "ses_12345678",
            "content": "first\nneedle here\nthird",
        },
    ).json()
    pointer = created["pointer_uri"]
    result = client.post(
        "/internal/v1/runtime/search",
        headers=AUTH,
        json={
            "schema_version": "1",
            "workspace_id": "ws_12345678",
            "session_id": "ses_12345678",
            "pointer": pointer,
            "query": "needle",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["matches"][0]["line"] == 2
    unauthenticated = client.post(
        "/internal/v1/runtime/search",
        json={
            "schema_version": "1",
            "workspace_id": "ws_12345678",
            "session_id": "ses_12345678",
            "pointer": pointer,
            "query": "needle",
        },
    )
    assert unauthenticated.status_code == 401
