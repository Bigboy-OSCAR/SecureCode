"""실제 C/C++ 구문 트리에서 선언·참조·원문 범위를 확인한다."""

from hashlib import sha256

import tree_sitter_c
import tree_sitter_cpp
from tree_sitter import Language, Parser

from securecode_context.symbols.graph import SourceGraph
from securecode_context.symbols.parser import parse_source
from securecode_context.symbols.parser.model import Declaration
from securecode_context.symbols.parser.native import parse_native


def declarations(path: str, source: str, *, cpp: bool = False) -> list[Declaration]:
    """
    함수 이름: declarations()
    기능: 실제 문법으로 작은 파일의 선언을 읽는다.
    인자: path -> 상대 경로, source -> 파일 내용, cpp -> C++ 문법 사용 여부
    반환값: 선언 목록
    작성 날짜: 2026/11/05
    """
    grammar = tree_sitter_cpp if cpp else tree_sitter_c
    content = source.encode()
    root = Parser(Language(grammar.language())).parse(content).root_node
    assert not root.has_error
    return parse_native(path, content, root)


def targets(decl: Declaration, name: str, options: list[Declaration]) -> list[Declaration]:
    """
    함수 이름: targets()
    기능: 참조의 정적 키를 모든 후보 선언 키와 대조한다.
    인자: decl -> 출발 선언, name -> 참조 이름, options -> 검사할 선언
    반환값: 정적 참조 대상 후보 목록
    작성 날짜: 2026/11/05
    """
    keys = {key for ref in decl.references if ref.name == name for key in ref.keys}
    return [candidate for candidate in options if keys.intersection(candidate.keys)]


def test_c_quoted_header_and_prototype_to_definition() -> None:
    """
    함수 이름: test_c_quoted_header_and_prototype_to_definition()
    기능: 헤더 경로·함수 원형·구현·상수의 참조와 조회 범위를 검사한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    header, prototype = declarations(
        "lib/math.h", "#ifndef MATH_H\n#define MATH_H\n#define BONUS 5\nint add(int);\n#endif\n"
    )
    (implementation,) = declarations(
        "lib/math.c", '#include "math.h"\nint add(int x){return x+BONUS;}'
    )
    (other,) = declarations("unrelated.c", "int add(int a){return a;}")
    (wrong_signature,) = declarations(
        "plugin.cpp", '#include "lib/math.h"\nint add(float a){return 0;}', cpp=True
    )
    (internal,) = declarations(
        "hidden.c", '#include "lib/math.h"\nstatic int add(int a){return 0;}'
    )
    (caller,) = declarations("sub/main.c", '#include "../lib/math.h"\nint run(){return add(0);}')
    graph = [header, prototype, implementation, other, wrong_signature, internal, caller]
    assert targets(caller, "add", graph) == [prototype]
    assert targets(prototype, "add", graph) == [implementation]
    assert targets(implementation, "BONUS", graph) == [header]
    assert prototype.imports == ""
    assert header.start_line == header.end_line == 3


def test_cpp_scopes_and_exact_spans() -> None:
    """
    함수 이름: test_cpp_scopes_and_exact_spans()
    기능: 템플릿 접두어·겹친 네임스페이스·한 줄 내 선언 경계·클래스 본문을 검사한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    source = (
        "// 문맥\r\nnamespace Outer::Inner { constexpr int LIMIT = 3;\n"
        "template<class T> T scale(T x) { return x * LIMIT; }\n"
        "class Box { int value; public: int get(){return value;} }; }\n"
        "int count(){return Outer::Inner::LIMIT;}\n"
    )
    limit, scale, box, count = declarations("lib.cpp", source, cpp=True)
    assert (limit.name, scale.name, box.name) == (
        "Outer::Inner::LIMIT",
        "Outer::Inner::scale",
        "Outer::Inner::Box",
    )
    assert (limit.kind, scale.kind, box.kind) == ("constant", "function", "class")
    assert targets(scale, "LIMIT", [limit, scale]) == [limit]
    assert targets(count, "Outer::Inner::LIMIT", [limit, scale]) == [limit]
    for declaration, original, line in (
        (limit, "constexpr int LIMIT = 3;", 2),
        (scale, "template<class T> T scale(T x) { return x * LIMIT; }", 3),
        (box, "class Box { int value; public: int get(){return value;} };", 4),
    ):
        assert source.encode()[declaration.start_byte : declaration.end_byte].decode() == original
        assert declaration.start_line == declaration.end_line == line


