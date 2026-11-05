"""작업 공간에 등록한 파일을 변경 확인 후 부분 조회한다."""

import io
import os
import stat
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import BinaryIO

from securecode_context.pointers.limits import (
    MAX_READ_BYTES,
    check_read_limit,
    utf8_prefix,
)

type Fingerprint = tuple[int, int, int, int, int]


def _fingerprint(file: BinaryIO) -> Fingerprint:
    """함수 이름: _fingerprint()
    기능: 열린 파일의 객체 식별자·크기·내용 변경 시각을 읽는다.
    인자: file -> 열린 원본
    반환값: 등록 시점과 비교할 식별 값
    작성 날짜: 2026/11/05
    """
    info = os.fstat(file.fileno())
    if sys.platform == "win32":
        from securecode_context.common.windows_file import change_time

        changed = change_time(file.fileno())
    else:
        changed = info.st_ctime_ns
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, changed


@dataclass(frozen=True)
class SourceItem:
    """클래스 이름: SourceItem
    기능: 원본의 등록 경로와 등록 시점의 객체 정보를 보관한다.
    작성 날짜: 2026/11/05
    """

    path: Path
    workspace_id: str
    fingerprint: Fingerprint


class SourceStore:
    """클래스 이름: SourceStore
    기능: 작업 공간 범위에서 원본 파일 등록·조회·해제를 제공한다.
    작성 날짜: 2026/11/05
    """

    def __init__(self, root_dir: str) -> None:
        """함수 이름: __init__()
        기능: 작업 공간 루트와 빈 등록부를 준비한다.
        인자: root_dir -> 실제 작업 공간 디렉터리
        반환값: 없음
        작성 날짜: 2026/11/05
        """
        self.root = Path(root_dir).resolve(strict=True)
        self._root_stat = self.root.stat()
        if not stat.S_ISDIR(self._root_stat.st_mode):
            raise NotADirectoryError("source root is not a directory")
        self.items: dict[str, SourceItem] = {}
        self._by_path: dict[tuple[str, Path], str] = {}
        self._lock = Lock()

    @contextmanager
    def _open(self, path: Path) -> Iterator[BinaryIO]:
        """함수 이름: _open()
        기능: 루트 안에서 확인한 실제 경로를 디렉터리 핸들 기준으로 열어 링크 교체를 차단한다.
        인자: path -> 작업 공간 상대 경로
        반환값: 등록된 루트 아래의 일반 파일
        작성 날짜: 2026/11/05
        """
        real = (self.root / path).resolve(strict=False)
        if real == self.root or not real.is_relative_to(self.root):
            raise PermissionError("path escapes workspace root")
        parts = real.relative_to(self.root).parts
        if sys.platform == "win32":
            from securecode_context.common.windows_file import final_path

            if any(os.path.isreserved(part) for part in parts):
                raise PermissionError("reserved source path")
            with real.open("rb") as file:
                if (
                    not stat.S_ISREG(os.fstat(file.fileno()).st_mode)
                    or not os.path.samestat(self._root_stat, self.root.stat())
                    or final_path(file.fileno()) != real
                ):
                    raise PermissionError("source handle outside authorized path")
                yield file
            return
        directory_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
        directory_fd = os.open(self.root, directory_flags)
        try:
            if not os.path.samestat(self._root_stat, os.fstat(directory_fd)):
                raise PermissionError("workspace root changed")
            for part in parts[:-1]:
                child = os.open(part, directory_flags, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = child
            fd = os.open(
                parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory_fd,
            )
        finally:
            os.close(directory_fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise PermissionError("source must be a regular file")
        with os.fdopen(fd, "rb") as file:
            yield file

    def register(self, relative_path: str, workspace_id: str) -> str:
        """함수 이름: register()
        기능: 같은 경로·버전은 재사용하고 변경된 파일은 새 ID로 등록한다.
        인자: relative_path -> 작업 공간 상대 경로, workspace_id -> 작업 공간 ID
        반환값: 원본 등록 ID
        작성 날짜: 2026/11/05
        """
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise PermissionError("source requires a workspace-relative path")
        key = (workspace_id, path)
        with self._lock, self._open(path) as file:
            item = SourceItem(path, workspace_id, _fingerprint(file))
            existing = self._by_path.get(key)
            if existing is not None:
                if self.items[existing] == item:
                    return existing
                del self.items[existing]
            source_id = str(uuid.uuid4())
            self.items[source_id] = item
            self._by_path[key] = source_id
            return source_id

    def read(
        self,
        source_id: str,
        workspace_id: str,
        start_line: int = 1,
        end_line: int | None = None,
        max_bytes: int = MAX_READ_BYTES,
    ) -> str:
        """함수 이름: read()
        기능: 요청한 줄에서 바이트 상한만큼만 읽고, 등록 시점과 읽기 전후의 파일을 확인한다.
        인자: source_id/workspace_id -> 등록 범위, start_line/end_line -> 1부터 시작하는 줄, max_bytes -> 바이트 상한
        반환값: 선택한 UTF-8 원문
        작성 날짜: 2026/11/05
        """
        check_read_limit(max_bytes)
        if start_line < 1 or (end_line is not None and end_line < start_line):
            raise ValueError("invalid line range")
        with self._lock:
            item = self.items.get(source_id)
        if item is None:
            raise KeyError("source pointer not found")
        if item.workspace_id != workspace_id:
            raise PermissionError("workspace scope mismatch")
        with self._open(item.path) as file:
            if _fingerprint(file) != item.fingerprint:
                raise ValueError("source file changed")
            text = self._read_lines(file, start_line, end_line, max_bytes)
            if _fingerprint(file) != item.fingerprint:
                raise ValueError("source file changed")
        with self._open(item.path) as current:
            if _fingerprint(current) != item.fingerprint:
                raise ValueError("source file changed")
        return text

    @staticmethod
    def _read_lines(file: BinaryIO, start: int, end: int | None, limit: int) -> str:
        """함수 이름: _read_lines()
        기능: 긴 줄도 작은 단위로 건너뛰며 선택한 범위에만 출력 한도를 적용한다.
        인자: file -> 열린 파일, start/end -> 양끝 포함 줄 범위, limit -> UTF-8 바이트 상한
        반환값: 줄 구분을 정규화한 원문
        작성 날짜: 2026/11/05
        """
        text = io.TextIOWrapper(file, encoding="utf-8", newline=None)
        output = bytearray()
        line, at_start = 1, True
        try:
            while (end is None or line <= end) and (segment := text.readline(8192)):
                if line >= start:
                    if at_start and line > start:
                        output.extend(b"\n")
                    raw = segment.removesuffix("\n").encode()
                    output.extend(raw[: limit - len(output)])
                    if len(output) >= limit:
                        break
                at_start = segment.endswith("\n")
                if at_start:
                    line += 1
        finally:
            text.detach()
        return utf8_prefix(bytes(output))[0]

    def unregister(self, source_id: str, workspace_id: str) -> bool:
        """함수 이름: unregister()
        기능: 작업 공간의 등록 메타데이터를 해제한다.
        인자: source_id/workspace_id -> 등록 범위
        반환값: 해제 성공 여부
        작성 날짜: 2026/11/05
        """
        with self._lock:
            item = self.items.get(source_id)
            if item is None or item.workspace_id != workspace_id:
                return False
            del self.items[source_id]
            del self._by_path[(workspace_id, item.path)]
            return True
