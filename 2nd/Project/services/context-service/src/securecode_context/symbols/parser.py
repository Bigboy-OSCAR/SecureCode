"""확장자와 구문 트리에 따라 원문 선언 파서를 선택한다."""

from pathlib import PurePosixPath

import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_java
import tree_sitter_javascript
from tree_sitter import Language, Parser

from .java import parse_java
from .javascript import parse_javascript
from .model import Declaration
from .native import parse_native
from .python_parser import parse_python
from .syntax import walk

EXTENSIONS = {
    ".py": "python",
    ".c": "c",
    ".h": "c",
    ".C": "cpp",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
}
_GRAMMARS = {
    "c": Language(tree_sitter_c.language()),
    "cpp": Language(tree_sitter_cpp.language()),
    "java": Language(tree_sitter_java.language()),
    "javascript": Language(tree_sitter_javascript.language()),
}
# Both grammars accept some C++ headers. C can mistake `class X {}` for a function body.
_CPP_HEADER_MARKERS = {
    "namespace_definition",
    "namespace_alias_definition",
    "class_specifier",
    "access_specifier",
    "template_declaration",
    "template_instantiation",
    "qualified_identifier",
    "alias_declaration",
    "using_declaration",
    "linkage_specification",
    "base_class_clause",
    "reference_declarator",
    "operator_name",
    "destructor_name",
    "lambda_expression",
    "concept_definition",
}
_EXTRACT = {
    "c": parse_native,
    "cpp": parse_native,
    "java": parse_java,
    "javascript": parse_javascript,
}


def parse_source(path: str, source: bytes) -> tuple[str, list[Declaration]]:
    """
    함수 이름: parse_source()
    기능: 지원 파일 하나를 파싱한다. .h는 두 문법으로 검사하고 공통 문법은 C로 처리한다.
    인자: path -> 상대 경로, source -> 파일 원문
    반환값: 실제 사용한 언어와 선언 목록
    작성 날짜: 2026/11/05
    """
    suffix = PurePosixPath(path).suffix
    language = EXTENSIONS[suffix]
    if language == "python":
        return language, parse_python(path, source)
    source.decode("utf-8")
    root = Parser(_GRAMMARS[language]).parse(source).root_node
    if suffix == ".h":
        cpp_root = Parser(_GRAMMARS["cpp"]).parse(source).root_node
        if not cpp_root.has_error and (
            root.has_error or any(node.type in _CPP_HEADER_MARKERS for node in walk(cpp_root))
        ):
            language, root = "cpp", cpp_root
    if root.has_error:
        bad = root
        # Missing punctuation may be an anonymous child rather than a named syntax node.
        while child := next((n for n in bad.children if n.has_error or n.is_missing), None):
            bad = child
        error = SyntaxError("invalid source")
        error.lineno = bad.start_point.row + 1
        raise error
    return language, _EXTRACT[language](path, source, root)
