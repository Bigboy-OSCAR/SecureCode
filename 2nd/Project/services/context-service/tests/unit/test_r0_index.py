"""R0 생성 명령, 혼합 워크스페이스의 참조 그래프와 재생성 회귀 시험."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from securecode_context.symbols.index import build_index


def test_mixed_workspace_cli(tmp_path: Path) -> None:
    """
    함수 이름: test_mixed_workspace_cli()
    기능: 실제 CLI 한 번으로 다섯 언어의 원문·해시·독립된 참조 묶음을 만들고 재생성을 확인한다.
    인자: tmp_path -> 임시 워크스페이스
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    programs = {
        "task.py": "def helper(): return 1\nasync def run(): return helper()",
        "task.c": "static int helper(void) {return 2;}\nint run(void) {return helper();}",
        "task.cpp": "namespace cpp { int helper() {return 3;} int run() {return helper();} }",
        "Task.java": "class Helper {static int n = 4;}\nclass Task {int run() {return Helper.n;}}",
        "task.js": "const helper = () => 5;\nexport function run() {return helper();}",
    }
    for path, source in programs.items():
        (tmp_path / path).write_bytes(source.encode())
    (tmp_path / "task.ts").write_text("export const unsupported: number = 0;")
    (tmp_path / "broken.java").write_text("class Broken {{{")
    output = tmp_path / "index.json"
    command = [
        sys.executable,
        "-m",
        "securecode_context.symbols",
        str(tmp_path),
        "--out",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True)
    first = output.read_bytes()
    index = json.loads(first)
    assert set(index["manifest"]) == {*programs, "broken.java"}
    assert {d["relative_path"]: d["reason_code"] for d in index["diagnostics"]} == {
        "broken.java": "syntax_error",
        "task.ts": "unsupported_language",
    }
    nodes = index["nodes"]
    assert {n["language"] for n in nodes.values()} == {"python", "c", "cpp", "java", "javascript"}
    for node in nodes.values():
        content = programs[node["path"]].encode()
        assert content[node["start_byte"] : node["end_byte"]].decode() == node["source"]
        assert node["content_sha256"] == hashlib.sha256(content).hexdigest()
    bundles = [c for c in index["raw"] if len(c["source_uris"]) == 2]
    assert len(bundles) == 5
    for bundle in bundles:
        primary, dependency = (nodes[key] for key in bundle["source_uris"])
        assert primary["language"] == dependency["language"]
        assert primary["name"] in {"run", "cpp::run", "Task"}
        assert dependency["name"] in {"helper", "cpp::helper", "Helper"}
        assert primary["source"] in bundle["text"] and dependency["source"] in bundle["text"]
        assert any(c["id"] == "atomic:" + primary["id"] for c in index["raw"])

    subprocess.run(command, check=True, capture_output=True)
    assert output.read_bytes() == first
    (tmp_path / "task.cpp").unlink()
    (tmp_path / "task.js").rename(tmp_path / "new.mjs")
    (tmp_path / "task.py").write_text("NEW_VALUE = 7")
    subprocess.run(command, check=True, capture_output=True)
    updated = json.loads(output.read_bytes())
    assert {n["path"] for n in updated["nodes"].values()} == {
        "task.py",
        "task.c",
        "Task.java",
        "new.mjs",
    }
    assert updated["manifest"]["task.py"] != index["manifest"]["task.py"]
    assert "memory://symbol/task.py::run" not in updated["nodes"]


