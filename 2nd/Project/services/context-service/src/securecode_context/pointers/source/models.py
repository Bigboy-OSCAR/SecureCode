"""Source Pointer 등록부의 내부 레코드와 등록 요청 값 객체."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal

type Identity = tuple[int, int, int, int, int]
type TargetKind = Literal["file", "directory"]


class SourceLocation(StrEnum):
    """
    클래스 이름: SourceLocation
    기능: 등록 원본이 작업 공간 내부인지 사용자가 허용한 외부 경로인지 구분한다.
    작성 날짜: 2026/11/10
    """

    WORKSPACE = "workspace"
    EXTERNAL = "external"


class SourceStatus(StrEnum):
    """
    클래스 이름: SourceStatus
    기능: 등록 원본의 수명주기 상태(ready -> changed/missing -> 갱신 또는 해제)를 표현한다.
    작성 날짜: 2026/11/10
    """

    READY = "ready"
    CHANGED = "changed"
    MISSING = "missing"


@dataclass(frozen=True)
class SourceTarget:
    """
    클래스 이름: SourceTarget
    기능: SourceMutationRequest.target을 검증 전 그대로 담는다. 경로 문자열은 권한이 아니다.
    작성 날짜: 2026/11/10
    """

    location: SourceLocation
    kind: TargetKind
    path: str


@dataclass(frozen=True)
class ExternalGrant:
    """
    클래스 이름: ExternalGrant
    기능: 사용자가 명시한 외부 파일·디렉터리 허용 항목. workspace 범위에만 유효하다.
    작성 날짜: 2026/11/10
    """

    grant_id: str
    workspace_id: str
    real_root: Path
    file_name: str | None


@dataclass(frozen=True)
class SourceRecord:
    """
    클래스 이름: SourceRecord
    기능: 디스크 등록부 한 행. real path는 저장하지 않고 허용 root + 상대 경로로 매번 해석한다.
    작성 날짜: 2026/11/10
    """

    source_id: str
    workspace_id: str
    location: SourceLocation
    grant_id: str | None
    relative_path: PurePosixPath
    media_type: str
    byte_size: int
    fingerprint: str
    identity: Identity
    revision: int
    status: SourceStatus
    preview: str
    created_at: str
    updated_at: str

    @property
    def pointer(self) -> str:
        """
        함수 이름: pointer()
        기능: 현재 revision의 정식 Source Pointer URI를 만든다.
        인자: 없음
        반환값: securecode://source/<workspace_id>/<source_id>?v=<revision>
        작성 날짜: 2026/11/10
        """
        return f"securecode://source/{self.workspace_id}/{self.source_id}?v={self.revision}"


@dataclass(frozen=True)
class ResolvedSource:
    """
    클래스 이름: ResolvedSource
    기능: 4.6 부분 읽기·4.9 PDF가 쓰는 내부 해석 결과. 이것만으로 bounded read가 끝난 것은 아니다.
        호출자는 open_verified로 같은 root/상대 경로를 다시 열고 identity를 비교해야 한다.
    작성 날짜: 2026/11/10
    """

    record: SourceRecord
    root: Path
    real_path: Path


@dataclass(frozen=True)
class SourceIssue:
    """
    클래스 이름: SourceIssue
    기능: 디렉터리 등록에서 제외한 파일과 계약 오류 코드.
    작성 날짜: 2026/11/10
    """

    relative_path: str
    code: str


@dataclass(frozen=True)
class SourceMutation:
    """
    클래스 이름: SourceMutation
    기능: 등록·갱신 결과. issues가 있으면 partial이다.
    작성 날짜: 2026/11/10
    """

    workspace_id: str
    items: list[SourceRecord] = field(default_factory=list)
    issues: list[SourceIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        """
        함수 이름: status()
        기능: 계약 SourceMutationResult.status 값을 계산한다.
        인자: 없음
        반환값: completed 또는 partial
        작성 날짜: 2026/11/10
        """
        return "partial" if self.issues else "completed"


@dataclass(frozen=True)
class SourcePage:
    """
    클래스 이름: SourcePage
    기능: 목록 조회 한 페이지와 다음 cursor.
    작성 날짜: 2026/11/10
    """

    workspace_id: str
    items: list[SourceRecord]
    limit: int
    next_cursor: str | None
