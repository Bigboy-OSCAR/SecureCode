"""다섯 언어 단독·혼합 프로젝트의 심볼 원문·위치·해시·정적 참조와 파일별 격리 시험."""

import hashlib
import sys
from pathlib import Path

import pytest

from securecode_context.symbols.graph import SourceNode
from securecode_context.symbols.index import build_index
from support.symbol_projects import (
    BROKEN_FILES,
    EXCLUDED_FILES,
    LANGUAGE_PROJECTS,
    SHARED_NAME_FILES,
    write_project,
)

# 언어별로 (시작 심볼, 기대하는 R0 bundle 구성원 이름) 을 고정한다.
EXPECTED_BUNDLES = {
    "python": ("pkg/service.py::compute", ["compute", "scale", "traced", "RATE"]),
    "c": ("main.c::run", ["run", "box", "clamp", "MAX_ITEMS"]),
    "cpp": ("main.cpp::total", ["total", "geo::Shape"]),
    "java": ("src/com/acme/app/Main.java::Main", ["Main", "Limits"]),
    "javascript": ("main.js::run", ["run", "double", "BASE"]),
}


def _assert_exact_source(root: Path, nodes: dict[str, SourceNode]) -> None:
    """
    함수 이름: _assert_exact_source()
    기능: 각 심볼의 원문·바이트·줄 범위·파일 해시가 디스크 파일과 같은지 확인한다.
    인자: root -> 프로젝트 루트, nodes -> 색인 심볼
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    for node in nodes.values():
        content = (root / node["path"]).read_bytes()
        assert content[node["start_byte"] : node["end_byte"]].decode() == node["source"]
        assert node["content_sha256"] == hashlib.sha256(content).hexdigest()
        start_line = content[: node["start_byte"]].count(b"\n") + 1
        end_line = start_line + node["source"].count("\n")
        assert (node["start"], node["end"]) == (start_line, end_line)


@pytest.mark.parametrize("language", sorted(LANGUAGE_PROJECTS))
def test_single_language_project(tmp_path: Path, language: str) -> None:
    """
    함수 이름: test_single_language_project()
    기능: 언어 하나만 있는 프로젝트에서 원문 위치와 다른 파일 참조로 만든 깊이 3 bundle을 확인한다.
    인자: tmp_path -> 임시 프로젝트, language -> 계약 언어 값
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    write_project(tmp_path, LANGUAGE_PROJECTS[language])
    index = build_index(tmp_path)
    nodes = index["nodes"]
    assert index["diagnostics"] == []
    assert {node["language"] for node in nodes.values()} == {language}
    assert set(index["manifest"]) == set(LANGUAGE_PROJECTS[language])
    _assert_exact_source(tmp_path, nodes)
    start, members = EXPECTED_BUNDLES[language]
    bundle = next(item for item in index["raw"] if item["id"] == "memory://symbol/" + start)
    assert [nodes[uri]["name"] for uri in bundle["source_uris"]] == members
    assert len({nodes[uri]["path"] for uri in bundle["source_uris"]}) > 1
    for uri in bundle["source_uris"]:
        assert nodes[uri]["source"] in bundle["text"]


