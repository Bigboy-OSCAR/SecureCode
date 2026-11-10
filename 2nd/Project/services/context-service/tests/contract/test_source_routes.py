"""내부 Source 경로(/internal/v1/source/*)가 4.2 계약 스키마와 오류 envelope를 지키는지 검사한다."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from support.helpers import TEST_TOKEN, ContractCheck
from support.source_fixtures import WS_A, WS_B, FixedRoots

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
LIFECYCLE = "pointers/lifecycle.schema.json#/definitions/"
ERROR_REF = "common/api-error.schema.json#/definitions/ErrorResponse"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """
    함수 이름: workspace()
    기능: 등록할 파일이 있는 workspace root를 만든다.
    인자: tmp_path -> 임시 폴더
    반환값: root 경로
    작성 날짜: 2026/11/10
    """
    root = tmp_path / "project"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "설계.md").write_text("# 설계\n", encoding="utf-8")
    (root / "docs" / "blob.bin").write_bytes(b"\x00")
    return root


@pytest.fixture
def client(service_settings: ServiceSettings, workspace: Path) -> Iterator[TestClient]:
    """
    함수 이름: client()
    기능: 시험용 root 포트를 주입한 앱 client를 만든다.
    인자: service_settings -> 시험 설정, workspace -> root
    반환값: TestClient
    작성 날짜: 2026/11/10
    """
    roots = FixedRoots({WS_A: workspace, WS_B: workspace})
    with TestClient(create_app(service_settings, workspace_roots=roots)) as test_client:
        yield test_client


def _register(client: TestClient, kind: str, path: str) -> dict[str, object]:
    """
    함수 이름: _register()
    기능: workspace 대상 등록 요청을 보낸다.
    인자: client -> 앱 client, kind -> file/directory, path -> 상대 경로
    반환값: 응답 JSON
    작성 날짜: 2026/11/10
    """
    body = {
        "schema_version": "1",
        "idempotency_key": "register-0001",
        "operation": "register",
        "workspace_id": WS_A,
        "target": {"location": "workspace", "kind": kind, "path": path},
    }
    response = client.post("/internal/v1/source/register", json=body, headers=AUTH)
    assert response.status_code == 200, response.text
    data: dict[str, object] = response.json()
    return data


def test_lifecycle_responses_match_contract(
    client: TestClient, contract_check: ContractCheck, workspace: Path
) -> None:
    """
    함수 이름: test_lifecycle_responses_match_contract()
    기능: register·stat·list·unregister 응답이 계약을 지키고 서버 절대 경로를 노출하지 않는지 확인한다.
    인자: client -> 앱 client, contract_check -> 계약 검사, workspace -> root
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    registered = _register(client, "file", "docs/설계.md")
    assert contract_check(LIFECYCLE + "SourceMutationResult", registered) == []
    items = registered["items"]
    assert isinstance(items, list)
    pointer = items[0]["pointer"]
    stat = client.post(
        "/internal/v1/source/stat", json={"workspace_id": WS_A, "pointer": pointer}, headers=AUTH
    )
    assert contract_check(LIFECYCLE + "PointerListItem", stat.json()) == []
    listed = client.post("/internal/v1/source/list", json={"workspace_id": WS_A}, headers=AUTH)
    assert contract_check(LIFECYCLE + "PointerListResult", listed.json()) == []
    delete = {
        "schema_version": "1",
        "idempotency_key": "delete-0001",
        "kind": "source",
        "workspace_id": WS_A,
        "pointer": pointer,
    }
    removed = client.post("/internal/v1/source/unregister", json=delete, headers=AUTH)
    assert contract_check(LIFECYCLE + "PointerDeleteResult", removed.json()) == []
    # The pytest temp folder name is unique, so it only appears if an absolute path leaks.
    for body in (registered, stat.json(), listed.json(), removed.json()):
        assert workspace.parent.name not in json.dumps(body, ensure_ascii=False)
    assert (workspace / "docs" / "설계.md").exists()


