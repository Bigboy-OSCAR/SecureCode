"""작업 공간 revision 저장·원자 전환·변경 감지·stale 거부·상태 계약 시험."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.symbols.graph import IndexCapacityError
from securecode_context.symbols.index import (
    RevisionStore,
    RevisionStoreError,
    RootPolicy,
    SymbolIndexService,
    diff_manifests,
)
from securecode_context.symbols.index import revision_store as store_module
from securecode_context.symbols.index import service as service_module
from support.symbol_projects import LANGUAGE_PROJECTS, write_project

WORKSPACE_ID = "ws_01J9Z6Q4TEST"
STATUS_SCHEMA = "api/workspace.schema.json#/definitions/IndexStatusResponse"
PROVENANCE_SCHEMA = "symbols/symbol.schema.json#/definitions/SourceProvenance"
COMPUTE = "memory://symbol/pkg/service.py::compute"


class FixtureSourceRegistry:
    """
    클래스 이름: FixtureSourceRegistry
    기능: [fixture] 4.5 등록부 대신 경로·해시가 같을 때만 정해진 Source URI를 돌려준다.
    작성 날짜: 2026/11/05
    """

    def __init__(self, registered: dict[tuple[str, str], str]) -> None:
        """
        함수 이름: __init__()
        기능: (경로, 해시) → URI 표를 보관한다.
        인자: registered -> 등록 표
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.registered = registered

    def lookup(self, workspace_id: str, relative_path: str, content_sha256: str) -> str | None:
        """
        함수 이름: lookup()
        기능: 같은 작업 공간·경로·해시의 등록만 인정한다.
        인자: workspace_id -> 작업 공간, relative_path -> 경로, content_sha256 -> 해시
        반환값: URI 또는 None
        작성 날짜: 2026/11/05
        """
        if workspace_id != WORKSPACE_ID:
            return None
        return self.registered.get((relative_path, content_sha256))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """
    함수 이름: workspace()
    기능: Python fixture 프로젝트를 임시 작업 공간에 만든다.
    인자: tmp_path -> pytest 임시 폴더
    반환값: 작업 공간 루트
    작성 날짜: 2026/11/05
    """
    root = tmp_path / "workspace"
    write_project(root, LANGUAGE_PROJECTS["python"])
    return root


@pytest.fixture
def service(tmp_path: Path) -> SymbolIndexService:
    """
    함수 이름: service()
    기능: 임시 데이터 폴더를 쓰는 색인 서비스를 만든다.
    인자: tmp_path -> pytest 임시 폴더
    반환값: SymbolIndexService
    작성 날짜: 2026/11/05
    """
    return SymbolIndexService(RevisionStore(tmp_path / "data" / "workspaces"))


