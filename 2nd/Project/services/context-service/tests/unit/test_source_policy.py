"""4.5 Source 파일 정책: 경로 이탈·링크·외부 허용 목록·형식/크기·등록 중 변경·디렉터리 등록."""

from pathlib import Path

import pytest

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source import media, paths
from securecode_context.pointers.source.models import SourceLocation, SourceTarget
from support.source_fixtures import (
    WS_A,
    WS_B,
    code_of,
    make_dir_link,
    make_file_link,
    make_workspaces,
    open_registry,
    workspace_file,
)


def _external(kind: str, path: Path | str) -> SourceTarget:
    """
    함수 이름: _external()
    기능: 사용자가 명시한 외부 대상 요청을 만든다.
    인자: kind -> file/directory, path -> 절대 경로
    반환값: SourceTarget
    작성 날짜: 2026/11/10
    """
    return SourceTarget(
        SourceLocation.EXTERNAL, "file" if kind == "file" else "directory", str(path)
    )


@pytest.mark.parametrize(
    "raw", ["../secret.txt", "a/../../secret.txt", "/etc/passwd", "C:/x.txt", "a\\b.txt", "./a.txt"]
)
def test_relative_path_escape_is_forbidden(tmp_path: Path, raw: str) -> None:
    """
    함수 이름: test_relative_path_escape_is_forbidden()
    기능: 작업 공간 대상의 상위·절대·드라이브·역슬래시·점 경로를 거부하는지 확인한다.
    인자: tmp_path -> 임시 폴더, raw -> 공격 경로
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    (tmp_path / "secret.txt").write_text("secret\n")
    with open_registry(tmp_path, roots) as registry, pytest.raises(ServiceError) as denied:
        registry.register(WS_A, workspace_file(raw))
    assert code_of(denied) is ErrorCode.FORBIDDEN


def test_sibling_directory_link_escape_is_forbidden(tmp_path: Path) -> None:
    """
    함수 이름: test_sibling_directory_link_escape_is_forbidden()
    기능: 3.6 재현 P9(ws와 ws_evil 접두어 혼동)를 링크로 시도해도 등록·조회가 거부되는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    evil = tmp_path / "ws_a_evil"
    evil.mkdir()
    (evil / "secret.txt").write_text("SIBLING_SECRET\n")
    make_dir_link(roots.roots[WS_A] / "docs", evil)
    with open_registry(tmp_path, roots) as registry, pytest.raises(ServiceError) as denied:
        registry.register(WS_A, workspace_file("docs/secret.txt"))
    assert code_of(denied) is ErrorCode.FORBIDDEN


def test_directory_swapped_to_link_after_registration(tmp_path: Path) -> None:
    """
    함수 이름: test_directory_swapped_to_link_after_registration()
    기능: 등록 뒤 상위 디렉터리를 같은 내용의 외부 링크로 바꿔도 stat이 거부되는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    docs = roots.roots[WS_A] / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("same\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.txt").write_text("same\n")
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, workspace_file("docs/a.txt")).items[0]
        (docs / "a.txt").unlink()
        docs.rmdir()
        make_dir_link(docs, outside)
        with pytest.raises(ServiceError) as denied:
            registry.stat(WS_A, record.pointer)
        assert code_of(denied) is ErrorCode.FORBIDDEN


def test_file_symlink_is_forbidden(tmp_path: Path) -> None:
    """
    함수 이름: test_file_symlink_is_forbidden()
    기능: 작업 공간 안의 파일 symlink가 외부를 가리키면 거부하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n")
    make_file_link(roots.roots[WS_A] / "link.txt", outside)
    with open_registry(tmp_path, roots) as registry, pytest.raises(ServiceError) as denied:
        registry.register(WS_A, workspace_file("link.txt"))
    assert code_of(denied) is ErrorCode.FORBIDDEN