def test_directory_partial_and_refresh_match_contract(
    client: TestClient, contract_check: ContractCheck, workspace: Path
) -> None:
    """
    함수 이름: test_directory_partial_and_refresh_match_contract()
    기능: 일부 제외 디렉터리 등록과 변경 후 refresh 응답이 계약을 지키는지 확인한다.
    인자: client -> 앱 client, contract_check -> 계약 검사, workspace -> root
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    result = _register(client, "directory", "docs")
    assert result["status"] == "partial"
    assert contract_check(LIFECYCLE + "SourceMutationResult", result) == []
    items = result["items"]
    assert isinstance(items, list)
    (workspace / "docs" / "설계.md").write_text("# 바뀐 설계\n", encoding="utf-8")
    refresh = {
        "schema_version": "1",
        "idempotency_key": "refresh-0001",
        "operation": "refresh",
        "workspace_id": WS_A,
        "pointer": items[0]["pointer"],
    }
    refreshed = client.post("/internal/v1/source/refresh", json=refresh, headers=AUTH).json()
    assert contract_check(LIFECYCLE + "SourceMutationResult", refreshed) == []
    assert refreshed["items"][0]["revision"] == 2


def test_errors_use_contract_envelope(client: TestClient, contract_check: ContractCheck) -> None:
    """
    함수 이름: test_errors_use_contract_envelope()
    기능: 경로 이탈·다른 workspace·잘못된 포인터·세션 필드가 계약 오류로 돌아오는지 확인한다.
    인자: client -> 앱 client, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    escape = {
        "schema_version": "1",
        "idempotency_key": "register-0002",
        "operation": "register",
        "workspace_id": WS_A,
        "target": {"location": "workspace", "kind": "file", "path": "../secret.txt"},
    }
    response = client.post("/internal/v1/source/register", json=escape, headers=AUTH)
    assert response.status_code == 403
    assert contract_check(ERROR_REF, response.json()) == []
    pointer = _register(client, "file", "docs/설계.md")["items"][0]["pointer"]  # type: ignore[index]
    foreign = client.post(
        "/internal/v1/source/stat", json={"workspace_id": WS_B, "pointer": pointer}, headers=AUTH
    )
    assert foreign.status_code == 403
    malformed = client.post(
        "/internal/v1/source/stat",
        json={"workspace_id": WS_A, "pointer": "securecode://source/x"},
        headers=AUTH,
    )
    assert malformed.json()["error"]["code"] == "INVALID_POINTER"
    with_session = {
        "schema_version": "1",
        "idempotency_key": "delete-0002",
        "kind": "source",
        "workspace_id": WS_A,
        "session_id": "ses_00000001",
        "pointer": pointer,
    }
    rejected = client.post("/internal/v1/source/unregister", json=with_session, headers=AUTH)
    assert rejected.json()["error"]["code"] == "VALIDATION_FAILED"
    unauthenticated = client.post("/internal/v1/source/list", json={"workspace_id": WS_A})
    assert unauthenticated.status_code == 401


def test_unregistered_workspace_fails_closed(
    service_settings: ServiceSettings, contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_unregistered_workspace_fails_closed()
    기능: 기본 앱은 host가 /workspaces/register로 등록하지 않은 workspace의 경로를 추측하지 않고 NOT_FOUND다.
    인자: service_settings -> 시험 설정, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    with TestClient(create_app(service_settings)) as client:
        body = {
            "schema_version": "1",
            "idempotency_key": "register-0003",
            "operation": "register",
            "workspace_id": WS_A,
            "target": {"location": "workspace", "kind": "file", "path": "a.txt"},
        }
        response = client.post("/internal/v1/source/register", json=body, headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["details"]["reason"] == "workspace_unknown"
    assert contract_check(ERROR_REF, response.json()) == []
