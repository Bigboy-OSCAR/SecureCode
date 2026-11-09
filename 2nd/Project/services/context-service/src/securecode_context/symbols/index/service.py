"""작업 공간별 색인 빌드·상태·현재 revision 제공을 조립한다(SymbolService.build_index 단계)."""

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from securecode_context.common.errors import ErrorCode, ServiceError

from ..graph import IndexCapacityError
from ..retrieval import PreparedRetrieval, prepare_retrieval
from .changes import ManifestChanges, has_changes, revision_changes
from .freshness import probe_changes
from .ports import SourceRegistryPort, UnregisteredSourceRegistry
from .records import IndexRevisionRecord, RetrievalInfo, build_record
from .revision_store import RevisionStore, RevisionStoreError
from .roots import RootPolicy
from .scanner import scan_workspace
from .status import BuildState, status_payload
from .verification import VerifiedSymbol, verify_symbols


def _utc_now() -> str:
    """
    함수 이름: _utc_now()
    기능: RFC 3339 UTC 시각 문자열을 만든다.
    인자: 없음
    반환값: 예) 2026-11-05T09:00:00Z
    작성 날짜: 2026/11/05
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class SymbolIndexService:
    """
    클래스 이름: SymbolIndexService
    기능: 새 revision의 원문·그래프·TF-IDF 벡터를 모두 준비한 뒤에만 ready로 원자적으로 전환하고,
        이전 revision 요청은 거부한다. 벡터는 서버 메모리에만 두고 재시작 뒤 같은 후보로 다시 만든다.
    작성 날짜: 2026/11/05
    """

    def __init__(
        self,
        store: RevisionStore,
        source_registry: SourceRegistryPort | None = None,
        root_policy: RootPolicy | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        """
        함수 이름: __init__()
        기능: 저장소·Source 등록부 포트·루트 정책·시계를 주입받는다.
        인자: store -> RevisionStore, source_registry -> 미지정 시 미등록 fixture,
            root_policy -> 루트 허용 정책, clock -> 시각 함수
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.store = store
        self.source_registry = source_registry or UnregisteredSourceRegistry()
        self.root_policy = root_policy or RootPolicy()
        self._clock = clock
        self._guard = Lock()
        self._locks: dict[str, Lock] = {}
        self._builds: dict[str, BuildState] = {}
        self._cache: dict[str, IndexRevisionRecord] = {}
        self._prepared: dict[str, PreparedRetrieval] = {}

    def build(self, workspace_id: str, root: Path) -> dict[str, Any]:
        """
        함수 이름: build()
        기능: 작업 공간 전체를 다시 스캔해 새 revision을 게시한다. 진행 중이면 그 상태를 돌려준다.
            실패하면 이전 revision을 그대로 제공하고 failed 상태만 기록한다.
        인자: workspace_id -> 작업 공간, root -> 등록된 루트
        반환값: IndexStatusResponse JSON 값
        작성 날짜: 2026/11/05
        """
        resolved = self.root_policy.resolve(root)
        lock = self._workspace_lock(workspace_id)
        if not lock.acquire(blocking=False):
            return status_payload(
                workspace_id,
                self._current_or_none(workspace_id),
                self._builds.get(workspace_id),
                stale=False,
            )
        try:
            return self._build_locked(workspace_id, resolved)
        finally:
            lock.release()

    def status(self, workspace_id: str, root: Path) -> dict[str, Any]:
        """
        함수 이름: status()
        기능: 현재 revision의 집계와 디스크 변경(stale) 여부를 돌려준다. 원문은 포함하지 않는다.
        인자: workspace_id -> 작업 공간, root -> 등록된 루트
        반환값: IndexStatusResponse JSON 값
        작성 날짜: 2026/11/05
        """
        resolved = self.root_policy.resolve(root)
        record = self._current_or_none(workspace_id)
        build = self._builds.get(workspace_id)
        stale = False
        if record is not None and (build is None or build.completed_at is not None):
            stale = has_changes(self._probe(record, resolved))
        return status_payload(workspace_id, record, build, stale)

    def current(self, workspace_id: str) -> IndexRevisionRecord:
        """
        함수 이름: current()
        기능: 검색 준비(3.4)에 쓸 현재 revision 기록을 돌려준다.
        인자: workspace_id -> 작업 공간
        반환값: IndexRevisionRecord
        작성 날짜: 2026/11/05
        """
        record = self._current_or_none(workspace_id)
        if record is None:
            raise ServiceError(ErrorCode.INDEX_NOT_READY, "아직 색인이 없습니다.")
        return record

    def require_revision(self, workspace_id: str, index_revision: int) -> IndexRevisionRecord:
        """
        함수 이름: require_revision()
        기능: 요청 revision이 현재 revision과 같을 때만 기록을 돌려준다.
        인자: workspace_id -> 작업 공간, index_revision -> 후보·묶음 요청의 revision
        반환값: IndexRevisionRecord
        작성 날짜: 2026/11/05
        """
        record = self.current(workspace_id)
        if record["index_revision"] != index_revision:
            raise ServiceError(
                ErrorCode.SOURCE_CHANGED,
                "색인이 새 버전으로 바뀌었습니다. 다시 검색하세요.",
                {"reason": "index_revision_superseded", "index_revision": record["index_revision"]},
            )
        return record

    def prepared(self, workspace_id: str) -> tuple[IndexRevisionRecord, PreparedRetrieval | None]:
        """
        함수 이름: prepared()
        기능: 현재 revision과 그 TF-IDF 준비 결과를 돌려준다. ready가 아니면 준비 결과는 None이다.
        인자: workspace_id -> 작업 공간
        반환값: (현재 revision 기록, PreparedRetrieval 또는 None)
        작성 날짜: 2026/11/05
        """
        record = self.current(workspace_id)
        if record["retrieval"]["state"] != "ready":
            return record, None
        with self._guard:
            cached = self._prepared.get(workspace_id)
        if cached is not None and cached.index_revision == record["index_revision"]:
            return record, cached
        prepared = prepare_retrieval(record["index_revision"], record["nodes"], record["raw"])
        with self._guard:
            self._prepared[workspace_id] = prepared
        return record, prepared

    def verified_symbols(
        self, workspace_id: str, root: Path, index_revision: int, symbol_ids: Iterable[str]
    ) -> dict[str, VerifiedSymbol | None]:
        """
        함수 이름: verified_symbols()
        기능: 원문을 내보내기 직전에 revision을 확인하고 파일마다 한 번 디스크 해시를 다시 비교한다.
        인자: workspace_id -> 작업 공간, root -> 등록된 루트, index_revision -> 요청 revision,
            symbol_ids -> memory://symbol/... 심볼 ID
        반환값: 심볼별 VerifiedSymbol, 색인 뒤 바뀐 파일이면 None
        작성 날짜: 2026/11/05
        """
        record = self.require_revision(workspace_id, index_revision)
        wanted = list(symbol_ids)
        if any(uri not in record["nodes"] for uri in wanted):
            raise ServiceError(ErrorCode.NOT_FOUND, "심볼을 찾을 수 없습니다.")
        resolved = self.root_policy.resolve(root)
        verified = verify_symbols(
            workspace_id, index_revision, resolved, record["nodes"], wanted, self.source_registry
        )
        self.require_revision(workspace_id, index_revision)
        return verified

    def verified_symbol(
        self, workspace_id: str, root: Path, index_revision: int, symbol_id: str
    ) -> VerifiedSymbol:
        """
        함수 이름: verified_symbol()
        기능: 심볼 하나를 검증한다. 파일이 바뀌었으면 원문 대신 SOURCE_CHANGED를 던진다.
        인자: workspace_id -> 작업 공간, root -> 등록된 루트, index_revision -> 요청 revision,
            symbol_id -> memory://symbol/... 심볼 ID
        반환값: VerifiedSymbol
        작성 날짜: 2026/11/05
        """
        verified = self.verified_symbols(workspace_id, root, index_revision, [symbol_id])
        result = verified[symbol_id]
        if result is None:
            raise ServiceError(
                ErrorCode.SOURCE_CHANGED,
                "원본 파일이 색인 이후 바뀌었습니다. 다시 색인하세요.",
                {"reason": "content_changed", "index_revision": index_revision},
            )
        return result

    def _build_locked(self, workspace_id: str, root: Path) -> dict[str, Any]:
        """
        함수 이름: _build_locked()
        기능: 잠금을 잡은 상태에서 스캔·차이 계산·벡터 준비·게시를 수행한다. 벡터 준비가
            끝나기 전에는 게시하지 않으므로 parsed 상태의 revision이 검색에 노출되지 않는다.
        인자: workspace_id -> 작업 공간, root -> 검사한 실제 루트
        반환값: IndexStatusResponse JSON 값
        작성 날짜: 2026/11/05
        """
        previous = self._current_or_none(workspace_id)
        revision = self.store.next_revision(workspace_id)
        started_at = self._clock()
        self._builds[workspace_id] = BuildState(revision, started_at)
        try:
            scan = scan_workspace(root, excluded=self._excluded())
            old_manifest = previous["manifest"] if previous else {}
            changes = revision_changes(
                old_manifest,
                previous["nodes"] if previous else {},
                previous["raw"] if previous else [],
                scan.index["manifest"],
            )
            parent = previous["index_revision"] if previous else None
            record = build_record(workspace_id, revision, parent, self._clock(), scan, changes)
            prepared = prepare_retrieval(revision, record["nodes"], record["raw"])
            record["retrieval"] = RetrievalInfo(
                state="ready",
                owner_task="3.4",
                candidate_count=len(prepared.infos),
                vocabulary_size=prepared.retriever.vocabulary_size,
            )
            self.store.publish(record)
        except (IndexCapacityError, OSError, RevisionStoreError, ValueError) as error:
            code = "QUOTA_EXCEEDED" if isinstance(error, IndexCapacityError) else "INTERNAL_ERROR"
            self._builds[workspace_id] = BuildState(None, started_at, self._clock(), code)
            return status_payload(workspace_id, previous, self._builds[workspace_id], stale=False)
        with self._guard:
            self._cache[workspace_id] = record
            self._prepared[workspace_id] = prepared
        del self._builds[workspace_id]
        return status_payload(workspace_id, record, None, stale=False)

    def _current_or_none(self, workspace_id: str) -> IndexRevisionRecord | None:
        """
        함수 이름: _current_or_none()
        기능: current.json이 가리키는 revision을 캐시 또는 디스크에서 읽는다.
        인자: workspace_id -> 작업 공간
        반환값: 현재 revision 기록, 없으면 None
        작성 날짜: 2026/11/05
        """
        revision = self.store.current_revision(workspace_id)
        if revision is None:
            return None
        with self._guard:
            cached = self._cache.get(workspace_id)
        if cached is not None and cached["index_revision"] == revision:
            return cached
        record = self.store.load(workspace_id, revision)
        with self._guard:
            self._cache[workspace_id] = record
        return record

    def _probe(self, record: IndexRevisionRecord, root: Path) -> ManifestChanges:
        """
        함수 이름: _probe()
        기능: 저장 위치를 제외하고 디스크와 revision manifest를 비교한다.
        인자: record -> 현재 revision, root -> 실제 루트
        반환값: ManifestChanges
        작성 날짜: 2026/11/05
        """
        return probe_changes(root, record["manifest"], record["file_stats"], self._excluded())

    def _excluded(self) -> frozenset[Path]:
        """
        함수 이름: _excluded()
        기능: 작업 공간 안에 저장소가 있어도 자기 자신을 색인하지 않게 한다.
        인자: 없음
        반환값: 탐색 제외 경로 집합
        작성 날짜: 2026/11/05
        """
        return frozenset({self.store.base_dir})

    def _workspace_lock(self, workspace_id: str) -> Lock:
        """
        함수 이름: _workspace_lock()
        기능: 작업 공간마다 빌드 잠금 하나를 만든다(ID 형식은 저장소가 검사).
        인자: workspace_id -> 작업 공간
        반환값: Lock
        작성 날짜: 2026/11/05
        """
        self.store.symbols_dir(workspace_id)
        with self._guard:
            return self._locks.setdefault(workspace_id, Lock())