def test_build_publishes_ready_revision(service, workspace, contract_check) -> None:
    """
    함수 이름: test_build_publishes_ready_revision()
    기능: 첫 빌드가 TF-IDF 벡터까지 준비한 revision 1을 ready로 게시하고 상태에 원문을 넣지 않는지 확인한다.
    인자: service -> 색인 서비스, workspace -> 작업 공간, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    assert service.status(WORKSPACE_ID, workspace)["index_status"] == "not_indexed"
    status = service.build(WORKSPACE_ID, workspace)
    assert contract_check(STATUS_SCHEMA, status) == []
    assert status["index_status"] == "ready" and status["searchable"] is True
    assert (status["index_revision"], status["pending_revision"]) == (1, None)
    assert status["counts"] == {"discovered": 3, "indexed": 3, "skipped": 0, "failed": 0}
    serialized = json.dumps(status)
    assert "def compute" not in serialized and str(workspace) not in serialized
    record = service.current(WORKSPACE_ID)
    assert record["retrieval"]["state"] == "ready"
    assert record["retrieval"]["candidate_count"] == len(record["raw"]) > 0
    assert record["retrieval"]["vocabulary_size"] > 0
    assert record["languages"] == ["python"]
    assert sorted(record["changes"]["added"]) == sorted(LANGUAGE_PROJECTS["python"])
    assert service.status(WORKSPACE_ID, workspace)["index_status"] == "ready"


def test_modify_delete_move_switch_revisions(service, workspace) -> None:
    """
    함수 이름: test_modify_delete_move_switch_revisions()
    기능: 수정·삭제·이동마다 stale을 감지하고 새 revision으로 전환하며 이전 revision 요청을 거부한다.
    인자: service -> 색인 서비스, workspace -> 작업 공간
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service.build(WORKSPACE_ID, workspace)
    (workspace / "pkg/constants.py").write_text("RATE = 4\n")
    assert service.status(WORKSPACE_ID, workspace)["index_status"] == "stale"
    second = service.build(WORKSPACE_ID, workspace)
    assert second["index_revision"] == 2 and second["index_status"] == "ready"
    changes = service.current(WORKSPACE_ID)["changes"]
    assert changes["modified"] == ["pkg/constants.py"]
    assert changes["idf_recompute_required"] and changes["bundle_rebuild_required"]
    # helper·compute bundle처럼 상수에 의존하던 후보까지 다시 만들어야 한다.
    assert COMPUTE in changes["stale_candidate_ids"]
    with pytest.raises(ServiceError) as superseded:
        service.require_revision(WORKSPACE_ID, 1)
    assert superseded.value.code is ErrorCode.SOURCE_CHANGED

    (workspace / "pkg/service.py").rename(workspace / "pkg/jobs.py")
    assert service.status(WORKSPACE_ID, workspace)["index_status"] == "stale"
    service.build(WORKSPACE_ID, workspace)
    record = service.current(WORKSPACE_ID)
    assert record["changes"]["moved"] == [{"from_path": "pkg/service.py", "to_path": "pkg/jobs.py"}]
    assert "memory://symbol/pkg/jobs.py::compute" in record["nodes"]
    assert COMPUTE not in record["nodes"]

    (workspace / "pkg/helpers.py").unlink()
    service.build(WORKSPACE_ID, workspace)
    record = service.current(WORKSPACE_ID)
    assert record["index_revision"] == 4 and record["parent_revision"] == 3
    assert record["changes"]["deleted"] == ["pkg/helpers.py"]
    assert not any(node["path"] == "pkg/helpers.py" for node in record["nodes"].values())
    assert (
        "scale" in record["nodes"]["memory://symbol/pkg/jobs.py::compute"]["unresolved_reference"]
    )
    assert service.status(WORKSPACE_ID, workspace)["index_status"] == "ready"


def test_touch_without_content_change_is_not_stale(service, workspace) -> None:
    """
    함수 이름: test_touch_without_content_change_is_not_stale()
    기능: 수정 시각만 바뀐 파일은 해시를 다시 확인해 stale로 보지 않는다.
    인자: service -> 색인 서비스, workspace -> 작업 공간
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service.build(WORKSPACE_ID, workspace)
    target = workspace / "pkg/constants.py"
    info = target.stat()
    os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns + 5_000_000_000))
    assert service.status(WORKSPACE_ID, workspace)["index_status"] == "ready"
    (workspace / "pkg/new.py").write_text("NEW = 1\n")
    (workspace / "README.md").write_text("not indexed\n")
    assert service.status(WORKSPACE_ID, workspace)["index_status"] == "stale"


def test_stale_source_is_not_returned(tmp_path, workspace, contract_check) -> None:
    """
    함수 이름: test_stale_source_is_not_returned()
    기능: 재색인 전에 파일이 바뀌면 원문 대신 SOURCE_CHANGED를 반환하고 등록 포인터를 붙인다.
    인자: tmp_path -> 임시 폴더, workspace -> 작업 공간, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    store = RevisionStore(tmp_path / "data")
    probe = SymbolIndexService(store)
    probe.build(WORKSPACE_ID, workspace)
    file_hash = probe.current(WORKSPACE_ID)["manifest"]["pkg/service.py"]
    pointer = f"securecode://source/{WORKSPACE_ID}/src_0001?v=1"
    registry = FixtureSourceRegistry({("pkg/service.py", file_hash): pointer})
    service = SymbolIndexService(store, source_registry=registry)
    verified = service.verified_symbol(WORKSPACE_ID, workspace, 1, COMPUTE)
    assert verified.provenance["pointer"] == pointer
    assert contract_check(PROVENANCE_SCHEMA, verified.provenance) == []
    helper = service.verified_symbol(
        WORKSPACE_ID, workspace, 1, "memory://symbol/pkg/helpers.py::scale"
    )
    assert helper.provenance["pointer"] is None

    (workspace / "pkg/service.py").write_text("def compute(x):\n    return 0\n")
    with pytest.raises(ServiceError) as changed:
        service.verified_symbol(WORKSPACE_ID, workspace, 1, COMPUTE)
    assert changed.value.code is ErrorCode.SOURCE_CHANGED
    assert changed.value.details["reason"] == "content_changed"
    with pytest.raises(ServiceError) as missing:
        service.verified_symbol(WORKSPACE_ID, workspace, 1, "memory://symbol/none.py::x")
    assert missing.value.code is ErrorCode.NOT_FOUND


