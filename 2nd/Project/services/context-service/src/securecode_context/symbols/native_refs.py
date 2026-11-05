"""C/C++ 선언자와 한 선언 안에서 보이는 참조를 읽는다."""

from tree_sitter import Node

from .model import Reference
from .native_tree import branch_children
from .syntax import node_text, walk

_NAME_TYPES = {
    "identifier",
    "type_identifier",
    "field_identifier",
    "qualified_identifier",
    "operator_name",
    "destructor_name",
}


def name_node(declarator: Node | None) -> Node | None:
    """
    함수 이름: name_node()
    기능: 포인터·배열·함수 선언자를 따라 이름을 찾는다.
    인자: declarator -> 선언자 노드
    반환값: 이름의 구문 노드 또는 None
    작성 날짜: 2026/11/05
    """
    while declarator is not None:
        if declarator.type in _NAME_TYPES:
            return declarator
        child = declarator.child_by_field_name("declarator")
        if child is None and declarator.type in {
            "parenthesized_declarator",
            "reference_declarator",
        }:
            child = declarator.named_child(0)
        declarator = child
    return None


def declared_name(declarator: Node | None) -> str:
    """
    함수 이름: declared_name()
    기능: 선언자의 식별자 문자열을 읽는다.
    인자: declarator -> 선언자 노드
    반환값: 선언 이름 또는 빈 문자열
    작성 날짜: 2026/11/05
    """
    return node_text(node) if (node := name_node(declarator)) else ""


def name_key(path: str, name: str, *, implementation: bool = False) -> str:
    """
    함수 이름: name_key()
    기능: 파일 경로로 한정한 C 계열 심볼 키를 만든다.
    인자: path -> 상대 경로, name -> 정규 이름, implementation -> 헤더 원형의 구현 키 여부
    반환값: 참조 해석용 키
    작성 날짜: 2026/11/05
    """
    category = "definition" if implementation else "name"
    return f"native:{category}:{path}\0{name}"


def reference_names(node: Node, self_name: str) -> tuple[set[str], set[str]]:
    """
    함수 이름: reference_names()
    기능: 지역 선언을 제외하고 참조 이름과 정적으로 결정할 수 없는 멤버 접근을 구분한다.
    인자: node -> 심볼 선언 전체, self_name -> 심볼 이름
    반환값: 정적 이름과 동적 표현식 집합
    작성 날짜: 2026/11/05
    """
    if node.type == "preproc_def":
        value = node.child_by_field_name("value")
        alias = node_text(value).strip() if value else ""
        return ({alias} if alias.isidentifier() else set()), set()
    local = {self_name, self_name.split("::")[-1]}
    for part in walk(node):
        if part.type in {
            "parameter_declaration",
            "optional_parameter_declaration",
            "declaration",
            "field_declaration",
            "function_definition",
            "type_definition",
        }:
            local.update(declared_name(item) for item in part.children_by_field_name("declarator"))
        if part.type == "enumerator" and (name := part.child_by_field_name("name")):
            local.add(node_text(name))
        if part.type == "type_parameter_declaration":
            local.update(node_text(child) for child in part.named_children)

    names, dynamic = set[str](), set[str]()
    stack = [(node, False)]
    while stack:
        part, conditional = stack.pop()
        if part.type in {"identifier", "type_identifier", "qualified_identifier"}:
            label = node_text(part)
            if label not in local:
                (dynamic if conditional else names).add(label)
            continue
        if part.type == "call_expression":
            target = part.child_by_field_name("function")
            if target is not None and (
                target.type
                in {"pointer_expression", "parenthesized_expression", "subscript_expression"}
                or (target.type == "identifier" and node_text(target) in local - {self_name})
            ):
                dynamic.add(node_text(target))
        if part.type == "field_expression":
            dynamic.add(node_text(part))
            if owner := part.child_by_field_name("argument"):
                stack.append((owner, conditional))
        elif part.type not in {"preproc_def", "preproc_function_def", "attribute_specifier"}:
            stack.extend(
                (child, conditional or unknown) for child, unknown in branch_children(part)
            )
    return names, dynamic


def references_for(
    node: Node, self_name: str, scope: str, visible: tuple[str, ...]
) -> list[Reference]:
    """
    함수 이름: references_for()
    기능: 이름과 네임스페이스, 인용 include 경로로 정적 참조 후보를 한정한다.
    인자: node -> 선언, self_name -> 선언 이름, scope -> 네임스페이스, visible -> 조회 가능한 파일
    반환값: 참조 후보
    작성 날짜: 2026/11/05
    """
    names, dynamic = reference_names(node, self_name)
    scopes = scope.split("::") if scope else []
    references = [Reference(name, ()) for name in sorted(dynamic)]
    for name in sorted(names):
        if name.startswith("::"):
            candidates = [name[2:]]
        else:
            candidates = ["::".join([*scopes[:i], name]) for i in range(len(scopes), -1, -1)]
        keys = tuple(name_key(path, candidate) for candidate in candidates for path in visible)
        references.append(Reference(name, keys))
    return references