def test_python_alias_decorator_and_depth(tmp_path: Path) -> None:
    """
    함수 이름: test_python_alias_decorator_and_depth()
    기능: 상대 import 별칭, UTF-8 데코레이터, 원문의 CRLF와 깊이 3 제한을 검증한다.
    인자: tmp_path -> 임시 패키지 루트
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    package = tmp_path / "pkg"
    package.mkdir()
    task = "from . import helpers as h\r\n@decorate('예제')\r\nasync def run():\r\n    return h.first()"
    (package / "task.py").write_bytes(task.encode())
    (package / "helpers.py").write_text(
        "FAR = 3\nLIMIT = FAR\ndef second(): return LIMIT\ndef first(): return second()\n"
    )
    index = build_index(tmp_path)
    uri = "memory://symbol/pkg/task.py::run"
    run = index["nodes"][uri]
    assert (run["start"], run["end"], run["kind"]) == (2, 4, "async_function")
    assert run["source"] == task.split("\r\n", 1)[1]
    assert "decorate" in run["unresolved_reference"]
    bundle = next(candidate for candidate in index["raw"] if candidate["id"] == uri)
    assert [index["nodes"][member]["name"] for member in bundle["source_uris"]] == [
        "run",
        "first",
        "second",
        "LIMIT",
    ]


def test_file_isolation(tmp_path: Path) -> None:
    """
    함수 이름: test_file_isolation()
    기능: 제외 폴더, 루트 밖 링크, 깨진 UTF-8, 크기 초과 파일과 정상 파일을 함께 처리한다.
    인자: tmp_path -> 임시 루트와 외부 파일의 부모
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "private.js"
    outside.write_text("export const SECRET = 123")
    (root / "ok.js").write_text("export const OK = 1")
    (root / "encoding.py").write_bytes(b"\xff")
    (root / "huge.c").write_bytes(b"a" * (1024 * 1024 + 1))
    ignored = root / "node_modules"
    ignored.mkdir()
    (ignored / "vendor.js").write_text("const VENDOR = 1")
    try:
        (root / "escape.js").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    index = build_index(root)
    assert set(index["nodes"]) == {"memory://symbol/ok.js::OK"}
    assert {d["relative_path"]: d["reason_code"] for d in index["diagnostics"]} == {
        "encoding.py": "encoding_error",
        "huge.c": "too_large",
        "escape.js": "path_rejected",
    }


def test_python_src_imports_respect_project_boundaries(tmp_path: Path) -> None:
    """
    함수 이름: test_python_src_imports_respect_project_boundaries()
    기능: src 모듈의 상대·절대 import가 형제 프로젝트의 동명 또는 유일한 심볼에 연결되지 않는지 확인한다.
    인자: tmp_path -> 임시 작업 공간
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    source = {
        "pyproject.toml": "",
        "src/pkg/shared.py": "LIMIT = 1\n",
        "src/pkg/caller.py": "from .shared import LIMIT\ndef primary(): return LIMIT\n",
        "tests/use.py": "from pkg.shared import LIMIT\ndef outside(): return LIMIT\n",
        "apps/other/src/pkg/shared.py": "LIMIT = 2\nOTHER = 3\n",
        "apps/other/src/pkg/use.py": (
            "import pkg.shared as sh\n"
            "from src.pkg.shared import OTHER\n"
            "def local(): return sh.LIMIT + OTHER\n"
        ),
        "src/pkg/missing.py": "from pkg.shared import OTHER\ndef missing(): return OTHER\n",
        "flat/setup.cfg": "",
        "flat/src/__init__.py": "",
        "flat/src/types.py": "FLAG = 1\n",
        "flat/check.py": (
            "from src.types import FLAG\nfrom types import FLAG as wrong\n"
            "def check(): return FLAG + wrong\n"
        ),
    }
    for name, text in source.items():
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
    nodes = build_index(tmp_path)["nodes"]
    prefix = "memory://symbol/"
    root_limit = prefix + "src/pkg/shared.py::LIMIT"
    assert nodes[prefix + "src/pkg/caller.py::primary"]["deps"] == [root_limit]
    assert nodes[prefix + "tests/use.py::outside"]["deps"] == [root_limit]
    assert nodes[prefix + "apps/other/src/pkg/use.py::local"]["deps"] == [
        prefix + "apps/other/src/pkg/shared.py::LIMIT",
        prefix + "apps/other/src/pkg/shared.py::OTHER",
    ]
    missing = nodes[prefix + "src/pkg/missing.py::missing"]
    assert missing["deps"] == []
    assert missing["unresolved_reference"] == ["OTHER"]
    flat = nodes[prefix + "flat/check.py::check"]
    assert flat["deps"] == [prefix + "flat/src/types.py::FLAG"]
    assert flat["unresolved_reference"] == ["wrong"]
