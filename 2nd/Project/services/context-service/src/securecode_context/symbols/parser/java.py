"""Java 최상위 타입의 원문과 정적으로 확인할 수 있는 타입 참조를 추출한다."""

from tree_sitter import Node

from .model import Declaration, Reference
from .syntax import node_text, walk

_TYPES = {
    "class_declaration",
    "enum_declaration",
    "interface_declaration",
    "annotation_type_declaration",
    "record_declaration",
}


def _qualified_name(statement: Node) -> str:
    """
    함수 이름: _qualified_name()
    기능: package/import 선언에서 주석과 공백을 제외하고 이름을 복원한다.
    인자: statement -> package 또는 import 선언 노드
    반환값: 점으로 구분한 이름
    작성 날짜: 2026/11/05
    """
    names = (
        part
        for part in statement.named_children
        if part.type in {"identifier", "scoped_identifier"}
    )
    return ".".join(
        node_text(node) for part in names for node in walk(part) if node.type == "identifier"
    )


def _java_references(
    declaration: Node, package: str, types: dict[str, str], members: dict[str, str]
) -> tuple[Reference, ...]:
    """
    함수 이름: _java_references()
    기능: 타입 사용, 정적 import 사용 및 수신자가 있는 메서드 호출을 구분한다.
    인자: declaration -> 타입 선언, package -> 패키지 이름, types/members -> 명시한 import
    반환값: 타입 키 또는 미해결 참조 목록
    작성 날짜: 2026/11/05
    """
    nodes = list(walk(declaration))
    bound: set[str] = set()
    for node in nodes:
        if node.type in _TYPES | {
            "variable_declarator",
            "formal_parameter",
            "catch_formal_parameter",
            "method_declaration",
            "type_parameter",
            "enhanced_for_statement",
        }:
            bound_name = node.child_by_field_name("name")
            if bound_name is None and node.type == "type_parameter" and node.named_children:
                bound_name = node.named_children[0]
            if bound_name:
                bound.add(node_text(bound_name))

    references: dict[str, tuple[str, ...]] = {}
    for node in nodes:
        name = node_text(node) if node.type in {"identifier", "type_identifier"} else ""
        parent = node.parent
        if parent is None:
            continue
        if node.type == "scoped_type_identifier":
            if parent.type != "scoped_type_identifier":
                qualified = node_text(node)
                references[qualified] = (f"java:{qualified}",)
            continue
        receiver = parent.child_by_field_name("object")
        if name and name not in bound and parent.type != "scoped_type_identifier":
            is_member = (
                receiver is not None
                and node != receiver
                and parent.type in {"method_invocation", "field_access"}
            )
            if name in members and not is_member:
                references[name] = (f"java:{members[name]}",) if members[name] else ()
            elif (
                node.type == "type_identifier"
                or (node == receiver and (name in types or name[0].isupper()))
                or (
                    parent.type in {"annotation", "marker_annotation"}
                    and parent.child_by_field_name("name") == node
                )
            ):
                qualified = types.get(name, f"{package}.{name}" if package else name)
                references[name] = (f"java:{qualified}",) if qualified else ()
        if node.type == "method_invocation":
            owner = node.child_by_field_name("object")
            method = node.child_by_field_name("name")
            if method and not owner:
                called = node_text(method)
                if called not in bound and called not in members:
                    references[called + "()"] = ()
            if owner and method:
                label = node_text(owner)
                if (
                    owner.type != "identifier"
                    or label in bound
                    or (label not in types and not label[0].isupper())
                ):
                    references[label + "." + node_text(method)] = ()
    return tuple(Reference(label, keys) for label, keys in sorted(references.items()))


def parse_java(path: str, source: bytes, root: Node) -> list[Declaration]:
    """
    함수 이름: parse_java()
    기능: Java 최상위 타입을 메서드·필드가 들어 있는 한 원문 단위로 만든다.
    인자: path -> 상대 경로, source -> 원문 바이트, root -> 검증한 Java 구문 트리
    반환값: 이름, 범위, 참조를 보존한 선언 목록
    작성 날짜: 2026/11/05
    """
    statements = root.named_children
    package = next(
        (_qualified_name(node) for node in statements if node.type == "package_declaration"), ""
    )
    types: dict[str, str] = {}
    members: dict[str, str] = {}
    imports = [node for node in statements if node.type == "import_declaration"]
    for statement in imports:
        if any(child.type == "asterisk" for child in statement.named_children):
            continue
        qualified = _qualified_name(statement)
        owner, _, name = qualified.rpartition(".")
        if any(child.type == "static" for child in statement.children):
            members[name] = owner if members.get(name, owner) == owner else ""
        else:
            types[name] = qualified if types.get(name, qualified) == qualified else ""

    result: list[Declaration] = []
    import_text = "\n".join(node_text(node) for node in imports)
    for statement in statements:
        name_node = statement.child_by_field_name("name")
        if statement.type not in _TYPES or name_node is None:
            continue
        name = node_text(name_node)
        qualified = f"{package}.{name}" if package else name
        result.append(
            Declaration(
                name,
                "class",
                statement.start_byte,
                statement.end_byte,
                statement.start_point.row + 1,
                statement.end_point.row + 1,
                (f"java:{qualified}",),
                _java_references(statement, package, types, members),
                import_text,
            )
        )
    return result