def test_python_decorator_alias_and_dynamic_reference(tmp_path: Path) -> None:
    """
    함수 이름: test_python_decorator_alias_and_dynamic_reference()
    기능: 함수→다른 파일 helper→별칭 상수 경로, decorator 시작 줄, 동적 호출 미해결을 확인한다.
    인자: tmp_path -> 임시 프로젝트
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    write_project(tmp_path, LANGUAGE_PROJECTS["python"])
    nodes = build_index(tmp_path)["nodes"]
    compute = nodes["memory://symbol/pkg/service.py::compute"]
    assert compute["start"] == 8 and compute["source"].startswith("@traced\n")
    assert compute["deps"] == [
        "memory://symbol/pkg/helpers.py::scale",
        "memory://symbol/pkg/service.py::traced",
    ]
    assert "getattr()" in compute["unresolved_reference"]
    scale = nodes["memory://symbol/pkg/helpers.py::scale"]
    assert scale["deps"] == ["memory://symbol/pkg/constants.py::RATE"]
    assert "from .constants import RATE as R" in scale["imports"]


def test_mixed_project_keeps_languages_apart(tmp_path: Path) -> None:
    """
    함수 이름: test_mixed_project_keeps_languages_apart()
    기능: 다섯 언어·동명 심볼·순환·깨진 파일·TypeScript·제외 폴더가 섞여도 파일 단위로 처리한다.
    인자: tmp_path -> 임시 프로젝트
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    for language, files in LANGUAGE_PROJECTS.items():
        write_project(tmp_path / language, files)
    write_project(tmp_path, SHARED_NAME_FILES | BROKEN_FILES | EXCLUDED_FILES)
    index = build_index(tmp_path)
    nodes = index["nodes"]
    assert {node["language"] for node in nodes.values()} == set(LANGUAGE_PROJECTS)
    assert not any(
        node["path"].split("/")[0] in {".git", ".securecode", "node_modules", "venv", "build"}
        or node["path"].startswith("generated/")
        for node in nodes.values()
    )
    assert {item["relative_path"]: item["reason_code"] for item in index["diagnostics"]} == {
        "broken/Bad.java": "syntax_error",
        "broken/bad.c": "syntax_error",
        "broken/bad.js": "syntax_error",
        "broken/bad.py": "syntax_error",
        "broken/types.ts": "unsupported_language",
    }
    _assert_exact_source(tmp_path, nodes)

    # 같은 이름 helper는 호출한 언어의 파일로만 연결된다.
    expected_helper = {
        "shared/use.py::use_py": "shared/helper.py::helper",
        "shared/helper.c::use_c": "shared/helper.c::helper",
        "shared/use.mjs::useJs": "shared/helper.mjs::helper",
    }
    for caller, helper in expected_helper.items():
        assert nodes["memory://symbol/" + caller]["deps"] == ["memory://symbol/" + helper]

    ping = "memory://symbol/cycle/a.py::ping"
    pong = "memory://symbol/cycle/b.py::pong"
    assert nodes[ping]["deps"] == [pong] and nodes[pong]["deps"] == [ping]
    cycle_bundle = next(item for item in index["raw"] if item["id"] == ping)
    assert cycle_bundle["source_uris"] == [ping, pong]


def test_failures_are_isolated_per_file(tmp_path: Path) -> None:
    """
    함수 이름: test_failures_are_isolated_per_file()
    기능: 구문·인코딩·크기 오류 파일 옆의 정상 파일이 그대로 색인되는지 확인한다.
    인자: tmp_path -> 임시 프로젝트
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    write_project(tmp_path, BROKEN_FILES | LANGUAGE_PROJECTS["javascript"])
    (tmp_path / "latin1.py").write_bytes(b"NAME = '\xe9'\n")
    (tmp_path / "huge.java").write_bytes(b"class Huge {}" + b" " * (1024 * 1024))
    index = build_index(tmp_path)
    reasons = {item["relative_path"]: item["reason_code"] for item in index["diagnostics"]}
    assert reasons["latin1.py"] == "encoding_error"
    assert reasons["huge.java"] == "too_large"
    assert reasons["broken/bad.py"] == "syntax_error"
    assert {node["path"] for node in index["nodes"].values()} == set(
        LANGUAGE_PROJECTS["javascript"]
    )


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    """
    함수 이름: test_symlink_escape_is_rejected()
    기능: 루트 밖을 가리키는 파일·디렉터리 링크를 읽지 않고 path_rejected 또는 미탐색으로 둔다.
    인자: tmp_path -> 임시 루트와 외부 폴더의 부모
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    write_project(root, {"ok.py": "OK = 1\n"})
    write_project(outside, {"secret.py": "SECRET = 1\n"})
    try:
        (root / "link.py").symlink_to(outside / "secret.py")
        (root / "linked_dir").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation needs extra privileges on this machine")
    index = build_index(root)
    assert set(index["nodes"]) == {"memory://symbol/ok.py::OK"}
    assert {"relative_path": "link.py", "reason_code": "path_rejected"} in index["diagnostics"]
    assert all("SECRET" not in node["source"] for node in index["nodes"].values())


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junctions exist only on Windows")
def test_windows_junction_escape_is_rejected(tmp_path: Path) -> None:
    """
    함수 이름: test_windows_junction_escape_is_rejected()
    기능: 권한 없이 만들 수 있는 NTFS 정션이 루트 밖 원문을 색인에 넣지 않는지 확인한다.
    인자: tmp_path -> 임시 루트와 외부 폴더의 부모
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    import _winapi

    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    write_project(root, {"ok.py": "OK = 1\n"})
    write_project(outside, {"secret.py": "SECRET = 1\n"})
    _winapi.CreateJunction(str(outside), str(root / "junction"))
    index = build_index(root)
    assert set(index["nodes"]) == {"memory://symbol/ok.py::OK"}
    assert index["diagnostics"] == [{"relative_path": "junction", "reason_code": "path_rejected"}]