def test_failed_publish_keeps_previous_revision(service, workspace, monkeypatch) -> None:
    """
    함수 이름: test_failed_publish_keeps_previous_revision()
    기능: current.json 교체 직전 실패나 용량 초과가 나도 이전 revision만 계속 제공하는지 확인한다.
    인자: service -> 색인 서비스, workspace -> 작업 공간, monkeypatch -> 실패 주입
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    service.build(WORKSPACE_ID, workspace)
    (workspace / "pkg/constants.py").write_text("RATE = 9\n")
    real_replace = os.replace

    def fail_on_pointer(source: str | Path, target: str | Path) -> None:
        """
        함수 이름: fail_on_pointer()
        기능: revision 파일은 쓰고 current.json 교체만 실패시킨다.
        인자: source -> 임시 파일, target -> 최종 경로
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        if Path(target).name == "current.json":
            raise OSError("disk full")
        real_replace(source, target)

    monkeypatch.setattr(store_module.os, "replace", fail_on_pointer)
    failed = service.build(WORKSPACE_ID, workspace)
    assert failed["index_status"] == "failed" and failed["index_revision"] == 1
    monkeypatch.setattr(store_module.os, "replace", real_replace)
    fresh = SymbolIndexService(service.store)
    record = fresh.current(WORKSPACE_ID)
    assert record["index_revision"] == 1 and "RATE = 3" in json.dumps(record["nodes"])
    leftovers = list(service.store.symbols_dir(WORKSPACE_ID).rglob(".tmp-*"))
    assert leftovers == []

    def too_large(*_args: object, **_kwargs: object) -> None:
        """
        함수 이름: too_large()
        기능: 작업 공간 용량 초과를 흉내 낸다.
        인자: 임의 인자
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        raise IndexCapacityError("workspace source fragment limit exceeded")

    monkeypatch.setattr(service_module, "scan_workspace", too_large)
    assert fresh.build(WORKSPACE_ID, workspace)["index_status"] == "failed"
    assert fresh.current(WORKSPACE_ID)["index_revision"] == 1
    monkeypatch.undo()
    # 실패해 남은 2번 파일이 있어도 다음 게시는 번호를 재사용하지 않는다.
    assert fresh.build(WORKSPACE_ID, workspace)["index_revision"] == 3


def test_concurrent_build_reports_indexing(service, workspace, monkeypatch) -> None:
    """
    함수 이름: test_concurrent_build_reports_indexing()
    기능: 빌드 중 두 번째 요청은 새 빌드를 시작하지 않고 pending_revision을 보여준다.
    인자: service -> 색인 서비스, workspace -> 작업 공간, monkeypatch -> 스캔 지연 주입
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    started, release = threading.Event(), threading.Event()
    real_scan = service_module.scan_workspace

    def slow_scan(*args: object, **kwargs: object) -> object:
        """
        함수 이름: slow_scan()
        기능: 첫 빌드를 멈춰 동시 요청을 재현한다.
        인자: 원래 스캔 인자
        반환값: 원래 스캔 결과
        작성 날짜: 2026/11/05
        """
        started.set()
        release.wait(timeout=10)
        return real_scan(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service_module, "scan_workspace", slow_scan)
    worker = threading.Thread(target=service.build, args=(WORKSPACE_ID, workspace))
    worker.start()
    assert started.wait(timeout=10)
    during = service.build(WORKSPACE_ID, workspace)
    assert (during["index_status"], during["pending_revision"]) == ("indexing", 1)
    assert during["index_revision"] is None
    release.set()
    worker.join(timeout=10)
    assert service.status(WORKSPACE_ID, workspace)["index_revision"] == 1


