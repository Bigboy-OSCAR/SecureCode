"""트리 순회와 선언 원문 읽기에 쓰는 구문 도구."""

from collections.abc import Iterator

from tree_sitter import Node


def walk(node: Node) -> Iterator[Node]:
    """
    함수 이름: walk()
    기능: 주어진 노드와 이름 있는 자손을 소스 순서로 방문한다.
    인자: node -> 시작 노드
    반환값: 노드 반복자
    작성 날짜: 2026/11/05
    """
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.named_children))


def node_text(node: Node) -> str:
    """
    함수 이름: node_text()
    기능: 바이트 원본에서 파싱한 노드의 텍스트를 읽는다.
    인자: node -> UTF-8 소스의 노드
    반환값: 원문 문자열
    작성 날짜: 2026/11/05
    """
    assert node.text is not None
    return node.text.decode("utf-8")
