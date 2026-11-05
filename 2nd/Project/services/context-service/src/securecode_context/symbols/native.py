"""C 및 C++ 구문 트리를 R0 원문 선언과 한정된 정적 참조로 변환한다."""

import posixpath
from collections.abc import Iterator

from tree_sitter import Node

from .model import Declaration, Reference
from .native_refs import declared_name, name_key, name_node, references_for
from .native_tree import top_level
from .syntax import node_text, walk

_AGGREGATES = {"struct_specifier", "union_specifier", "enum_specifier", "class_specifier"}


def function_prototype(declarator: Node) -> bool:
    """
    함수 이름: function_prototype()
    기능: 함수 반환 타입의 포인터와 함수 포인터 변수를 구분한다.
    인자: declarator -> 선언자
    반환값: 함수 원형 여부
    작성 날짜: 2026/11/05
    """
    part: Node | None = declarator
    while part is not None:
        inner = part.child_by_field_name("declarator")
        if part.type == "function_declarator":
            return inner is not None and inner.type != "parenthesized_declarator"
        part = inner or (part.named_child(0) if part.type == "reference_declarator" else None)
    return False


def parameter_signature(node: Node, name: str) -> str:
    """
    함수 이름: parameter_signature()
    기능: 매개변수명과 공백을 제외한 인자 구문으로 원형과 정의의 일치를 확인한다.
    인자: node -> 함수 선언 또는 정의, name -> 함수명
    반환값: 매개변수 타입 토큰의 키
    작성 날짜: 2026/11/05
    """
    for declarator in node.children_by_field_name("declarator"):
        if declared_name(declarator) != name:
            continue
        for part in walk(declarator):
            if part.type != "function_declarator" or not (
                params := part.child_by_field_name("parameters")
            ):
                continue
            ignored = {
                named.id
                for param in params.named_children
                if (named := name_node(param.child_by_field_name("declarator")))
            }
            stack, tokens = [params], []
            while stack:
                token = stack.pop()
                if token.id in ignored or token.type == "comment":
                    continue
                if token.child_count:
                    stack.extend(reversed(token.children))
                else:
                    tokens.append(node_text(token))
            return " ".join(tokens)
    return ""


def named_declarations(node: Node) -> Iterator[tuple[str, str]]:
    """
    함수 이름: named_declarations()
    기능: 한 선언의 함수·자료형·파일 상수 이름을 추출한다.
    인자: node -> 선언 노드
    반환값: 심볼 이름과 종류
    작성 날짜: 2026/11/05
    """
    if node.type in _AGGREGATES:
        if node.child_by_field_name("body") and (name := node.child_by_field_name("name")):
            yield node_text(name), "class"
    elif node.type == "alias_declaration":
        if name := node.child_by_field_name("name"):
            yield node_text(name), "class"
    elif node.type == "type_definition":
        for item in node.children_by_field_name("declarator"):
            yield declared_name(item), "class"
    elif node.type == "function_definition":
        yield declared_name(node.child_by_field_name("declarator")), "function"
    elif node.type == "preproc_def" and node.child_by_field_name("value"):
        if name := node.child_by_field_name("name"):
            yield node_text(name), "constant"
    elif node.type == "declaration":
        if (aggregate := node.child_by_field_name("type")) and aggregate.type in _AGGREGATES:
            yield from named_declarations(aggregate)
        has_const = any(
            child.type == "type_qualifier" and node_text(child) in {"const", "constexpr"}
            for child in node.named_children
        )
        for item in node.children_by_field_name("declarator"):
            if function_prototype(item):
                yield declared_name(item), "function"
            elif has_const:
                yield declared_name(item), "constant"


def quoted_paths(path: str, includes: list[Node]) -> tuple[str, ...]:
    """
    함수 이름: quoted_paths()
    기능: 직접 지정된 로컬 헤더만 프로젝트 상대 경로로 정규화한다.
    인자: path -> 현재 파일 상대 경로, includes -> include 노드 목록
    반환값: 조회 가능한 헤더 경로
    작성 날짜: 2026/11/05
    """
    paths: set[str] = set()
    for include in includes:
        target = include.child_by_field_name("path")
        if target is None or target.type != "string_literal":
            continue
        relative = posixpath.normpath(
            posixpath.join(posixpath.dirname(path), node_text(target)[1:-1])
        )
        if not relative.startswith(("/", "../")) and relative != "..":
            paths.add(relative)
    return tuple(sorted(paths))


