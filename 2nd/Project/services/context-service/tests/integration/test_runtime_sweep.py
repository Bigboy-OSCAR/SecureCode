"""4.10: 서비스가 시작되면 TTL이 지난 Runtime 출력의 행과 파일을 실제로 지운다."""

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from support.helpers import TEST_TOKEN, FixedTokenCounter

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


def test_expired_outputs_are_swept_on_start(service_settings: ServiceSettings) -> None:
    """
    함수 이름: test_expired_outputs_are_swept_on_start()
    기능: 만료 시각을 과거로 바꾼 출력이 다음 서비스 시작 때 tombstone이 되고 blob 파일이 사라진다.
    인자: service_settings -> 시험 설정
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    scope = {"workspace_id": "ws_12345678", "session_id": "ses_12345678"}
    with TestClient(create_app(service_settings, token_counter=FixedTokenCounter())) as client:
        body = {**scope, "content": "EXPIRING-OUTPUT " * 400}
        created = client.post("/internal/v1/runtime/pointers", json=body, headers=AUTH).json()
    root = Path(service_settings.data_dir) / "runtime"
    blobs = [path for path in (root / "blobs").rglob("*") if path.is_file()]
    assert blobs, "the output was stored"
    with sqlite3.connect(root / "runtime.sqlite3") as db:
        db.execute(
            "UPDATE runtime_pointers SET expires_at = '2000-01-01T00:00:00+00:00' WHERE pointer_id = ?",
            (created["pointer_id"],),
        )
    with TestClient(create_app(service_settings, token_counter=FixedTokenCounter())) as client:
        read = client.post(
            "/internal/v1/runtime/read",
            json={"schema_version": "1", **scope, "pointer": created["pointer_uri"]},
            headers=AUTH,
        ).json()
    assert read["error"]["code"] in ("EXPIRED", "NOT_FOUND")
    assert not [path for path in blobs if path.exists()], "expired blob files were removed"
