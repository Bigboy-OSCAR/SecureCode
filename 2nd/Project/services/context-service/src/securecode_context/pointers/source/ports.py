"""Source 등록부가 기대는 외부 포트와 등록 issue 코드."""

from pathlib import Path
from typing import Protocol

from securecode_context.common.errors import ErrorCode, ServiceError

ISSUE_CODES = frozenset(
    code.value
    for code in (
        ErrorCode.FORBIDDEN,
        ErrorCode.NOT_FOUND,
        ErrorCode.SOURCE_CHANGED,
        ErrorCode.PAYLOAD_TOO_LARGE,
        ErrorCode.UNSUPPORTED_FORMAT,
    )
)


class SourceRootPort(Protocol):
    """
    클래스 이름: SourceRootPort
    기능: 작업 공간 ID를 서버 내부 root로 바꾼다. 3.6이 host 작업 공간 등록부를 연결한다.
        symbols의 WorkspaceRootPort와 같은 모양이라 같은 구현을 쓸 수 있다.
    작성 날짜: 2026/11/10
    """

    def root_for(self, workspace_id: str) -> Path:
        """
        함수 이름: root_for()
        기능: 등록된 작업 공간 root를 돌려준다. 모르면 NOT_FOUND를 던진다.
        인자: workspace_id -> 작업 공간
        반환값: 절대 경로
        작성 날짜: 2026/11/10
        """
        ...


class UnconnectedWorkspaceRoots:
    """
    클래스 이름: UnconnectedWorkspaceRoots
    기능: host 작업 공간 등록부(3.6)가 연결되기 전 기본값. 모든 workspace를 모른다고 답해
        내부 경로 추측 없이 실패하게 한다. fixture가 아니라 fail-closed 기본값이다.
    작성 날짜: 2026/11/10
    """

    def root_for(self, workspace_id: str) -> Path:
        """
        함수 이름: root_for()
        기능: 항상 NOT_FOUND를 던진다.
        인자: workspace_id -> 작업 공간
        반환값: 없음(항상 예외)
        작성 날짜: 2026/11/10
        """
        raise ServiceError(
            ErrorCode.NOT_FOUND,
            "작업 공간이 연결되지 않았습니다.",
            {"reason": "workspace_root_unconnected"},
        )
