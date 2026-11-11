"""3.6 내부 작업 공간 등록·R0 색인/검색/묶음 경로를 실제 앱(데이터 폴더 등록부)으로 시험한다."""

import time
from collections.abc import Iterator
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from fastapi.testclient import TestClient

from securecode_context.api.symbols import _BUILDS
from securecode_context.app.factory import create_app
from securecode_context.app.settings import ServiceSettings
from support.helpers import TEST_TOKEN, ContractCheck, FixedTokenCounter
from support.symbol_projects import LANGUAGE_PROJECTS, write_project

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
WS = "ws_00000001"
STATUS_REF = "api/workspace.schema.json#/definitions/IndexStatusResponse"
SEARCH_REF = "symbols/symbol.schema.json#/definitions/SymbolSearchResponse"
BUNDLE_REF = "symbols/symbol.schema.json#/definitions/SymbolBundle"


@pytest.fixture
def env(service_settings: ServiceSettings, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """
    함수 이름: env()
    기능: Python 프로젝트 작업 공간과 기본 등록부 앱(시험 root 포트 없음)을 준비한다.
    인자: service_settings -> 시험 설정, tmp_path -> 임시 폴더
    반환값: client·root 사전
    작성 날짜: 2026/11/10
    """
    root = tmp_path / "project"
    write_project(root, LANGUAGE_PROJECTS["python"])
    with TestClient(create_app(service_settings, token_counter=FixedTokenCounter())) as client:
        yield {"client": client, "root": root, "data": service_settings.data_dir}


def post(env: dict[str, Any], route: str, body: dict[str, Any]) -> Any:
    """
    함수 이름: post()
    기능: 내부 경로를 호출하고 응답 JSON을 돌려준다.
    인자: env -> 환경, route -> 경로, body -> 본문
    반환값: 응답 JSON
    작성 날짜: 2026/11/10
    """
    return env["client"].post(f"/internal/v1/{route}", json=body, headers=AUTH).json()


def register(env: dict[str, Any], root: Path) -> Any:
    """
    함수 이름: register()
    기능: 작업 공간 root를 등록한다.
    인자: env -> 환경, root -> root 경로
    반환값: 응답 JSON
    작성 날짜: 2026/11/10
    """
    return post(
        env,
        "workspaces/register",
        {"schema_version": "1", "workspace_id": WS, "root_path": str(root)},
    )


def test_register_index_search_and_bundle(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_register_index_search_and_bundle()
    기능: 등록 → 백그라운드 색인 → ready → 검색(원문 없음) → 묶음(상한 안 원문)이 계약대로 동작한다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    assert register(env, env["root"])["registered"] is True
    status = post(env, "symbols/index", {"schema_version": "1", "workspace_id": WS})
    deadline = time.monotonic() + 30
    while status["index_status"] not in ("ready", "partial") and time.monotonic() < deadline:
        assert contract_check(STATUS_REF, status) == []
        time.sleep(0.1)
        status = post(env, "symbols/index/status", {"schema_version": "1", "workspace_id": WS})
    assert contract_check(STATUS_REF, status) == [] and status["searchable"] is True
    found = post(env, "symbols/search", {"workspace_id": WS, "query": "compute traced"})
    assert contract_check(SEARCH_REF, found) == []
    first = found["candidates"][0]
    assert "def compute" not in str(found), "search returns metadata only"
    bundle = post(env, "symbols/bundle", {
        "workspace_id": WS, "candidate_id": first["candidate_id"],
        "index_revision": first["index_revision"], "max_tokens": 4000,
    })  # fmt: skip
    assert contract_check(BUNDLE_REF, bundle) == []
    assert bundle["fragments"] and "def compute" in bundle["fragments"][0]["content"]


def test_registration_rechecks_roots(env: dict[str, Any], tmp_path: Path) -> None:
    """
    함수 이름: test_registration_rechecks_roots()
    기능: 상대 경로·파일·서비스 데이터 폴더와 겹치는 root·다른 root 재등록을 서버가 거절하고,
        등록 안 된 workspace는 검색할 수 없다.
    인자: env -> 환경, tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    assert register(env, Path("relative"))["error"]["details"]["reason"] == "root_not_absolute"
    assert register(env, file_path)["error"]["details"]["reason"] == "root_not_directory"
    assert register(env, env["data"])["error"]["details"]["reason"] == "root_overlaps_service_data"
    unknown = post(env, "symbols/search", {"workspace_id": WS, "query": "compute"})
    assert unknown["error"]["code"] == "NOT_FOUND"
    register(env, env["root"])
    other = tmp_path / "other"
    other.mkdir()
    assert register(env, other)["error"]["details"]["reason"] == "root_conflict"


def test_queued_index_stays_pending_until_worker_starts(
    env: dict[str, Any], contract_check: ContractCheck
) -> None:
    """
    함수 이름: test_queued_index_stays_pending_until_worker_starts()
    기능: 다른 색인 작업 뒤에 대기한 프로젝트가 not_indexed로 돌아가지 않고 중복 제출되지 않는다.
    인자: env -> 환경, contract_check -> 계약 검사기
    반환값: 없음
    작성 날짜: 2026/11/11
    """
    release = Event()
    blocker = _BUILDS.submit(release.wait, 10)
    try:
        assert register(env, env["root"])["registered"] is True
        body = {"schema_version": "1", "workspace_id": WS}
        started = post(env, "symbols/index", body)
        assert started["index_status"] == "queued"
        assert contract_check(STATUS_REF, started) == []
        job = env["client"].app.state.index_jobs[WS]
        assert post(env, "symbols/index/status", body)["index_status"] == "queued"
        assert post(env, "symbols/index", body)["index_status"] == "queued"
        assert env["client"].app.state.index_jobs[WS] is job
    finally:
        release.set()
        blocker.result(timeout=10)
    job.result(timeout=10)
    assert post(env, "symbols/index/status", body)["index_status"] == "ready"
