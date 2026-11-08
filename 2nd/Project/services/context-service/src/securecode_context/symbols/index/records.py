"""디스크에 저장하는 symbol index revision 기록의 모양을 정의한다."""

from collections import Counter
from typing import Literal, NotRequired, TypedDict

from ..graph import RawCandidate, SourceNode
from .changes import RevisionChanges
from .scanner import Diagnostic, ScanResult

RECORD_FORMAT_VERSION = 1
# TF-IDF 벡터 준비가 끝난 revision만 ready로 게시한다. pending은 이전 형식·준비 전 기록이다.
type RetrievalState = Literal["pending", "ready"]
_FAILED_REASONS = frozenset({"syntax_error", "encoding_error", "path_rejected"})


class IndexCounts(TypedDict):
    """
    클래스 이름: IndexCounts
    기능: IndexStatusResponse.counts와 같은 파일 수 집계를 보관한다.
    작성 날짜: 2026/11/05
    """

    discovered: int
    indexed: int
    skipped: int
    failed: int


class RetrievalInfo(TypedDict):
    """
    클래스 이름: RetrievalInfo
    기능: 검색 준비 상태와 책임 작업, 준비한 후보·어휘 수를 기록한다.
    작성 날짜: 2026/11/05
    """

    state: RetrievalState
    owner_task: str
    candidate_count: NotRequired[int]
    vocabulary_size: NotRequired[int]


class IndexRevisionRecord(TypedDict):
    """
    클래스 이름: IndexRevisionRecord
    기능: 한 작업 공간의 불변 revision. 원문·그래프·후보는 서버 안에서만 쓰고 API로 보내지 않는다.
    작성 날짜: 2026/11/05
    """

    format_version: int
    workspace_id: str
    index_revision: int
    parent_revision: int | None
    created_at: str
    retrieval: RetrievalInfo
    languages: list[str]
    counts: IndexCounts
    manifest: dict[str, str]
    file_stats: dict[str, list[int]]
    file_languages: dict[str, str]
    diagnostics: list[Diagnostic]
    changes: RevisionChanges
    nodes: dict[str, SourceNode]
    raw: list[RawCandidate]


def count_files(scan: ScanResult) -> IndexCounts:
    """
    함수 이름: count_files()
    기능: 진단 사유를 실패(구문·인코딩·경로)와 건너뜀(미지원 언어·크기)으로 나눠 센다.
    인자: scan -> 스캔 결과
    반환값: IndexCounts
    작성 날짜: 2026/11/05
    """
    reasons = Counter(item["reason_code"] for item in scan.index["diagnostics"])
    failed = sum(count for reason, count in reasons.items() if reason in _FAILED_REASONS)
    skipped = sum(reasons.values()) - failed
    return IndexCounts(
        discovered=scan.discovered,
        indexed=len(scan.file_languages),
        skipped=skipped,
        failed=failed,
    )


def build_record(
    workspace_id: str,
    index_revision: int,
    parent_revision: int | None,
    created_at: str,
    scan: ScanResult,
    changes: RevisionChanges,
) -> IndexRevisionRecord:
    """
    함수 이름: build_record()
    기능: 스캔 결과 전체를 새 revision 기록 하나로 묶는다. 이전 revision 자료를 섞지 않는다.
    인자: workspace_id -> 작업 공간, index_revision -> 새 번호, parent_revision -> 이전 번호,
        created_at -> RFC 3339 시각, scan -> 스캔 결과, changes -> 이전 revision과의 차이
    반환값: IndexRevisionRecord
    작성 날짜: 2026/11/05
    """
    index = scan.index
    return IndexRevisionRecord(
        format_version=RECORD_FORMAT_VERSION,
        workspace_id=workspace_id,
        index_revision=index_revision,
        parent_revision=parent_revision,
        created_at=created_at,
        retrieval=RetrievalInfo(state="pending", owner_task="3.4"),
        languages=sorted(set(scan.file_languages.values())),
        counts=count_files(scan),
        manifest=index["manifest"],
        file_stats={path: list(info) for path, info in scan.file_stats.items()},
        file_languages=scan.file_languages,
        diagnostics=index["diagnostics"],
        changes=changes,
        nodes=index["nodes"],
        raw=index["raw"],
    )