def test_external_file_grant_is_exact_scoped_and_revoked(tmp_path: Path) -> None:
    """
    함수 이름: test_external_file_grant_is_exact_scoped_and_revoked()
    기능: 외부 파일 허용은 그 파일 하나·그 workspace에만 적용되고, 해제하면 권한도 사라지는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "spec.md").write_text("# spec\n")
    (shared / "other.md").write_text("# other\n")
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, _external("file", shared / "spec.md")).items[0]
        assert record.location is SourceLocation.EXTERNAL
        assert registry.stat(WS_A, record.pointer).revision == 1
        with pytest.raises(ServiceError) as other_workspace:
            registry.stat(WS_B, record.pointer)
        assert code_of(other_workspace) is ErrorCode.FORBIDDEN
        registry.unregister(WS_A, record.pointer)
        assert registry.list_sources(WS_A).items == []
    with open_registry(tmp_path, roots) as restarted:
        relisted = restarted.register(WS_A, _external("file", shared / "spec.md")).items[0]
        assert relisted.source_id != record.source_id
    assert (shared / "spec.md").exists() and (shared / "other.md").exists()


def test_external_path_rules(tmp_path: Path) -> None:
    """
    함수 이름: test_external_path_rules()
    기능: 상대·네트워크·서비스 데이터 폴더·파일 시스템 최상위·없는 경로·kind 불일치를 거부하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    (tmp_path / "file.txt").write_text("x\n")
    cases = {
        "relative/path.txt": ErrorCode.FORBIDDEN,
        "//server/share/a.txt": ErrorCode.FORBIDDEN,
        str(tmp_path / "data"): ErrorCode.FORBIDDEN,
        str(Path(tmp_path.anchor)): ErrorCode.FORBIDDEN,
        str(tmp_path / "missing"): ErrorCode.NOT_FOUND,
    }
    with open_registry(tmp_path, roots) as registry:
        for raw, expected in cases.items():
            with pytest.raises(ServiceError) as denied:
                registry.register(WS_A, _external("directory", raw))
            assert code_of(denied) is expected, raw
        with pytest.raises(ServiceError) as mismatch:
            registry.register(WS_A, _external("directory", tmp_path / "file.txt"))
        assert code_of(mismatch) is ErrorCode.UNSUPPORTED_FORMAT


