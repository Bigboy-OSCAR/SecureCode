"""Symbol index가 Source Pointer 등록부(4.5/4.6)에 기대는 최소 포트와 대기용 fixture."""

from typing import Protocol


class SourceRegistryPort(Protocol):
    """
    클래스 이름: SourceRegistryPort
    기능: 심볼 출처 파일이 Source로 등록돼 있으면 정식 Source Pointer URI를 알려준다.
        symbols는 이 포트만 알고 pointers 패키지를 import하지 않아 순환 의존이 생기지 않는다.
    작성 날짜: 2026/11/05
    """

    def lookup(self, workspace_id: str, relative_path: str, content_sha256: str) -> str | None:
        """
        함수 이름: lookup()
        기능: 같은 작업 공간·경로·내용 해시로 등록된 Source의 포인터를 찾는다.
        인자: workspace_id -> 작업 공간, relative_path -> 상대 경로, content_sha256 -> 파일 해시
        반환값: securecode://source/... URI, 등록되지 않았거나 버전이 다르면 None
        작성 날짜: 2026/11/05
        """
        ...


class UnregisteredSourceRegistry:
    """
    클래스 이름: UnregisteredSourceRegistry
    기능: [fixture] 4.5/4.6 영속 등록부가 연결되기 전 기본값. 항상 미등록으로 답해
        SourceProvenance.pointer를 계약대로 null로 둔다. 실제 등록부 구현이 아니다.
    작성 날짜: 2026/11/05
    """

    def lookup(self, workspace_id: str, relative_path: str, content_sha256: str) -> str | None:
        """
        함수 이름: lookup()
        기능: 등록부가 없으므로 항상 미등록으로 답한다.
        인자: workspace_id -> 작업 공간, relative_path -> 상대 경로, content_sha256 -> 파일 해시
        반환값: None
        작성 날짜: 2026/11/05
        """
        return None
