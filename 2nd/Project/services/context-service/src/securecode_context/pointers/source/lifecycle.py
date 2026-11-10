"""등록 레코드의 저장·revision 갱신·변경 확인(ready → changed/missing) 규칙."""

import dataclasses
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from threading import RLock

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source import media
from securecode_context.pointers.source.derived import DerivedCachePort
from securecode_context.pointers.source.models import (
    Identity,
    SourceLocation,
    SourceRecord,
    SourceStatus,
)
from securecode_context.pointers.source.paths import hash_stable, identity_of, open_verified
from securecode_context.pointers.source.registry_db import SourceDb, path_key


@dataclasses.dataclass(frozen=True)
class _Scan:
    """
    클래스 이름: _Scan
    기능: 열린 원본 한 번에서 얻은 identity·hash·형식·미리보기.
    작성 날짜: 2026/11/10
    """

    identity: Identity
    fingerprint: str
    media_type: str
    byte_size: int
    preview: str


def now_utc() -> str:
    """
    함수 이름: now_utc()
    기능: 계약 Timestamp(UTC RFC 3339) 문자열을 만든다.
    인자: 없음
    반환값: 현재 시각
    작성 날짜: 2026/11/10
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scan(root: Path, relative: PurePosixPath) -> _Scan:
    """
    함수 이름: _scan()
    기능: 원본을 검증해 열고 형식을 판별한 뒤 형식별 상한 안에서 전체 hash를 계산한다.
    인자: root -> 실제 허용 root, relative -> 상대 경로
    반환값: _Scan
    작성 날짜: 2026/11/10
    """
    with open_verified(root, relative) as file:
        media_type = media.detect_media(relative.name, file.read(8192))
        fingerprint, head = hash_stable(file, media.size_limit(media_type))
        identity = identity_of(file)
    preview = media.preview_of(media_type, head)
    return _Scan(identity, fingerprint, media_type, identity[2], preview)


class SourceLifecycle:
    """
    클래스 이름: SourceLifecycle
    기능: 원본 검사 결과를 등록부와 비교해 revision·상태·파생 캐시 참조를 맞춘다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, db: SourceDb, lock: RLock, cache: DerivedCachePort | None) -> None:
        """
        함수 이름: __init__()
        기능: 등록부 DB·잠금·파생 캐시 포트를 보관한다.
        인자: db -> SourceDb, lock -> 등록부 잠금, cache -> 파생 캐시 삭제 포트
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._db = db
        self._lock = lock
        self._cache = cache

    def save(
        self,
        workspace_id: str,
        location: SourceLocation,
        grant_id: str | None,
        root: Path,
        relative: PurePosixPath,
    ) -> SourceRecord:
        """
        함수 이름: save()
        기능: 원본을 잠금 밖에서 검사한 뒤 잠금 안에서 기존 등록과 비교해 저장한다.
            내용이 같으면 revision 유지, 다르면 revision+1과 이전 파생 캐시 참조 해제.
        인자: workspace_id/location/grant_id -> 범위, root -> 실제 root, relative -> 상대 경로
        반환값: 저장한 SourceRecord
        작성 날짜: 2026/11/10
        """
        scan = _scan(root, relative)
        now = now_utc()
        released: list[str] = []
        with self._lock, self._db.transaction():
            existing = self._db.find_path(workspace_id, path_key(location, grant_id, relative))
            if existing is None:
                record = SourceRecord(
                    f"src_{uuid.uuid4().hex}", workspace_id, location, grant_id, relative,
                    scan.media_type, scan.byte_size, scan.fingerprint, scan.identity, 1,
                    SourceStatus.READY, scan.preview, now, now,
                )  # fmt: skip
            else:
                same = existing.fingerprint == scan.fingerprint
                if not same:
                    released = self._db.links.release_refs(existing.source_id)
                record = dataclasses.replace(
                    existing, media_type=scan.media_type, byte_size=scan.byte_size,
                    fingerprint=scan.fingerprint, identity=scan.identity,
                    revision=existing.revision if same else existing.revision + 1,
                    status=SourceStatus.READY, preview=scan.preview, updated_at=now,
                )  # fmt: skip
            self._db.save(record)
        self.delete_caches(released)
        return record

    def verify(self, record: SourceRecord, root: Path) -> SourceRecord:
        """
        함수 이름: verify()
        기능: identity가 바뀐 경우만 재해시한다. 내용이 같으면 identity만 갱신하고,
            다르면 changed, 사라졌으면 missing으로 표시한 뒤 오류를 낸다.
        인자: record -> 등록 레코드, root -> 실제 허용 root
        반환값: 확인한 레코드
        작성 날짜: 2026/11/10
        """
        try:
            with open_verified(root, record.relative_path) as file:
                identity = identity_of(file)
                if identity == record.identity and record.status is SourceStatus.READY:
                    return record
                fingerprint, _ = hash_stable(file, media.size_limit(record.media_type))
        except ServiceError as error:
            if error.code is ErrorCode.NOT_FOUND:
                self._mark(record, SourceStatus.MISSING)
                raise ServiceError(
                    ErrorCode.NOT_FOUND, "원본 파일이 삭제됐습니다.", {"reason": "original_missing"}
                ) from error
            if error.code in (ErrorCode.PAYLOAD_TOO_LARGE, ErrorCode.SOURCE_CHANGED):
                self._mark(record, SourceStatus.CHANGED)
                raise ServiceError(ErrorCode.SOURCE_CHANGED, "원본이 바뀌었습니다.") from error
            raise
        if fingerprint != record.fingerprint:
            self._mark(record, SourceStatus.CHANGED)
            raise ServiceError(
                ErrorCode.SOURCE_CHANGED, "원본이 바뀌었습니다. 갱신 후 다시 읽으세요."
            )
        updated = dataclasses.replace(
            record, identity=identity, status=SourceStatus.READY, updated_at=now_utc()
        )
        with self._lock:
            self._db.save(updated)
        return updated

    def delete_caches(self, keys: list[str]) -> None:
        """
        함수 이름: delete_caches()
        기능: 더 이상 참조되지 않는 파생 캐시만 지운다.
        인자: keys -> 캐시 키
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        if self._cache is not None:
            for key in keys:
                self._cache.delete(key)

    def _mark(self, record: SourceRecord, status: SourceStatus) -> None:
        """
        함수 이름: _mark()
        기능: 상태만 바꿔 저장한다.
        인자: record -> 레코드, status -> 새 상태
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        with self._lock:
            self._db.save(dataclasses.replace(record, status=status, updated_at=now_utc()))
