"""SymbolService 포트(3.4 구현: symbol_service.R0SymbolService)와 작업 공간 루트 포트.
요청·응답 모양은 contracts/symbols/symbol.schema.json을 따른다."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from securecode_context.common.errors import ErrorCode, ServiceError


class SymbolService(Protocol):
    """
    클래스 이름: SymbolService
    기능: R0 TF-IDF 후보 검색과 예산 안 Symbol Bundle 읽기. LLM 선택·요약·임베딩을 쓰지 않는다.
    작성 날짜: 2026/11/04
    """

    def search(self, request: Mapping[str, object]) -> Mapping[str, object]:
        """
        함수 이름: search()
        기능: SymbolSearchRequest를 받아 SymbolSearchResponse를 돌려준다(무결과는 no_match로 표시).
        인자: request -> 검증된 SymbolSearchRequest
        반환값: SymbolSearchResponse
        작성 날짜: 2026/11/04
        """
        ...

    def read_bundle(self, request: Mapping[str, object]) -> Mapping[str, object]:
        """
        함수 이름: read_bundle()
        기능: SymbolBundleRequest의 후보를 예산 안 원문 fragment로 돌려준다.
        인자: request -> 검증된 SymbolBundleRequest
        반환값: SymbolBundle
        작성 날짜: 2026/11/04
        """
        ...


class WorkspaceRootPort(Protocol):
    """
    클래스 이름: WorkspaceRootPort
    기능: 작업 공간 ID를 서버 내부의 등록 루트로 바꾼다. 실제 등록부는 3.5가 연결한다.
    작성 날짜: 2026/11/05
    """

    def root_for(self, workspace_id: str) -> Path:
        """
        함수 이름: root_for()
        기능: 등록된 작업 공간 루트를 돌려준다. 모르는 ID는 NOT_FOUND를 던진다.
        인자: workspace_id -> 작업 공간
        반환값: 절대 경로(API 응답에 넣지 않는다)
        작성 날짜: 2026/11/05
        """
        ...


class StaticWorkspaceRoots:
    """
    클래스 이름: StaticWorkspaceRoots
    기능: [fixture] 3.5 작업 공간 등록부 전까지 CLI·시험이 쓰는 고정 ID→루트 표.
    작성 날짜: 2026/11/05
    """

    def __init__(self, roots: Mapping[str, Path]) -> None:
        """
        함수 이름: __init__()
        기능: ID별 루트 표를 복사해 보관한다.
        인자: roots -> 작업 공간 ID와 루트
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.roots = dict(roots)

    def root_for(self, workspace_id: str) -> Path:
        """
        함수 이름: root_for()
        기능: 표에서 루트를 찾는다.
        인자: workspace_id -> 작업 공간
        반환값: 루트 경로
        작성 날짜: 2026/11/05
        """
        root = self.roots.get(workspace_id)
        if root is None:
            raise ServiceError(ErrorCode.NOT_FOUND, "작업 공간을 찾을 수 없습니다.")
        return root
