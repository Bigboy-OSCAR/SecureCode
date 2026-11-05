"""JavaScript의 최상위 선언과 명시적으로 연결할 수 있는 모듈 참조를 색인한다."""

from collections.abc import Iterator

from tree_sitter import Node

from .javascript_modules import ModuleBindings, assigned_export, collect_bindings, export_keys
from .model import Declaration, Reference
from .syntax import node_text, walk

_VARIABLES = {"lexical_declaration", "variable_declaration"}
_FUNCTIONS = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "generator_function_declaration",
    "generator_function",
}
_CLASSES = {"class_declaration", "class"}


def _kind(value: Node) -> str:
    """
    함수 이름: _kind()
    기능: 실제 초기값의 구문을 기준으로 기존 R0 계약의 심볼 종류를 고른다.
    인자: value -> 선언 또는 초기값
    반환값: 계약의 종류 문자열
    작성 날짜: 2026/11/05
    """
    if value.type in _FUNCTIONS:
        return (
            "async_function"
            if any(child.type == "async" for child in value.children)
            else "function"
        )
    return "class" if value.type in _CLASSES else "constant"


def _pattern_names(pattern: Node) -> Iterator[str]:
    """
    함수 이름: _pattern_names()
    기능: 바인딩 패턴에서 실제 선언 이름만 읽고 기본값과 속성 키는 건너뛴다.
    인자: pattern -> 단일 이름, 구조 분해 또는 매개변수 목록
    반환값: 바인딩 이름의 반복자
    작성 날짜: 2026/11/05
    """
    pending = [pattern]
    while pending:
        part = pending.pop()
        if part.type in {"identifier", "shorthand_property_identifier_pattern"}:
            yield node_text(part)
        elif part.type in {"assignment_pattern", "object_assignment_pattern", "pair_pattern"}:
            field = "value" if part.type == "pair_pattern" else "left"
            name = part.child_by_field_name(field)
            if name:
                pending.append(name)
        else:
            pending.extend(part.named_children)


def _bound_names(root: Node) -> set[str]:
    """
    함수 이름: _bound_names()
    기능: 내부 선언과 매개변수가 가리는 이름을 제외해 외부 심볼과의 오연결을 피한다.
    인자: root -> 심볼 원문 노드
    반환값: 참조 키로 사용하지 않을 내부 이름
    작성 날짜: 2026/11/05
    """
    blocked: set[str] = set()
    for node in walk(root):
        fields: tuple[str, ...]
        if node.type in _FUNCTIONS | _CLASSES:
            fields = ("name", "parameter", "parameters")
        elif node.type in {"method_definition", "catch_clause"}:
            fields = ("parameter", "parameters")
        elif node.type == "variable_declarator":
            fields = ("name",)
        elif node.type == "for_in_statement" and node.child_by_field_name("kind"):
            fields = ("left",)
        else:
            continue
        for field in fields:
            pattern = node.child_by_field_name(field)
            if pattern:
                blocked.update(_pattern_names(pattern))
    return blocked


def _references(path: str, value: Node, bindings: ModuleBindings) -> tuple[Reference, ...]:
    """
    함수 이름: _references()
    기능: 로컬 식별자와 명시한 import를 연결하고 동적 멤버 호출은 미해결로 남긴다.
    인자: path -> 상대 경로, value -> 선언 본문, bindings -> 파일의 import 목록
    반환값: 선언에서 사용한 참조와 정확한 대상 키 후보
    작성 날짜: 2026/11/05
    """
    blocked = _bound_names(value)
    references: dict[str, tuple[str, ...]] = {}
    for node in walk(value):
        if node.type == "import" and node.parent and node.parent.type == "call_expression":
            references["import()"] = ()
        if node.type not in {"identifier", "shorthand_property_identifier"}:
            continue
        name = node_text(node)
        parent = node.parent
        prop = None
        if (
            parent
            and parent.type == "member_expression"
            and node == parent.child_by_field_name("object")
        ):
            prop = parent.child_by_field_name("property")
        if name in blocked:
            if prop:
                references[name + "." + node_text(prop)] = ()
            elif (
                parent
                and parent.type == "call_expression"
                and node == parent.child_by_field_name("function")
            ):
                references[name + "()"] = ()
            continue
        if name in bindings.imported:
            module, public = bindings.imported[name]
            if public in {"*", "require:*"} and prop:
                member = node_text(prop)
                references[f"{name}.{member}"] = export_keys(path, module, member)
            elif public == "*" or (
                public == "require:*" and parent and parent.type == "subscript_expression"
            ):
                references[name] = ()
            elif public == "require:*":
                references[name] = export_keys(path, module, "default")
            else:
                references[name] = export_keys(path, module, public)
        else:
            references[name] = (f"js:local:{path}:{name}",)
            if prop:
                references[name + "." + node_text(prop)] = ()
    return tuple(Reference(label, keys) for label, keys in sorted(references.items()))


def _entries(statement: Node) -> Iterator[tuple[str, Node, Node, str]]:
    """
    함수 이름: _entries()
    기능: 한 문장을 바인딩 이름, 분석할 값, 반환할 원문 범위, 직접 공개 이름으로 분해한다.
    인자: statement -> 최상위 문장
    반환값: 선언 정보의 반복자
    작성 날짜: 2026/11/05
    """
    decl = statement
    public = ""
    if statement.type == "export_statement":
        candidate = statement.child_by_field_name("declaration") or statement.child_by_field_name(
            "value"
        )
        if candidate is None or candidate.type == "identifier":
            return
        decl = candidate
        public = "default" if any(part.type == "default" for part in statement.children) else "*"
    elif assigned := assigned_export(statement):
        public, value = assigned
        if value.type != "identifier":
            yield public, value, statement, public
        return

    if decl.type in _VARIABLES:
        declarators = [
            child for child in decl.named_children if child.type == "variable_declarator"
        ]
        for declarator in declarators:
            name = declarator.child_by_field_name("name")
            if not name or name.type != "identifier":
                continue
            value = declarator.child_by_field_name("value") or declarator
            span = statement if len(declarators) == 1 else declarator
            yield node_text(name), value, span, public
    elif decl.type in _FUNCTIONS | _CLASSES or public == "default":
        name = decl.child_by_field_name("name")
        yield node_text(name) if name else "default", decl, statement, public


def parse_javascript(path: str, source: bytes, root: Node) -> list[Declaration]:
    """
    함수 이름: parse_javascript()
    기능: 원문을 실행하지 않고 최상위 선언, 함수형 변수 및 클래스 본문을 가져온다.
    인자: path -> 상대 경로, source -> 원문 바이트, root -> 검증한 JavaScript 구문 트리
    반환값: 위치, 원문, 파일과 export 범위의 참조 정보를 담은 선언 목록
    작성 날짜: 2026/11/05
    """
    bindings = collect_bindings(root)
    imports = "\n".join(bindings.statements)
    result: list[Declaration] = []
    for statement in root.named_children:
        for name, value, span, public in _entries(statement):
            exports = set(bindings.exported.get(name, ()))
            if public:
                exports.add(name if public == "*" else public)
            keys = [f"js:export:{path}:{alias}" for alias in sorted(exports)]
            if statement.type != "expression_statement":
                keys.append(f"js:local:{path}:{name}")
            result.append(
                Declaration(
                    name,
                    _kind(value),
                    span.start_byte,
                    span.end_byte,
                    span.start_point.row + 1,
                    span.end_point.row + 1,
                    tuple(keys),
                    _references(path, value, bindings),
                    imports,
                )
            )
    return result
