"""Runtime blob 파일: 임시 파일 스트리밍 저장 → fsync → rename, 64 KiB 청크 digest 검증 읽기.

경로는 <root>/<workspace>/<session>/<pointer_id>.blob이며 DB에 절대 경로를 저장하지 않는다.
"""

import errno
import hashlib
import os
from pathlib import Path

from securecode_context.pointers.models.runtime import (
    BlobCorrupt,
    QuotaExceeded,
    StorageUnavailable,
)
from securecode_context.pointers.runtime.db import MAX_OBJECT_BYTES

CHUNK_BYTES = 64 * 1024
DIGEST_BYTES = 32
TEMP_PREFIX = ".tmp-"


def disk_error(error: OSError) -> Exception:
    """
    함수 이름: disk_error()
    기능: 디스크 오류를 공간 부족(QUOTA_EXCEEDED)과 그 외(SERVICE_UNAVAILABLE)로 나눈다.
    인자: error -> OS 오류
    반환값: 저장소 오류
    작성 날짜: 2026/11/10
    """
    if error.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", -1)):
        return QuotaExceeded("디스크 공간이 부족합니다", "disk_full")
    return StorageUnavailable("저장소에 쓸 수 없습니다", "disk_error")


def blob_path(root: Path, workspace_id: str, session_id: str, pointer_id: str) -> Path:
    """
    함수 이름: blob_path()
    기능: 범위와 ID로 blob 위치를 정한다(범위 문자열은 저장소가 먼저 검사한다).
    인자: root -> blob root, workspace_id/session_id -> 범위, pointer_id -> UUID
    반환값: 파일 경로
    작성 날짜: 2026/11/10
    """
    return root / workspace_id / session_id / f"{pointer_id}.blob"


class BlobWriter:
    """
    클래스 이름: BlobWriter
    기능: 임시 파일에 청크로 쓰며 전체·청크 SHA-256과 크기를 계산한다. commit 전에는 보이지 않는다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, target: Path) -> None:
        """
        함수 이름: __init__()
        기능: 같은 폴더에 임시 파일을 연다.
        인자: target -> 최종 blob 경로
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self.target = target
        self.temp = target.with_name(TEMP_PREFIX + target.name)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._stream = self.temp.open("xb")
        except OSError as error:
            raise disk_error(error) from error
        self._whole = hashlib.sha256()
        self._digests = bytearray()
        self._pending = bytearray()
        self.size = 0
        self.head = b""

    def write(self, data: bytes) -> None:
        """
        함수 이름: write()
        기능: 객체 상한을 넘기 전까지 쓰고 64 KiB마다 청크 digest를 남긴다.
        인자: data -> 다음 바이트
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        if self.size + len(data) > MAX_OBJECT_BYTES:
            raise QuotaExceeded("객체 용량 한도를 초과했습니다", "object_limit")
        try:
            self._stream.write(data)
        except OSError as error:
            raise disk_error(error) from error
        if len(self.head) < 8192:
            self.head += data[: 8192 - len(self.head)]
        self.size += len(data)
        self._whole.update(data)
        self._pending += data
        while len(self._pending) >= CHUNK_BYTES:
            self._digests += hashlib.sha256(self._pending[:CHUNK_BYTES]).digest()
            del self._pending[:CHUNK_BYTES]

    def commit(self) -> tuple[str, bytes]:
        """
        함수 이름: commit()
        기능: fsync 후 최종 이름으로 원자적으로 바꾼다.
        인자: 없음
        반환값: 전체 SHA-256 hex와 청크 digest 묶음
        작성 날짜: 2026/11/10
        """
        if self._pending:
            self._digests += hashlib.sha256(self._pending).digest()
            self._pending.clear()
        try:
            self._stream.flush()
            os.fsync(self._stream.fileno())
            self._stream.close()
            os.replace(self.temp, self.target)
        except OSError as error:
            self.abort()
            raise disk_error(error) from error
        return self._whole.hexdigest(), bytes(self._digests)

    def abort(self) -> None:
        """
        함수 이름: abort()
        기능: 임시 파일을 닫고 지운다. 여러 번 불러도 된다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        if not self._stream.closed:
            self._stream.close()
        self.temp.unlink(missing_ok=True)


class VerifiedBlob:
    """
    클래스 이름: VerifiedBlob
    기능: 읽는 64 KiB 청크마다 저장 때의 digest와 비교한다. 다르면 원문 대신 BlobCorrupt다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, path: Path, byte_size: int, digests: bytes) -> None:
        """
        함수 이름: __init__()
        기능: blob을 열고 크기와 digest 개수가 등록과 같은지 확인한다.
        인자: path -> blob, byte_size -> 등록 크기, digests -> 청크 digest 묶음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        try:
            self._stream = path.open("rb")
        except FileNotFoundError as error:
            raise BlobCorrupt("저장된 출력이 없습니다", "blob_missing") from error
        expected_chunks = (byte_size + CHUNK_BYTES - 1) // CHUNK_BYTES
        if os.fstat(self._stream.fileno()).st_size != byte_size or len(digests) != (
            expected_chunks * DIGEST_BYTES
        ):
            self._stream.close()
            raise BlobCorrupt("저장된 출력 크기가 다릅니다", "blob_size_mismatch")
        self._size = byte_size
        self._digests = digests
        self._position = 0
        self._cached: tuple[int, bytes] | None = None

    def seek(self, offset: int, whence: int = 0, /) -> int:
        """
        함수 이름: seek()
        기능: 논리 위치만 옮긴다.
        인자: offset -> 위치, whence -> 0(처음 기준)만 지원
        반환값: 새 위치
        작성 날짜: 2026/11/10
        """
        self._position = max(0, offset)
        return self._position

    def read(self, size: int = -1, /) -> bytes:
        """
        함수 이름: read()
        기능: 필요한 청크만 읽고 검증한 뒤 요청 구간을 돌려준다.
        인자: size -> 최대 바이트(-1이면 끝까지, 호출자는 상한을 준다)
        반환값: 바이트
        작성 날짜: 2026/11/10
        """
        end = self._size if size < 0 else min(self._size, self._position + size)
        parts: list[bytes] = []
        while self._position < end:
            index = self._position // CHUNK_BYTES
            chunk = self._chunk(index)
            start = self._position - index * CHUNK_BYTES
            piece = chunk[start : start + (end - self._position)]
            parts.append(piece)
            self._position += len(piece)
        return b"".join(parts)

    def close(self) -> None:
        """
        함수 이름: close()
        기능: 파일을 닫는다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._stream.close()

    def _chunk(self, index: int) -> bytes:
        """
        함수 이름: _chunk()
        기능: 청크 하나를 읽어 digest를 확인한다. 직전 청크는 다시 읽지 않는다.
        인자: index -> 청크 번호
        반환값: 청크 바이트
        작성 날짜: 2026/11/10
        """
        if self._cached is not None and self._cached[0] == index:
            return self._cached[1]
        self._stream.seek(index * CHUNK_BYTES)
        chunk = self._stream.read(CHUNK_BYTES)
        expected = self._digests[index * DIGEST_BYTES : (index + 1) * DIGEST_BYTES]
        if hashlib.sha256(chunk).digest() != expected:
            raise BlobCorrupt("저장된 출력이 손상됐습니다", "checksum_mismatch")
        self._cached = (index, chunk)
        return chunk
