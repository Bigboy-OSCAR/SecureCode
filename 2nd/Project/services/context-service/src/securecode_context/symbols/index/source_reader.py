"""작업 공간 루트 안의 일반 파일만 링크 교체 없이 제한된 크기로 읽는다."""

import os
import stat
import sys
from pathlib import Path

MAX_FILE_BYTES = 1024 * 1024


def _open_source(root: Path, path: Path, flags: int) -> int:
    """
    함수 이름: _open_source()
    기능: 지원하는 OS에서는 디렉터리 핸들을 따라 각 경로 요소의 심볼릭 링크를 거부한다.
    인자: root -> 기준 디렉터리, path -> 읽을 파일, flags -> 열기 플래그
    반환값: 열린 파일 디스크립터
    작성 날짜: 2026/11/05
    """
    if sys.platform == "win32":
        if any(os.path.isreserved(part) for part in path.relative_to(root).parts):
            raise PermissionError("reserved source path")
        return os.open(path, flags | os.O_BINARY)
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root, dir_flags)
    try:
        for part in path.parent.relative_to(root).parts:
            child = os.open(part, dir_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(path.name, flags | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)


def read_source(root: Path, path: Path) -> bytes:
    """
    함수 이름: read_source()
    기능: 루트 안의 일반 파일만 크기 제한 내에서 읽고 열기 중 파일 교체를 검사한다.
    인자: root -> 실제 루트, path -> 파일 경로
    반환값: 원문 바이트(상한 초과 확인용 1바이트 포함)
    작성 날짜: 2026/11/05
    """
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.resolve(strict=True) != path:
        raise OSError("path_rejected")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(_open_source(root, path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not os.path.samestat(info, opened) or not path.resolve().is_relative_to(root):
            raise OSError("path_rejected")
        if sys.platform == "win32":
            from securecode_context.common.windows_file import final_path

            if final_path(stream.fileno()) != path:
                raise OSError("path_rejected")
        source = stream.read(MAX_FILE_BYTES + 1)
        after_read = os.fstat(stream.fileno())
        if (opened.st_size, opened.st_mtime_ns) != (after_read.st_size, after_read.st_mtime_ns):
            raise OSError("source_changed")
        return source