def aggregate_names(node: Node, qualname: str) -> Iterator[str]:
    """
    함수 이름: aggregate_names()
    기능: 타입 안에 정의된 멤버·열거 상수를 같은 타입 원문에서 조회할 키로 만든다.
    인자: node -> 타입 선언, qualname -> 한정된 타입 이름
    반환값: 멤버의 한정된 이름
    작성 날짜: 2026/11/05
    """
    if node.type not in _AGGREGATES:
        aggregate = node.child_by_field_name("type")
        if aggregate is None or aggregate.type not in _AGGREGATES:
            return
        node = aggregate
    body = node.child_by_field_name("body")
    if body is None:
        return
    scope = qualname.rpartition("::")[0]
    scoped_enum = any(child.type in {"class", "struct"} for child in node.children)
    for member in body.named_children:
        if member.type == "enumerator" and (name := member.child_by_field_name("name")):
            yield f"{qualname}::{node_text(name)}"
            if not scoped_enum:
                yield "::".join(filter(None, (scope, node_text(name))))
        if member.type in {"function_definition", "field_declaration"}:
            for item in member.children_by_field_name("declarator"):
                if member.type == "field_declaration" and function_prototype(item):
                    continue
                if field := declared_name(item):
                    yield f"{qualname}::{field}"


def internal_function(node: Node) -> bool:
    """
    함수 이름: internal_function()
    기능: static 함수와 익명 네임스페이스 함수의 정의를 파일 안으로 제한한다.
    인자: node -> 함수 선언 또는 정의
    반환값: 내부 연결 여부
    작성 날짜: 2026/11/05
    """
    if any(
        child.type == "storage_class_specifier" and node_text(child) == "static"
        for child in node.named_children
    ):
        return True
    parent = node.parent
    while parent:
        if parent.type == "namespace_definition" and parent.child_by_field_name("name") is None:
            return True
        parent = parent.parent
    return False


def parse_native(path: str, source: bytes, root: Node) -> list[Declaration]:
    """
    함수 이름: parse_native()
    기능: C/C++ 선언 범위, 직접 인용 헤더와 한정된 이름 참조를 보존한다.
    인자: path -> 프로젝트 상대 경로, source -> UTF-8 원문, root -> 구문 트리
    반환값: 추출한 선언 목록
    작성 날짜: 2026/11/05
    """
    entries = list(top_level(root))
    includes = [
        node
        for scope, node, _, conditional in entries
        if not scope and not conditional and node.type == "preproc_include"
    ]
    headers = quoted_paths(path, includes)
    imports = "\n".join(node_text(node).rstrip("\r\n") for node in includes)
    definitions = {
        (scope, name, parameter_signature(node, name))
        for scope, node, _, conditional in entries
        if not conditional and node.type == "function_definition"
        for name, _ in named_declarations(node)
    }
    declarations: list[Declaration] = []
    for scope, node, outer, conditional in entries:
        for name, kind in named_declarations(node):
            if not name:
                continue
            qualname = "::".join(filter(None, (scope, name)))
            keys = [name_key(path, qualname)]
            references = references_for(outer, name, qualname.rpartition("::")[0], (path, *headers))
            if kind == "class":
                keys.extend(name_key(path, member) for member in aggregate_names(node, qualname))
            if kind == "function":
                signature = parameter_signature(node, name)
                typed_name = f"{qualname}{signature}"
                if node.type == "declaration" and (scope, name, signature) in definitions:
                    continue
                internal = internal_function(node)
                if node.type == "declaration" and not internal:
                    references.append(
                        Reference(name, (name_key(path, typed_name, implementation=True),))
                    )
                elif node.type == "function_definition" and not internal:
                    keys.extend(
                        name_key(header, typed_name, implementation=True) for header in headers
                    )
            end_node = outer
            if outer.type in _AGGREGATES | {"template_declaration"}:
                following = outer.next_sibling
                if following and following.type == ";":
                    end_node = following
            end_byte = end_node.end_byte
            while end_byte > outer.start_byte and source[end_byte - 1] in (10, 13):
                end_byte -= 1
            end_line = end_node.end_point.row + (end_node.end_point.column != 0)
            declarations.append(
                Declaration(
                    qualname,
                    kind,
                    outer.start_byte,
                    end_byte,
                    outer.start_point.row + 1,
                    end_line,
                    () if conditional else tuple(keys),
                    tuple(references),
                    imports,
                )
            )
    return declarations