def test_store_rejects_bad_ids_and_mixed_records(tmp_path: Path, service, workspace) -> None:
    """
    함수 이름: test_store_rejects_bad_ids_and_mixed_records()
    기능: 경로 이탈 ID, 다른 작업 공간의 기록, 재사용 번호를 거부하고 오래된 파일을 정리한다.
    인자: tmp_path -> 임시 폴더, service -> 색인 서비스, workspace -> 작업 공간
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    store = service.store
    for bad in ("../ws_01J9Z6Q4TEST", "ws_short", "ws_01J9Z6Q4TEST/.."):
        with pytest.raises(ServiceError):
            store.symbols_dir(bad)
    for _ in range(3):
        (workspace / "pkg/constants.py").write_text(f"RATE = {_}\n")
        service.build(WORKSPACE_ID, workspace)
    revisions = sorted(p.name for p in (store.symbols_dir(WORKSPACE_ID) / "revisions").iterdir())
    assert revisions == ["2.json", "3.json"]
    record = store.load(WORKSPACE_ID, 3)
    with pytest.raises(RevisionStoreError):
        store.publish(record)
    other = "ws_OTHER0000TEST"
    target = store.symbols_dir(other) / "revisions"
    target.mkdir(parents=True)
    (target / "1.json").write_text(json.dumps(record))
    with pytest.raises(RevisionStoreError):
        store.load(other, 1)


def test_root_policy_and_store_inside_workspace(tmp_path: Path, workspace) -> None:
    """
    함수 이름: test_root_policy_and_store_inside_workspace()
    기능: 상대·파일·최상위·허용 밖 루트를 거부하고 작업 공간 안 저장소를 색인하지 않는다.
    인자: tmp_path -> 임시 폴더, workspace -> 작업 공간
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    policy = RootPolicy((workspace.parent,))
    rejected = {
        Path("relative"): "root_not_absolute",
        workspace / "pkg/constants.py": "root_not_directory",
        Path(workspace.anchor): "root_is_filesystem_root",
        tmp_path / "missing": "root_not_found",
    }
    for root, reason in rejected.items():
        with pytest.raises(ServiceError) as error:
            RootPolicy().resolve(root)
        assert (error.value.code, error.value.details["reason"]) == (ErrorCode.FORBIDDEN, reason)
    elsewhere = tmp_path.parent
    with pytest.raises(ServiceError) as outside:
        policy.resolve(elsewhere)
    assert outside.value.details["reason"] == "path_outside_allowed_roots"

    inner_store = RevisionStore(workspace / "index-data")
    service = SymbolIndexService(inner_store, root_policy=policy)
    service.build(WORKSPACE_ID, workspace)
    service.build(WORKSPACE_ID, workspace)
    record = service.current(WORKSPACE_ID)
    assert not any(path.startswith("index-data/") for path in record["file_stats"])
    assert service.status(WORKSPACE_ID, workspace)["index_status"] == "ready"


def test_diff_manifests_ambiguous_copy_is_not_a_move() -> None:
    """
    함수 이름: test_diff_manifests_ambiguous_copy_is_not_a_move()
    기능: 같은 내용이 두 곳에 생기면 이동으로 단정하지 않고 추가·삭제로 남긴다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    changes = diff_manifests({"a.py": "h1", "b.py": "h2"}, {"c.py": "h1", "d.py": "h1"})
    assert changes == {
        "added": ["c.py", "d.py"],
        "modified": [],
        "deleted": ["a.py", "b.py"],
        "moved": [],
    }


def test_cli_publishes_revisions(tmp_path: Path, workspace, contract_check) -> None:
    """
    함수 이름: test_cli_publishes_revisions()
    기능: 실제 CLI --store 실행이 revision을 차례로 게시하고 원문 없는 상태 JSON만 출력하는지 확인한다.
    인자: tmp_path -> 임시 폴더, workspace -> 작업 공간, contract_check -> 계약 검사
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    store_dir = tmp_path / "data"
    command = [
        sys.executable,
        "-m",
        "securecode_context.symbols",
        str(workspace),
        "--store",
        str(store_dir),
        "--workspace-id",
        WORKSPACE_ID,
    ]
    first = json.loads(subprocess.run(command, check=True, capture_output=True).stdout)
    (workspace / "pkg/helpers.py").unlink()
    second = json.loads(subprocess.run(command, check=True, capture_output=True).stdout)
    assert (first["index_revision"], second["index_revision"]) == (1, 2)
    assert contract_check(STATUS_SCHEMA, second) == []
    assert "def compute" not in json.dumps(second)
    current = json.loads((store_dir / WORKSPACE_ID / "symbols/current.json").read_text())
    assert current["index_revision"] == 2
    rejected = subprocess.run([*command[:-1], "../escape"], capture_output=True)
    assert rejected.returncode == 1 and not (tmp_path / "escape").exists()
