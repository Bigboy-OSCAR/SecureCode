"""기존 포인터 ASGI 경로의 인증·파일 위치·세션 격리 회귀 시험."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from securecode_context.api.main import app
from securecode_context.app.settings import SettingsError
from securecode_context.pointers.runtime.sqlite_store import SQLiteRuntimeStore


def test_legacy_app_requires_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """함수 이름: test_legacy_app_requires_configuration()
    기능: 인증 토큰 미설정 시 원문 저장소를 만들기 전에 기동을 중단하는지 확인한다.
    인자: monkeypatch -> 환경변수 교체, tmp_path -> 임시 경로
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    monkeypatch.delenv("SECURECODE_INTERNAL_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SECURECODE_DATA_DIR", str(tmp_path / "data"))
    with pytest.raises(SettingsError), TestClient(app):
        pass
    assert not (tmp_path / "runtime_pointers.db").exists()
    assert not (tmp_path / "data").exists()


def test_authenticated_legacy_routes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """함수 이름: test_authenticated_legacy_routes()
    기능: 실제 레거시 HTTP 경로에서 토큰·Origin·TTL·범위·UTF-8 경계를 검증한다.
    인자: monkeypatch -> 환경변수 교체, tmp_path -> 임시 경로
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    token = "test-token" * 4
    monkeypatch.setenv("SECURECODE_INTERNAL_TOKEN", token)
    monkeypatch.setenv("SECURECODE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)
    base = "/api/v1/pointers/runtime"
    scope = {"workspace_id": "ws_12345678", "session_id": "ses_12345678"}
    body = dict(scope, content="ab한")
    auth = {"Authorization": "Bearer " + token}
    # 이전 실행에서 짧은 범위 ID로 저장한 원문을 서비스 재기동 뒤 읽는다.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    old = SQLiteRuntimeStore(data_dir / "runtime_pointers.db").put("legacy", "w1", "s1")
    with TestClient(app) as client:
        legacy_read = {"workspace_id": "w1", "session_id": "s1", "pointer_id": old}
        assert (
            client.post(base + "/read", json=legacy_read, headers=auth).json()["content"]
            == "legacy"
        )
        assert client.post(base, json=body).status_code == 401
        assert (
            client.post(
                base, json=body, headers={**auth, "Origin": "http://other.local"}
            ).status_code
            == 403
        )
        created = client.post(base, json=body, headers=auth).json()
        pointer = created["pointer_id"]
        assert created["byte_size"] == 5
        assert (
            created["pointer_uri"] == f"securecode://runtime/ws_12345678/ses_12345678/{pointer}?v=1"
        )
        read = dict(scope, pointer_id=pointer)
        first = client.post(base + "/read", json={**read, "max_bytes": 3}, headers=auth)
        assert first.json()["content"] == "ab"
        assert first.json()["next_cursor"] == 2
        assert (
            client.post(base + "/read", json={**read, "session_id": "s2"}, headers=auth).status_code
            == 403
        )
        assert (
            client.post(base + "/read", json={**read, "max_bytes": 0}, headers=auth).status_code
            >= 400
        )
        assert (
            client.post(base, json={**body, "workspace_id": "foo/bar"}, headers=auth).status_code
            >= 400
        )
        expired = client.post(base, json={**body, "ttl_seconds": 0}, headers=auth).json()
        assert (
            client.post(
                base + "/read", json={**read, "pointer_id": expired["pointer_id"]}, headers=auth
            ).status_code
            == 410
        )
        assert client.get(base, params=scope, headers=auth).json()["pointer_ids"] == [pointer]
        assert (
            client.delete(
                base + "/" + pointer, params={**scope, "workspace_id": "x"}, headers=auth
            ).status_code
            == 404
        )
        assert client.delete(base + "/" + pointer, params=scope, headers=auth).json() == {
            "deleted": True
        }
    assert (tmp_path / "data/runtime_pointers.db").is_file()
    assert not (tmp_path / "runtime_pointers.db").exists()
