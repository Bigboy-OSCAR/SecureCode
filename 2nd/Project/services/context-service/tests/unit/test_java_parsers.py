"""Java와 JavaScript의 실제 구문 트리에서 원문 범위와 정적 참조 경계를 확인한다."""

from pathlib import Path

import tree_sitter_java
import tree_sitter_javascript
from tree_sitter import Language, Parser

from securecode_context.symbols.index import build_index
from securecode_context.symbols.java import parse_java
from securecode_context.symbols.javascript import parse_javascript
from securecode_context.symbols.model import Declaration


def _parse_js(path: str, text: str) -> dict[str, Declaration]:
    """
    함수 이름: _parse_js()
    기능: JavaScript 예제를 실제 문법으로 파싱해 이름별 선언으로 돌려준다.
    인자: path -> 파일 경로, text -> 원문
    반환값: 선언 이름별 레코드
    작성 날짜: 2026/11/05
    """
    source = text.encode()
    root = Parser(Language(tree_sitter_javascript.language())).parse(source).root_node
    assert not root.has_error
    return {decl.name: decl for decl in parse_javascript(path, source, root)}


def test_java_packages_imports_and_type_ranges() -> None:
    """
    함수 이름: test_java_packages_imports_and_type_ranges()
    기능: 타입·메서드 원문 보존, 명시된 타입/정적 import와 동적 호출 구분을 검증한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    source = (
        "package sample;\n"
        "import project.util.Calculator;\n"
        "import static other.Limits.MAX;\n"
        "/* class Fake {} */\n"
        "@Deprecated\nrecord Holder(Worker worker) {\n"
        "  int size() { return Calculator.size() + MAX + worker.size(); }\n"
        '  String label() { return "class 가짜 {}"; }\n}\n'
        "interface Worker { int size(); }\n"
    ).encode()
    root = Parser(Language(tree_sitter_java.language())).parse(source).root_node
    holder, worker = parse_java("src/sample/Holder.java", source, root)
    assert [holder.name, worker.name] == ["Holder", "Worker"]
    assert (holder.start_line, holder.end_line, holder.kind) == (5, 9, "class")
    span = source[holder.start_byte : holder.end_byte].decode()
    assert span.startswith("@Deprecated\nrecord Holder") and span.endswith("\n}")
    refs = {ref.name: ref.keys for ref in holder.references}
    assert refs["Calculator"] == ("java:project.util.Calculator",)
    assert refs["MAX"] == ("java:other.Limits",)
    assert refs["Worker"] == worker.keys
    assert refs["worker.size"] == ()


def test_js_esm_bindings_exports_and_scoped_references() -> None:
    """
    함수 이름: test_js_esm_bindings_exports_and_scoped_references()
    기능: ESM 별칭·default·namespace만 파일 간 참조가 되고 가려진 이름은 연결되지 않는지 검사한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    module = _parse_js(
        "lib/util.mjs",
        "export { magic as limit }; const magic = 9; export default function read() {}",
    )
    source = (
        "// function decoy() {}\n"
        "import load, {limit as LIMIT} from '../lib/util.mjs';\n"
        "import * as ns from '../lib/util.mjs';\n"
        "export const Run = async () => {\n  return <View>{load() + LIMIT + ns.limit}</View>;\n};\n"
        "class Panel { run() { return Run(); } }\n"
        "function shadow({load}) { return load() }\n"
    )
    nodes = _parse_js("ui/view.jsx", source)
    assert set(nodes) == {"Run", "Panel", "shadow"}
    run = nodes["Run"]
    assert (run.start_line, run.end_line, run.kind) == (4, 6, "async_function")
    assert source.encode()[run.start_byte : run.end_byte].decode() == "\n".join(
        source.splitlines()[3:6]
    )
    refs = {ref.name: ref.keys for ref in run.references}
    assert set(refs["load"]) & set(module["read"].keys)
    assert set(refs["LIMIT"]) & set(module["magic"].keys)
    assert refs["ns.limit"] == refs["LIMIT"]
    assert set(nodes["Panel"].references[0].keys) & set(run.keys)
    assert not any(set(ref.keys) & set(module["read"].keys) for ref in nodes["shadow"].references)
    assert "js:export:lib/util.mjs:magic" not in module["magic"].keys


def test_commonjs_relative_literals_only() -> None:
    """
    함수 이름: test_commonjs_relative_literals_only()
    기능: require 구조 분해와 명시한 export를 연결하고 외부 패키지나 경로 이탈은 제외한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    library = _parse_js("util/index.cjs", "exports.compute = v => v * 2;")
    app = _parse_js(
        "src/app.cjs",
        "const { compute: run } = require('../util');\n"
        "const external = require('other'); const escaped = require('../../../outside');\n"
        "module.exports = function main(x) { return run(x) + external.test() + escaped.test(); };",
    )
    refs = {ref.name: ref.keys for ref in app["default"].references}
    assert set(refs["run"]) & set(library["compute"].keys)
    assert refs["external.test"] == ()
    assert refs["escaped.test"] == ()


def test_literal_require_member_alias_and_direct_call(tmp_path: Path) -> None:
    """
    함수 이름: test_literal_require_member_alias_and_direct_call()
    기능: 리터럴 require의 정적 속성을 호출하거나 별칭으로 쓰는 경우와 동적 인자를 구분한다.
    인자: tmp_path -> 임시 프로젝트 경로
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    (tmp_path / "lib.cjs").write_text("exports.size = (v) => v.length;")
    (tmp_path / "user.cjs").write_text(
        'const measure = require("./lib.cjs").size;\n'
        'exports.work = v => measure(v) + require(/* local */ "./lib.cjs").size(v);\n'
        "exports.dynamic = path => require(path).size();\n"
        'function shadow(require) { return require("./lib.cjs").size(); }'
    )
    (tmp_path / "shadow.cjs").write_text(
        "function require(name) { return {}; }\n"
        'const {size} = require("./lib.cjs");\nexports.work = () => size();'
    )
    nodes = build_index(tmp_path)["nodes"]
    size = "memory://symbol/lib.cjs::size"
    assert nodes["memory://symbol/user.cjs::measure"]["deps"] == [size]
    assert set(nodes["memory://symbol/user.cjs::work"]["deps"]) == {
        size,
        "memory://symbol/user.cjs::measure",
    }
    dynamic = nodes["memory://symbol/user.cjs::dynamic"]
    assert not dynamic["deps"] and "require().size" in dynamic["unresolved_reference"]
    assert not nodes["memory://symbol/user.cjs::shadow"]["deps"]
    assert not nodes["memory://symbol/shadow.cjs::work"]["deps"]