@pytest.mark.parametrize(
    ("name", "content"),
    [("fake.pdf", b"not a pdf"), ("hidden.txt", b"%PDF-1.7\n"), ("blob.txt", b"ab\x00cd")],
)
def test_disguised_or_binary_content_is_unsupported(
    tmp_path: Path, name: str, content: bytes
) -> None:
    """
    함수 이름: test_disguised_or_binary_content_is_unsupported()
    기능: 확장자 위장 PDF·PDF를 숨긴 텍스트·이진 파일을 거부하는지 확인한다.
    인자: tmp_path -> 임시 폴더, name -> 파일 이름, content -> 내용
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    (roots.roots[WS_A] / name).write_bytes(content)
    with open_registry(tmp_path, roots) as registry, pytest.raises(ServiceError) as rejected:
        registry.register(WS_A, workspace_file(name))
    assert code_of(rejected) is ErrorCode.UNSUPPORTED_FORMAT


def test_size_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    함수 이름: test_size_limit_is_enforced()
    기능: 형식별 크기 상한을 넘으면 등록하지 않는지 확인한다(상한 값은 작게 바꿔 시험).
    인자: tmp_path -> 임시 폴더, monkeypatch -> 상한 변경
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    (roots.roots[WS_A] / "big.txt").write_bytes(b"x" * 2048)
    monkeypatch.setattr(media, "size_limit", lambda _media: 1024)
    with open_registry(tmp_path, roots) as registry:
        with pytest.raises(ServiceError) as too_large:
            registry.register(WS_A, workspace_file("big.txt"))
        assert code_of(too_large) is ErrorCode.PAYLOAD_TOO_LARGE
        assert registry.list_sources(WS_A).items == []


def test_change_during_register_fails_without_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    함수 이름: test_change_during_register_fails_without_record()
    기능: hash 계산 도중 원본이 바뀌면 SOURCE_CHANGED이고 섞인 fingerprint를 저장하지 않는지 확인한다.
    인자: tmp_path -> 임시 폴더, monkeypatch -> 변경 시점 주입
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    target = roots.roots[WS_A] / "live.log"
    target.write_text("start\n")
    original = paths.identity_of
    calls = 0

    def append_after_first(file: object) -> tuple[int, int, int, int, int]:
        """
        함수 이름: append_after_first()
        기능: 첫 identity 측정 직후 실제 파일에 내용을 덧붙인다.
        인자: file -> 열린 원본
        반환값: 원래 identity
        작성 날짜: 2026/11/10
        """
        nonlocal calls
        calls += 1
        identity = original(file)  # type: ignore[arg-type]
        if calls == 1:
            with target.open("a") as handle:
                handle.write("appended while hashing\n")
        return identity

    monkeypatch.setattr(paths, "identity_of", append_after_first)
    with open_registry(tmp_path, roots) as registry:
        with pytest.raises(ServiceError) as changed:
            registry.register(WS_A, workspace_file("live.log"))
        assert code_of(changed) is ErrorCode.SOURCE_CHANGED
        assert registry.list_sources(WS_A).items == []


def test_directory_registration_reports_each_entry_once(tmp_path: Path) -> None:
    """
    함수 이름: test_directory_registration_reports_each_entry_once()
    기능: 디렉터리 등록이 파일마다 items 또는 issues 한 곳에만 나오고 partial이 되는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    docs = roots.roots[WS_A] / "docs"
    (docs / "sub").mkdir(parents=True)
    (docs / "a.md").write_text("# a\n")
    (docs / "sub" / "b.txt").write_text("b\n")
    (docs / "blob.bin").write_bytes(b"\x00\x01")
    target = SourceTarget(SourceLocation.WORKSPACE, "directory", "docs")
    with open_registry(tmp_path, roots) as registry:
        result = registry.register(WS_A, target)
    assert result.status == "partial"
    assert sorted(item.relative_path.as_posix() for item in result.items) == [
        "docs/a.md",
        "docs/sub/b.txt",
    ]
    assert [(issue.relative_path, issue.code) for issue in result.issues] == [
        ("blob.bin", "UNSUPPORTED_FORMAT")
    ]


def test_directory_over_100_entries_registers_nothing(tmp_path: Path) -> None:
    """
    함수 이름: test_directory_over_100_entries_registers_nothing()
    기능: 100개를 넘는 폴더는 등록 전에 PAYLOAD_TOO_LARGE로 거절하는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    many = roots.roots[WS_A] / "many"
    many.mkdir()
    for index in range(101):
        (many / f"{index:03}.txt").write_text("x\n")
    target = SourceTarget(SourceLocation.WORKSPACE, "directory", "many")
    with open_registry(tmp_path, roots) as registry:
        with pytest.raises(ServiceError) as too_many:
            registry.register(WS_A, target)
        assert code_of(too_many) is ErrorCode.PAYLOAD_TOO_LARGE
        assert registry.list_sources(WS_A).items == []


def test_restart_rechecks_workspace_root_link(tmp_path: Path) -> None:
    """
    함수 이름: test_restart_rechecks_workspace_root_link()
    기능: 재시작 뒤 workspace root가 링크로 바뀌면 이전 등록도 거부되는지 확인한다.
    인자: tmp_path -> 임시 폴더
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    roots = make_workspaces(tmp_path)
    (roots.roots[WS_A] / "a.txt").write_text("a\n")
    with open_registry(tmp_path, roots) as registry:
        record = registry.register(WS_A, workspace_file("a.txt")).items[0]
    moved = tmp_path / "moved"
    roots.roots[WS_A].rename(moved)
    make_dir_link(roots.roots[WS_A], moved)
    with open_registry(tmp_path, roots) as restarted, pytest.raises(ServiceError) as denied:
        restarted.stat(WS_A, record.pointer)
    assert code_of(denied) is ErrorCode.FORBIDDEN