def test_local_names_and_runtime_dispatch() -> None:
    """
    함수 이름: test_local_names_and_runtime_dispatch()
    기능: 가려진 이름·객체 메서드·함수 포인터가 동명 외부 함수로 연결되지 않는지 검사한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    nodes = declarations(
        "main.cpp",
        "int go(){return 7;}\nconst int LIMIT = 2;\nint run(int LIMIT, int (*fp)(int), Obj obj)"
        '{const char *s="go()"; /* go() */ return obj.go()+fp(LIMIT);}',
        cpp=True,
    )
    run = nodes[-1]
    assert {ref.name for ref in run.references if not ref.keys} == {"obj.go", "fp"}
    assert not targets(run, "go", nodes)
    assert not targets(run, "LIMIT", nodes)


def test_cpp_inline_members_and_enum_values() -> None:
    """
    함수 이름: test_cpp_inline_members_and_enum_values()
    기능: 스코프가 명시된 인라인 메서드와 열거 참조가 소속 타입 원문을 가리키는지 확인한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    box, level, caller = declarations(
        "api.cpp",
        "struct Box { static int get(){return 1;} };\n"
        "enum class Level { Low=3, High=5 };\n"
        "int run(){return Box::get()+static_cast<int>(Level::High);}",
        cpp=True,
    )
    assert targets(caller, "Box::get", [box, level]) == [box]
    assert targets(caller, "Level::High", [box, level]) == [level]


def test_unknown_build_flags_and_inactive_branches() -> None:
    """
    함수 이름: test_unknown_build_flags_and_inactive_branches()
    기능: 비활성 분기와 미정인 빌드 설정에서 심볼·헤더·호출이 확정되는 일을 막는다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    file = declarations(
        "main.c",
        '#if 0\n#include "off.h"\nint skipped(){return 7;}\n#elif 1\n'
        "int enabled(){return 1;}\n#endif\n"
        '#ifdef FEATURE\n#include "feature.h"\nint optional(){return 1;}\n#endif\n'
        "int run(){\n#if 0\nreturn skipped();\n#endif\n#if FEATURE\nreturn enabled();\n#endif\n"
        "return optional()+from_header();\n}",
    )
    (from_header,) = declarations("feature.h", "int from_header(){return 0;}")
    enabled, optional, run = file
    assert not optional.keys and optional.name == "optional"
    assert not targets(run, "optional", file)
    assert not targets(run, "from_header", [from_header])
    assert not targets(run, "enabled", [enabled])
    assert {ref.name for ref in run.references if not ref.keys} == {"enabled"}
    assert run.imports == ""
    assert "skipped" not in {ref.name for ref in run.references}


def test_overload_and_c_header_language() -> None:
    """
    함수 이름: test_overload_and_c_header_language()
    기능: C 문법으로 유효한 .h와 C++ 오버로드 후보의 미해결 처리를 공통 그래프에서 검사한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/05
    """
    graph = SourceGraph()
    for path, content, expected_language in (
        ("common.h", b"int code(int);", "c"),
        ("over.h", b"namespace a {int pick(int); int pick(float);}", "cpp"),
        ("main.cpp", b'#include "over.h"\nint main(){return a::pick(1);}', "cpp"),
    ):
        language, records = parse_source(path, content)
        assert language == expected_language
        graph.add_file(path, language, content, sha256(content).hexdigest(), records)
    graph.link()
    caller = graph.nodes["memory://symbol/main.cpp::main"]
    assert caller["unresolved_reference"] == ["a::pick"]
    assert caller["deps"] == []
