"""선택한 디렉터리 아래 파일을 링크를 따라가지 않고 최대 100개까지 나열한다."""

import os
from pathlib import Path, PurePosixPath

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pointers.source.models import SourceIssue
from securecode_context.pointers.source.paths import normalize_relative

MAX_DIRECTORY_ENTRIES = 100


def list_directory(directory: Path) -> tuple[list[PurePosixPath], list[SourceIssue]]:
    """
    함수 이름: list_directory()
    기능: 하위 항목을 모두 센 뒤 일반 파일만 후보로 돌려준다. 100개를 넘으면 아무것도 등록하지 않는다.
        링크·정션·이름이 허용되지 않는 항목은 FORBIDDEN, 특수 파일은 UNSUPPORTED_FORMAT issue다.
    인자: directory -> 검사한 실제 디렉터리
    반환값: 선택 root 기준 파일 상대 경로와 제외 issue
    작성 날짜: 2026/11/10
    """
    files: list[PurePosixPath] = []
    issues: list[SourceIssue] = []
    pending: list[tuple[Path, PurePosixPath]] = [(directory, PurePosixPath())]
    seen = 0
    while pending:
        current, prefix = pending.pop()
        with os.scandir(current) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                seen += 1
                if seen > MAX_DIRECTORY_ENTRIES:
                    raise ServiceError(
                        ErrorCode.PAYLOAD_TOO_LARGE,
                        "선택한 폴더에 항목이 너무 많습니다. 더 좁은 범위를 선택하세요.",
                        {"limit": MAX_DIRECTORY_ENTRIES},
                    )
                relative = prefix / entry.name
                issue = _classify(entry, relative)
                if issue is not None:
                    issues.append(issue)
                elif entry.is_dir(follow_symlinks=False):
                    pending.append((Path(entry.path), relative))
                else:
                    files.append(relative)
    files.sort()
    return files, issues


def _classify(entry: os.DirEntry[str], relative: PurePosixPath) -> SourceIssue | None:
    """
    함수 이름: _classify()
    기능: 한 항목을 따라갈 수 있는지 판단한다.
    인자: entry -> 디렉터리 항목, relative -> 선택 root 기준 경로
    반환값: 제외 issue, 허용이면 None
    작성 날짜: 2026/11/10
    """
    try:
        normalize_relative(relative.as_posix())
    except ServiceError:
        return SourceIssue(relative.as_posix(), ErrorCode.FORBIDDEN.value)
    if entry.is_symlink() or entry.is_junction():
        return SourceIssue(relative.as_posix(), ErrorCode.FORBIDDEN.value)
    if entry.is_dir(follow_symlinks=False) or entry.is_file(follow_symlinks=False):
        return None
    return SourceIssue(relative.as_posix(), ErrorCode.UNSUPPORTED_FORMAT.value)
