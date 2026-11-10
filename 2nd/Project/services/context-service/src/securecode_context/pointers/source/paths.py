"""Source 경로 정책: 상대 경로 정규화, 외부 허용 root 검사, 링크 교체를 막는 열기와 fingerprint."""

import hashlib
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source.models import Identity

HASH_CHUNK_BYTES = 1024 * 1024
_CONTROL = {chr(code) for code in range(32)} | {"\x7f"}


def forbidden(reason: str) -> ServiceError:
    """
    함수 이름: forbidden()
    기능: 경로를 노출하지 않는 FORBIDDEN 오류를 만든다.
    인자: reason -> details.reason 값
    반환값: ServiceError
    작성 날짜: 2026/11/10
    """
    return ServiceError(ErrorCode.FORBIDDEN, "허용되지 않은 경로입니다.", {"reason": reason})


def _same_path(left: Path, right: Path) -> bool:
    """
    함수 이름: _same_path()
    기능: Windows 대소문자 차이를 무시하고 두 실제 경로가 같은지 비교한다.
    인자: left/right -> 비교할 절대 경로
    반환값: 같은 경로이면 True
    작성 날짜: 2026/11/10
    """
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _inside(path: Path, root: Path) -> bool:
    """
    함수 이름: _inside()
    기능: 문자열 접두어가 아닌 경로 요소 경계로 root 아래인지 확인한다.
    인자: path -> 실제 경로, root -> 실제 root
    반환값: root 자신이거나 그 아래이면 True
    작성 날짜: 2026/11/10
    """
    try:
        common = os.path.commonpath([os.path.normcase(str(path)), os.path.normcase(str(root))])
    except ValueError:
        return False
    return common == os.path.normcase(str(root))


def normalize_relative(raw: str) -> PurePosixPath:
    """
    함수 이름: normalize_relative()
    기능: 계약 RelativePath를 검사한다. 절대·드라이브·역슬래시·..·.·예약 이름·제어 문자를 거부한다.
    인자: raw -> 요청의 상대 경로
    반환값: 정규화한 POSIX 상대 경로
    작성 날짜: 2026/11/10
    """
    if not 1 <= len(raw) <= 1024 or "\\" in raw or any(char in _CONTROL for char in raw):
        raise forbidden("invalid_relative_path")
    if raw.startswith("/") or PureWindowsPath(raw).drive:
        raise forbidden("absolute_path")
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise forbidden("path_traversal")
    if sys.platform == "win32" and any(os.path.isreserved(part) for part in parts):
        raise forbidden("reserved_name")
    return PurePosixPath(*parts)


def resolve_external_root(raw: str, forbidden_roots: tuple[Path, ...]) -> Path:
    """
    함수 이름: resolve_external_root()
    기능: 사용자가 고른 외부 경로를 허용 root로 만든다. 상대·네트워크·장치 경로, 링크 자체,
        파일 시스템 최상위, 서비스 데이터 폴더와 겹치는 경로를 거부한다.
    인자: raw -> 요청 본문의 절대 경로, forbidden_roots -> 서비스 소유 폴더
    반환값: 실제 경로
    작성 날짜: 2026/11/10
    """
    if not 1 <= len(raw) <= 4096 or any(char in _CONTROL for char in raw):
        raise forbidden("invalid_external_path")
    if raw.startswith(("\\\\", "//")):
        raise forbidden("network_or_device_path")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise forbidden("external_path_not_absolute")
    if ".." in candidate.parts:
        raise forbidden("path_traversal")
    if candidate.is_symlink() or candidate.is_junction():
        raise forbidden("external_path_is_link")
    try:
        real = candidate.resolve(strict=True)
    except OSError as error:
        raise ServiceError(ErrorCode.NOT_FOUND, "원본을 찾을 수 없습니다.") from error
    if real == Path(real.anchor):
        raise forbidden("filesystem_root")
    for owned in forbidden_roots:
        if _inside(real, owned) or _inside(owned, real):
            raise forbidden("service_owned_path")
    return real


