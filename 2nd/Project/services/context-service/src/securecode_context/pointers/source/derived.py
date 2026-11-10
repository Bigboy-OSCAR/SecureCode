"""Source에서 만든 서비스 소유 파생 캐시(PDF 페이지 등)의 삭제 포트."""

import re
import shutil
from pathlib import Path
from typing import Protocol

from securecode_context.common.errors import ErrorCode, ServiceError

_CACHE_KEY = re.compile(r"[A-Za-z0-9_-]{1,128}")


def check_cache_key(cache_key: str) -> None:
    """
    함수 이름: check_cache_key()
    기능: 캐시 키가 경로 요소로 안전한 형식인지 확인한다.
    인자: cache_key -> 파생 캐시 키
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    if not _CACHE_KEY.fullmatch(cache_key):
        raise ServiceError(ErrorCode.VALIDATION_FAILED, "캐시 키 형식이 올바르지 않습니다.")


class DerivedCachePort(Protocol):
    """
    클래스 이름: DerivedCachePort
    기능: 마지막 참조가 사라진 파생 캐시를 지운다. 사용자 원본은 이 포트의 대상이 아니다.
    작성 날짜: 2026/11/10
    """

    def delete(self, cache_key: str) -> None:
        """
        함수 이름: delete()
        기능: 캐시 키 하나의 서비스 소유 데이터를 지운다. 없으면 아무것도 하지 않는다.
        인자: cache_key -> 검사한 캐시 키
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        ...


class DerivedCacheDirectory:
    """
    클래스 이름: DerivedCacheDirectory
    기능: 데이터 폴더 아래 <root>/<cache_key> 디렉터리를 파생 캐시로 소유한다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, root: Path) -> None:
        """
        함수 이름: __init__()
        기능: 캐시 root를 만든다.
        인자: root -> 서비스 데이터 폴더 아래 경로
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root.resolve(strict=True)

    def path_for(self, cache_key: str) -> Path:
        """
        함수 이름: path_for()
        기능: 캐시 키의 저장 디렉터리 위치를 돌려준다(4.9가 쓰기 위치로 사용).
        인자: cache_key -> 캐시 키
        반환값: root 바로 아래 경로
        작성 날짜: 2026/11/10
        """
        check_cache_key(cache_key)
        return self.root / cache_key

    def delete(self, cache_key: str) -> None:
        """
        함수 이름: delete()
        기능: root 바로 아래의 캐시 디렉터리만 지운다. 링크이면 링크만 제거한다.
        인자: cache_key -> 캐시 키
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        target = self.path_for(cache_key)
        if target.is_symlink() or target.is_junction():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
