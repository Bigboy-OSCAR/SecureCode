"""PDF 페이지 캐시(4.9). 키는 원본 SHA-256 + 파서 버전이고 4.5 파생 캐시 폴더에 둔다.

캐시 하나 = manifest.json + pages/NNNN.txt(페이지별 UTF-8 텍스트). 등록 해제·revision 변경으로 마지막
참조가 풀리면 4.5 SourceLifecycle이 폴더를 지운다. 페이지 파일은 읽을 때 길이·SHA-256을 다시 확인한다.
"""

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pdf.worker import page_file
from securecode_context.pointers.source.derived import DerivedCacheDirectory

MANIFEST = "manifest.json"


@dataclass(frozen=True)
class PdfManifest:
    """
    클래스 이름: PdfManifest
    기능: 캐시한 파싱 결과. state는 ready/partial/unsupported/failed, pages는 페이지 번호별 메타다.
    작성 날짜: 2026/11/10
    """

    content_sha256: str
    parser_version: str
    state: str
    reason: str | None
    page_count: int
    pages: dict[int, dict[str, Any]]

    def excluded(self) -> list[dict[str, Any]]:
        """
        함수 이름: excluded()
        기능: 제외 페이지 목록(계약 excluded_pages 모양).
        인자: 없음
        반환값: [{page, reason}]
        작성 날짜: 2026/11/10
        """
        return [
            {"page": number, "reason": meta["excluded"]}
            for number, meta in sorted(self.pages.items())
            if "excluded" in meta
        ]


def cache_key(content_sha256: str, parser_version: str) -> str:
    """
    함수 이름: cache_key()
    기능: 원본 해시와 파서 버전으로 경로에 안전한 캐시 키를 만든다.
    인자: content_sha256 -> 원본 SHA-256, parser_version -> 파서 버전
    반환값: pdf- 접두사 키
    작성 날짜: 2026/11/10
    """
    digest = hashlib.sha256(f"{content_sha256}:{parser_version}".encode()).hexdigest()
    return "pdf-" + digest[:40]


class PdfPageCache:
    """
    클래스 이름: PdfPageCache
    기능: 파생 캐시 폴더 안의 PDF 캐시를 쓰고 읽는다.
    작성 날짜: 2026/11/10
    """

    def __init__(self, derived: DerivedCacheDirectory) -> None:
        """
        함수 이름: __init__()
        기능: 4.5 파생 캐시 폴더를 저장한다.
        인자: derived -> DerivedCacheDirectory
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._derived = derived

    def load(self, key: str) -> PdfManifest | None:
        """
        함수 이름: load()
        기능: 캐시 manifest를 읽는다. 없거나 읽을 수 없으면 None이다.
        인자: key -> 캐시 키
        반환값: PdfManifest 또는 None
        작성 날짜: 2026/11/10
        """
        path = self._derived.path_for(key) / MANIFEST
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pages = {int(meta["page"]): meta for meta in data["pages"]}
            return PdfManifest(
                data["content_sha256"], data["parser_version"], data["state"],
                data.get("reason"), int(data["page_count"]), pages,
            )  # fmt: skip
        except OSError, ValueError, KeyError, TypeError:
            return None

    def commit(self, key: str, work_dir: Path, manifest: dict[str, Any]) -> None:
        """
        함수 이름: commit()
        기능: 작업 폴더에 manifest를 쓰고 캐시 위치로 원자적으로 옮긴다. 이미 있으면 작업 폴더를 버린다.
        인자: key -> 캐시 키, work_dir -> 같은 볼륨의 작업 폴더, manifest -> manifest 사전
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        (work_dir / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        target = self._derived.path_for(key)
        try:
            os.replace(work_dir, target)
        except OSError:
            if self.load(key) is None:
                raise
            shutil.rmtree(work_dir, ignore_errors=True)

    def drop(self, key: str) -> None:
        """
        함수 이름: drop()
        기능: 참조를 걸지 못한 캐시를 지운다(파싱 중 등록 해제 등).
        인자: key -> 캐시 키
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._derived.delete(key)

    def page_bytes(self, key: str, manifest: PdfManifest, number: int) -> bytes:
        """
        함수 이름: page_bytes()
        기능: 페이지 텍스트를 읽고 manifest의 길이·SHA-256과 비교한다. 다르면 캐시를 지우고 거절한다.
        인자: key -> 캐시 키, manifest -> manifest, number -> 읽을 수 있는 페이지 번호
        반환값: UTF-8 바이트
        작성 날짜: 2026/11/10
        """
        meta = manifest.pages[number]
        try:
            data = page_file(self._derived.path_for(key), number).read_bytes()
        except OSError:
            data = b""
        if len(data) != meta["bytes"] or hashlib.sha256(data).hexdigest() != meta["sha256"]:
            self._derived.delete(key)
            raise ServiceError(
                ErrorCode.INDEX_NOT_READY,
                "PDF 페이지 캐시가 손상되어 다시 파싱해야 합니다.",
                {"reason": "pdf_cache_corrupt"},
            )
        return data
