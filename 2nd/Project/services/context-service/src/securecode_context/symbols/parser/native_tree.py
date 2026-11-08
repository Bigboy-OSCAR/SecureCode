"""빌드 설정을 실행하지 않고 C 계열 전처리 분기의 가시성을 구분한다."""

from collections.abc import Iterator

from tree_sitter import Node

from .syntax import node_text

_CONDITIONS = {"preproc_ifdef", "preproc_if", "preproc_elif", "preproc_elifdef"}


def _branch_value(node: Node) -> bool | None:
    """
    함수 이름: _branch_value()
    기능: 문자 그대로 0·1인 조건과 파일 맨 바깥 헤더 가드를 인식한다.
    인자: node -> 전처리 조건
    반환값: 분기 선택 여부 또는 빌드 설정이 필요한 경우 None
    작성 날짜: 2026/11/05
    """
    condition = node.child_by_field_name("condition")
    if condition and node_text(condition) in {"0", "1"}:
        return node_text(condition) == "1"
    parent = node.parent
    if not parent or parent.type != "translation_unit" or node.children[0].type != "#ifndef":
        return None
    if node.child_by_field_name("alternative") is not None:
        return None
    name = node.child_by_field_name("name")
    directives = [
        child for child in node.named_children if child != name and child.type != "comment"
    ]
    if name and directives and directives[0].type == "preproc_def":
        defined = directives[0].child_by_field_name("name")
        if defined and node_text(defined) == node_text(name):
            return True
    return None


def branch_children(node: Node) -> list[tuple[Node, bool]]:
    """
    함수 이름: branch_children()
    기능: 가능한 분기의 자식과 해당 분기가 빌드 설정에 의존하는지 반환한다.
    인자: node -> 구문 노드
    반환값: 자식과 조건부 여부의 목록
    작성 날짜: 2026/11/05
    """
    if node.type not in _CONDITIONS:
        return [(child, False) for child in node.named_children]
    enabled = _branch_value(node)
    condition = node.child_by_field_name("condition") or node.child_by_field_name("name")
    alternative = node.child_by_field_name("alternative")
    return [
        (child, enabled is None)
        for child in node.named_children
        if child != condition and (enabled is None or enabled == (child != alternative))
    ]


def top_level(root: Node) -> Iterator[tuple[str, Node, Node, bool]]:
    """
    함수 이름: top_level()
    기능: 네임스페이스·조건부 전처리·템플릿을 통과하되 함수·클래스 본문은 건너뛴다.
    인자: root -> 파일 구문 트리
    반환값: 네임스페이스, 선언 노드, 원문 범위 노드, 조건부 여부
    작성 날짜: 2026/11/05
    """
    pending: list[tuple[str, Node, Node | None, bool]] = [("", root, None, False)]
    while pending:
        scope, node, outer, conditional = pending.pop()
        if node.type in _CONDITIONS | {"translation_unit", "declaration_list", "preproc_else"}:
            pending.extend(
                (scope, child, outer, conditional or unknown)
                for child, unknown in reversed(branch_children(node))
            )
        elif node.type in {"namespace_definition", "linkage_specification"}:
            if node.type == "namespace_definition" and (name := node.child_by_field_name("name")):
                scope = "::".join(filter(None, (scope, node_text(name))))
            if body := node.child_by_field_name("body"):
                pending.append((scope, body, None, conditional))
        elif node.type == "template_declaration":
            pending.extend(
                (scope, child, outer or node, conditional)
                for child in reversed(node.named_children)
            )
        else:
            yield scope, node, outer or node, conditional
