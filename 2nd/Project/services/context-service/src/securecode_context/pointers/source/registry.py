"""Source Pointer 디스크 등록부: 등록·갱신·stat·resolve·목록·등록 해제와 provenance 조회 포트."""

from pathlib import Path
from threading import RLock
from types import TracebackType
from typing import Self

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source.derived import DerivedCachePort, check_cache_key
from securecode_context.pointers.source.lifecycle import SourceLifecycle
from securecode_context.pointers.source.models import (
    ResolvedSource,
    SourceIssue,
    SourceLocation,
    SourceMutation,
    SourcePage,
    SourceRecord,
    SourceTarget,
)
from securecode_context.pointers.source.paths import check_inside, forbidden
from securecode_context.pointers.source.ports import ISSUE_CODES, SourceRootPort
from securecode_context.pointers.source.registration import RegistrationPlanner
from securecode_context.pointers.source.registry_db import SourceDb
from securecode_context.pointers.source.uri import (
    check_workspace_id,
    decode_cursor,
    encode_cursor,
    parse_source_uri,
)


class SourceRegistry:
    """
    클래스 이름: SourceRegistry
    기능: workspace 범위 Source 등록부. 경로는 매번 허용 root에서 다시 해석하고, 원본은 지우지 않는다.
    작성 날짜: 2026/11/10
    """

    def __init__(
        self,
        db_path: Path,
        roots: SourceRootPort,
        cache: DerivedCachePort | None = None,
        forbidden_roots: tuple[Path, ...] = (),
    ) -> None:
        """
        함수 이름: __init__()
        기능: SQLite 등록부를 열고 root 포트·파생 캐시·서비스 소유 경로를 보관한다.
        인자: db_path -> 등록부 파일, roots -> workspace root 포트,
            cache -> 파생 캐시 삭제 포트, forbidden_roots -> 외부 등록을 막을 서비스 폴더
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._db = SourceDb(db_path)
        self._roots = roots
        owned = (db_path.parent, *forbidden_roots)
        self._lock = RLock()
        self._life = SourceLifecycle(self._db, self._lock, cache)
        self._planner = RegistrationPlanner(
            self._db, self._lock, self._workspace_root, tuple(path.resolve() for path in owned)
        )

    def __enter__(self) -> Self:
        """
        함수 이름: __enter__()
        기능: with 문에서 등록부를 사용한다.
        인자: 없음
        반환값: 자기 자신
        작성 날짜: 2026/11/10
        """
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """
        함수 이름: __exit__()
        기능: with 문이 끝나면 DB 연결을 닫는다.
        인자: kind/error/trace -> 예외 정보
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.close()

    def close(self) -> None:
        """
        함수 이름: close()
        기능: SQLite 연결을 닫는다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._db.close()

    def register(self, workspace_id: str, target: SourceTarget) -> SourceMutation:
        """
        함수 이름: register()
        기능: 파일 하나 또는 디렉터리 아래 파일을 등록한다. 같은 원본은 같은 등록을 재사용한다.
        인자: workspace_id -> 인증된 범위, target -> 요청 대상
        반환값: SourceMutation(디렉터리는 파일별 issue 포함)
        작성 날짜: 2026/11/10
        """
        check_workspace_id(workspace_id)
        plan = self._planner.plan(workspace_id, target)
        result = SourceMutation(workspace_id, issues=list(plan.issues))
        for relative in plan.files:
            try:
                result.items.append(
                    self._life.save(workspace_id, plan.location, plan.grant_id, plan.root, relative)
                )
            except ServiceError as error:
                if not plan.is_directory or error.code.value not in ISSUE_CODES:
                    self._planner.release_grant(plan.grant_id)
                    raise
                shown = relative.relative_to(plan.prefix).as_posix()
                result.issues.append(SourceIssue(shown, error.code.value))
        if not result.items:
            self._planner.release_grant(plan.grant_id)
        return result

    def refresh(self, workspace_id: str, pointer: str) -> SourceRecord:
        """
        함수 이름: refresh()
        기능: 권한을 다시 확인하고 원본이 바뀌었으면 revision을 올린다. 이전 revision 포인터는 무효다.
        인자: workspace_id -> 범위, pointer -> 어느 revision이든 같은 등록의 URI
        반환값: 현재 SourceRecord
        작성 날짜: 2026/11/10
        """
        record = self._get(workspace_id, pointer)
        root = self._root_of(record)
        return self._life.save(
            workspace_id, record.location, record.grant_id, root, record.relative_path
        )

    def stat(self, workspace_id: str, pointer: str) -> SourceRecord:
        """
        함수 이름: stat()
        기능: 범위·revision·경로·내용을 확인한다. identity가 같으면 재해시하지 않는다.
        인자: workspace_id -> 범위, pointer -> 현재 revision URI
        반환값: 변경되지 않은 SourceRecord
        작성 날짜: 2026/11/10
        """
        return self.resolve(workspace_id, pointer).record

    def resolve(self, workspace_id: str, pointer: str) -> ResolvedSource:
        """
        함수 이름: resolve()
        기능: 4.6/4.9 포트. 검증한 레코드와 허용 root·실제 경로를 돌려준다. 읽기 전후 재확인은 호출자 몫이다.
        인자: workspace_id -> 범위, pointer -> 현재 revision URI
        반환값: ResolvedSource
        작성 날짜: 2026/11/10
        """
        uri = parse_source_uri(pointer, workspace_id)
        record = self._get(workspace_id, pointer)
        if uri.revision != record.revision:
            raise ServiceError(
                ErrorCode.SOURCE_CHANGED,
                "원본이 갱신됐습니다. 새 포인터로 다시 읽으세요.",
                {"current_revision": record.revision},
            )
        root = self._root_of(record)
        record = self._life.verify(record, root)
        return ResolvedSource(record, root, check_inside(root, record.relative_path))

    def list_sources(
        self, workspace_id: str, limit: int = 20, cursor: str | None = None
    ) -> SourcePage:
        """
        함수 이름: list_sources()
        기능: 등록 메타데이터를 source_id 순서로 최대 100개씩 돌려준다. 원본은 읽지 않는다.
        인자: workspace_id -> 범위, limit -> 1~100, cursor -> 이전 페이지 cursor
        반환값: SourcePage
        작성 날짜: 2026/11/10
        """
        check_workspace_id(workspace_id)
        if not 1 <= limit <= 100:
            raise ServiceError(ErrorCode.VALIDATION_FAILED, "limit은 1~100입니다.")
        after = decode_cursor(cursor, workspace_id)
        with self._lock:
            rows = self._db.page(workspace_id, after, limit + 1)
        items = rows[:limit]
        next_cursor = (
            encode_cursor(workspace_id, items[-1].source_id) if len(rows) > limit else None
        )
        return SourcePage(workspace_id, items, limit, next_cursor)

    def unregister(self, workspace_id: str, pointer: str) -> None:
        """
        함수 이름: unregister()
        기능: 등록·파생 캐시 참조·쓰지 않는 외부 허용을 지운다. 원본 파일은 보존한다. 없어도 같은 결과다.
        인자: workspace_id -> 범위, pointer -> 어느 revision이든 같은 등록의 URI
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        uri = parse_source_uri(pointer, workspace_id)
        with self._lock, self._db.transaction():
            record = self._db.get(workspace_id, uri.source_id)
            if record is None:
                return
            self._db.delete(workspace_id, uri.source_id)
            released = self._db.links.release_refs(uri.source_id)
            if record.grant_id is not None:
                self._db.links.drop_unused_grant(record.grant_id)
        self._life.delete_caches(released)

    def attach_derived(self, workspace_id: str, pointer: str, cache_key: str) -> None:
        """
        함수 이름: attach_derived()
        기능: 현재 revision의 파생 캐시 참조를 기록한다. revision이 바뀌거나 해제되면 참조가 풀린다.
        인자: workspace_id -> 범위, pointer -> 현재 URI, cache_key -> 캐시 키
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        check_cache_key(cache_key)
        record = self.stat(workspace_id, pointer)
        with self._lock:
            self._db.links.add_ref(record.source_id, cache_key)

    def lookup(self, workspace_id: str, relative_path: str, content_sha256: str) -> str | None:
        """
        함수 이름: lookup()
        기능: symbols SourceRegistryPort. 같은 경로·내용의 ready 등록이 있으면 URI를 돌려준다.
        인자: workspace_id -> 범위, relative_path -> 작업 공간 상대 경로, content_sha256 -> 내용 해시
        반환값: Source Pointer URI 또는 None
        작성 날짜: 2026/11/10
        """
        with self._lock:
            record = self._db.find_fingerprint(workspace_id, relative_path, content_sha256)
        return record.pointer if record else None

    def _workspace_root(self, workspace_id: str) -> Path:
        """
        함수 이름: _workspace_root()
        기능: root 포트의 작업 공간 root를 실제 경로로 확인한다.
        인자: workspace_id -> 범위
        반환값: 실제 root
        작성 날짜: 2026/11/10
        """
        root = self._roots.root_for(workspace_id)
        if root.is_symlink() or root.is_junction():
            raise forbidden("workspace_root_is_link")
        try:
            return root.resolve(strict=True)
        except OSError as error:
            raise ServiceError(ErrorCode.NOT_FOUND, "작업 공간 root가 없습니다.") from error

    def _root_of(self, record: SourceRecord) -> Path:
        """
        함수 이름: _root_of()
        기능: 재시작 뒤에도 매번 workspace root 또는 외부 허용 항목을 다시 확인한다.
        인자: record -> 등록 레코드
        반환값: 실제 허용 root
        작성 날짜: 2026/11/10
        """
        if record.location is SourceLocation.WORKSPACE:
            return self._workspace_root(record.workspace_id)
        grant = self._db.links.grant(record.workspace_id, record.grant_id or "")
        if grant is None:
            raise forbidden("external_grant_missing")
        if grant.file_name is not None and record.relative_path.as_posix() != grant.file_name:
            raise forbidden("outside_external_grant")
        return self._planner.verify_grant_root(grant.real_root)

    def _get(self, workspace_id: str, pointer: str) -> SourceRecord:
        """
        함수 이름: _get()
        기능: URI를 검사하고 같은 workspace의 등록 행을 읽는다.
        인자: workspace_id -> 범위, pointer -> URI
        반환값: SourceRecord
        작성 날짜: 2026/11/10
        """
        uri = parse_source_uri(pointer, workspace_id)
        with self._lock:
            record = self._db.get(workspace_id, uri.source_id)
        if record is None:
            raise ServiceError(ErrorCode.NOT_FOUND, "등록된 원본을 찾을 수 없습니다.")
        return record
