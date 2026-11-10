"""격리된 PDF 파싱 프로세스(4.9). 시간 초과·취소 때 프로세스째 끝내므로 멈춘 파서가 서비스를 잡지 않는다.

자식 프로세스는 서비스가 복사한 원본만 읽고 작업 폴더에 페이지 파일과 result.json만 쓴다.
"""

import hashlib
import json
import multiprocessing
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from securecode_context.pdf.parser import PdfRejectedError, extract_pages

RESULT_FILE = "result.json"
PAGES_DIR = "pages"


class ParseCancelledError(Exception):
    """
    클래스 이름: ParseCancelledError
    기능: 취소(해제·서비스 종료)로 파싱을 멈췄다는 신호. 결과를 남기지 않는다.
    작성 날짜: 2026/11/10
    """


@dataclass(frozen=True)
class WorkerResult:
    """
    클래스 이름: WorkerResult
    기능: 자식 프로세스 결과. state는 ok/unsupported/failed이고 ok면 pages에 페이지 메타가 있다.
    작성 날짜: 2026/11/10
    """

    state: str
    reason: str | None
    pages: list[dict[str, Any]]


def page_file(out_dir: Path, number: int) -> Path:
    """
    함수 이름: page_file()
    기능: 페이지 텍스트 파일 위치.
    인자: out_dir -> 작업/캐시 폴더, number -> 페이지 번호
    반환값: 경로
    작성 날짜: 2026/11/10
    """
    return out_dir / PAGES_DIR / f"{number:04d}.txt"


def _child(source: str, out_dir: str, page_limit: int) -> None:
    """
    함수 이름: _child()
    기능: [자식 프로세스] 페이지를 추출해 UTF-8 파일과 result.json을 쓴다.
    인자: source -> 복사한 원본, out_dir -> 작업 폴더, page_limit -> 페이지 상한
    반환값: 없음
    작성 날짜: 2026/11/10
    """
    out = Path(out_dir)
    result: dict[str, Any]
    try:
        (out / PAGES_DIR).mkdir(parents=True, exist_ok=True)
        pages = []
        for page in extract_pages(Path(source), page_limit):
            if page.text is None:
                pages.append({"page": page.number, "excluded": page.excluded})
                continue
            data = page.text.encode("utf-8")
            page_file(out, page.number).write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            pages.append({"page": page.number, "bytes": len(data), "sha256": sha})
        result = {"state": "ok", "reason": None, "pages": pages}
    except PdfRejectedError as rejected:
        result = {"state": rejected.state, "reason": rejected.reason, "pages": []}
    except Exception:
        result = {"state": "failed", "reason": "parse_failed", "pages": []}
    (out / RESULT_FILE).write_text(json.dumps(result), encoding="utf-8")


def run_isolated(
    source: Path, out_dir: Path, page_limit: int, timeout: float, cancel: threading.Event
) -> WorkerResult:
    """
    함수 이름: run_isolated()
    기능: 자식 프로세스로 파싱하고 시간 초과면 failed/timeout, 취소면 ParseCancelled를 낸다.
    인자: source -> 복사한 원본, out_dir -> 작업 폴더, page_limit -> 페이지 상한,
        timeout -> 초 단위 상한, cancel -> 취소 신호
    반환값: WorkerResult
    작성 날짜: 2026/11/10
    """
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_child, args=(str(source), str(out_dir), page_limit), daemon=True
    )
    process.start()
    deadline = time.monotonic() + timeout
    try:
        while process.is_alive():
            process.join(0.05)
            if cancel.is_set():
                raise ParseCancelledError
            if time.monotonic() > deadline:
                return WorkerResult("failed", "timeout", [])
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
    result_path = out_dir / RESULT_FILE
    if not result_path.is_file():
        return WorkerResult("failed", "parse_failed", [])
    data = json.loads(result_path.read_text(encoding="utf-8"))
    return WorkerResult(data["state"], data["reason"], data["pages"])