def check_inside(root: Path, relative: PurePosixPath) -> Path:
    """
    함수 이름: check_inside()
    기능: root 아래 상대 경로의 실제 위치를 확인한다. 경로 중간 링크·정션과 root 이탈을 거부한다.
    인자: root -> 실제 허용 root, relative -> 정규화한 상대 경로
    반환값: 실제 파일 경로
    작성 날짜: 2026/11/10
    """
    lexical = root.joinpath(*relative.parts)
    try:
        real = lexical.resolve(strict=True)
    except OSError as error:
        raise ServiceError(ErrorCode.NOT_FOUND, "원본을 찾을 수 없습니다.") from error
    if not _same_path(real, lexical):
        raise forbidden("link_in_path")
    if not _inside(real, root) or _same_path(real, root):
        raise forbidden("path_outside_root")
    return real


# Windows has no O_NOFOLLOW/dir_fd; open_verified checks final_path there instead.
if sys.platform != "win32":

    def _open_posix(root: Path, relative: PurePosixPath) -> int:
        """
        함수 이름: _open_posix()
        기능: 디렉터리 핸들을 따라 각 요소를 O_NOFOLLOW로 열어 열기 도중 링크 교체를 막는다.
        인자: root -> 실제 root, relative -> 상대 경로
        반환값: 열린 파일 기술자
        작성 날짜: 2026/11/10
        """
        directory_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
        directory_fd = os.open(root, directory_flags)
        try:
            for part in relative.parts[:-1]:
                child = os.open(part, directory_flags, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = child
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            return os.open(relative.parts[-1], flags, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)


@contextmanager
def open_verified(root: Path, relative: PurePosixPath) -> Iterator[BinaryIO]:
    """
    함수 이름: open_verified()
    기능: 경로를 검사한 뒤 같은 일반 파일인지 핸들로 다시 확인하고 연다.
    인자: root -> 실제 허용 root, relative -> 상대 경로
    반환값: 읽기 전용 이진 파일
    작성 날짜: 2026/11/10
    """
    real = check_inside(root, relative)
    before = real.lstat()
    try:
        if sys.platform == "win32":
            fd = os.open(real, os.O_RDONLY | os.O_BINARY)
        else:
            fd = _open_posix(root, relative)
    except OSError as error:
        raise forbidden("open_rejected") from error
    with os.fdopen(fd, "rb") as file:
        opened = os.fstat(file.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise ServiceError(ErrorCode.UNSUPPORTED_FORMAT, "일반 파일만 등록할 수 있습니다.")
        if not os.path.samestat(before, opened):
            raise ServiceError(ErrorCode.SOURCE_CHANGED, "원본이 열기 도중 바뀌었습니다.")
        if sys.platform == "win32":
            from securecode_context.common.windows_file import final_path

            if not _same_path(final_path(file.fileno()), real):
                raise forbidden("handle_outside_root")
        yield file


def identity_of(file: BinaryIO) -> Identity:
    """
    함수 이름: identity_of()
    기능: 열린 파일의 장치·inode·크기·수정·변경 시각을 읽는다. 바뀌지 않으면 재해시하지 않는다.
    인자: file -> 열린 원본
    반환값: 비교용 identity
    작성 날짜: 2026/11/10
    """
    info = os.fstat(file.fileno())
    if sys.platform == "win32":
        from securecode_context.common.windows_file import change_time

        changed = change_time(file.fileno())
    else:
        changed = info.st_ctime_ns
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, changed


def hash_stable(file: BinaryIO, max_bytes: int) -> tuple[str, bytes]:
    """
    함수 이름: hash_stable()
    기능: 고정 크기 청크로 SHA-256을 계산한다. 크기 상한 초과나 계산 중 변경은 실패다.
    인자: file -> 열린 원본, max_bytes -> 허용 최대 크기
    반환값: 전체 SHA-256과 앞부분 8 KiB(형식 판별·미리보기용)
    작성 날짜: 2026/11/10
    """
    before = identity_of(file)
    if before[2] > max_bytes:
        raise ServiceError(
            ErrorCode.PAYLOAD_TOO_LARGE, "원본 크기가 등록 한도를 넘습니다.", {"limit": max_bytes}
        )
    digest = hashlib.sha256()
    head = b""
    total = 0
    file.seek(0)
    while chunk := file.read(HASH_CHUNK_BYTES):
        if not head:
            head = chunk[:8192]
        total += len(chunk)
        if total > max_bytes:
            raise ServiceError(ErrorCode.SOURCE_CHANGED, "원본이 등록 도중 커졌습니다.")
        digest.update(chunk)
    if identity_of(file) != before or total != before[2]:
        raise ServiceError(ErrorCode.SOURCE_CHANGED, "원본이 등록 도중 바뀌었습니다.")
    return digest.hexdigest(), head
