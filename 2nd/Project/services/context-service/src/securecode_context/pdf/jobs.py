"""PDF 파싱 job(4.9): 같은 원본 해시·파서 버전은 같은 job을 재사용하고, 결과는 페이지 캐시에 둔다.

job ID는 (workspace, source, 원본 SHA-256, 파서 버전)에서 결정적으로 만든다. 같은 요청을 다시 보내면
같은 job을 돌려준다(멱등). 원본은 서비스 작업 폴더로 복사하며 SHA-256을 확인한 뒤 격리 프로세스로
파싱한다. 시간 초과는 failed/timeout(캐시하지 않음), 취소는 결과 없이 정리한다.
"""

import hashlib
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.pdf.cache import PdfPageCache, cache_key
from securecode_context.pdf.limits import (
    MAX_PARALLEL_JOBS,
    MAX_PDF_PAGES,
    PARSE_TIMEOUT_SECONDS,
    PARSER_VERSION,
    PDF_MEDIA,
)
from securecode_context.pdf.wire import job_status
from securecode_context.pdf.worker import ParseCancelledError, WorkerResult, run_isolated
from securecode_context.pointers.source.paths import open_verified
from securecode_context.pointers.source.registry import SourceRegistry

COPY_CHUNK = 1024 * 1024
DONE_STATES = ("ready", "partial", "unsupported", "failed")


@dataclass
class PdfJob:
    """
    클래스 이름: PdfJob
    기능: job 하나. state는 queued/running/ready/partial/unsupported/failed/stale이다.
    작성 날짜: 2026/11/10
    """

    job_id: str
    workspace_id: str
    pointer: str
    key: str
    content_sha256: str
    state: str = "queued"
    reason: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)


class PdfJobs:
    """
    클래스 이름: PdfJobs
    기능: parse 제출·상태·취소. 동시에 MAX_PARALLEL_JOBS개까지 격리 프로세스로 파싱한다.
    작성 날짜: 2026/11/10
    """

    def __init__(
        self,
        registry: SourceRegistry,
        cache: PdfPageCache,
        work_root: Path,
        timeout: float = PARSE_TIMEOUT_SECONDS,
    ) -> None:
        """
        함수 이름: __init__()
        기능: 등록부·캐시·작업 폴더를 저장하고 남은 작업 폴더를 지운다.
        인자: registry -> Source 등록부, cache -> 페이지 캐시, work_root -> 캐시와 같은 볼륨의 작업 폴더,
            timeout -> 파싱 시간 상한(초)
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        self._registry = registry
        self._cache = cache
        self._work_root = work_root
        self.timeout = timeout
        shutil.rmtree(work_root, ignore_errors=True)
        work_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._jobs: dict[str, PdfJob] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(MAX_PARALLEL_JOBS, thread_name_prefix="pdf-job")

    def submit(self, workspace_id: str, pointer: str) -> dict[str, Any]:
        """
        함수 이름: submit()
        기능: 현재 revision의 PDF Source를 확인하고 같은 job(진행 중·캐시 완료)을 재사용하거나 새로 시작한다.
            실패·stale job은 새 제출로 다시 시도한다.
        인자: workspace_id -> 인증된 범위, pointer -> 현재 revision URI
        반환값: PdfJobStatus
        작성 날짜: 2026/11/10
        """
        record = self._registry.resolve(workspace_id, pointer).record
        if record.media_type != PDF_MEDIA:
            raise ServiceError(
                ErrorCode.UNSUPPORTED_FORMAT, "PDF Source가 아닙니다.", {"reason": "not_pdf"}
            )
        identity = f"{workspace_id}|{record.source_id}|{record.fingerprint}|{PARSER_VERSION}"
        job_id = "pdf_" + hashlib.sha256(identity.encode()).hexdigest()[:40]
        key = cache_key(record.fingerprint, PARSER_VERSION)
        with self._lock:
            job = self._jobs.get(job_id)
            retry = job is not None and job.state == "failed" and self._cache.load(key) is None
            if job is None or job.state == "stale" or retry:
                job = PdfJob(job_id, workspace_id, record.pointer, key, record.fingerprint)
                self._jobs[job_id] = job
                cached = self._cache.load(key)
                if cached is None:
                    self._executor.submit(self._run, job)
                else:
                    job.state, job.reason = cached.state, cached.reason
        if job.state in DONE_STATES:
            self._registry.attach_derived(workspace_id, record.pointer, key)
        return self.status(workspace_id, job_id)

    def status(self, workspace_id: str, job_id: str) -> dict[str, Any]:
        """
        함수 이름: status()
        기능: job 상태를 돌려준다. 끝난 job은 원본·revision을 다시 확인해 바뀌었으면 stale이다.
        인자: workspace_id -> 인증된 범위, job_id -> job ID
        반환값: PdfJobStatus
        작성 날짜: 2026/11/10
        """
        job = self._jobs.get(job_id)
        if job is None or job.workspace_id != workspace_id:
            raise ServiceError(ErrorCode.NOT_FOUND, "PDF job을 찾을 수 없습니다.")
        state, reason = job.state, job.reason
        manifest = self._cache.load(job.key) if state in ("ready", "partial") else None
        if state in DONE_STATES:
            try:
                self._registry.resolve(workspace_id, job.pointer)
            except ServiceError as error:
                if error.code != ErrorCode.SOURCE_CHANGED:
                    raise
                state, reason, manifest = "stale", "source_changed", None
        if state in ("ready", "partial") and manifest is None:
            state, reason = "stale", "parser_changed"
        return job_status(job_id, workspace_id, job.pointer, state, reason, manifest)

    def cancel(self, workspace_id: str, job_id: str) -> None:
        """
        함수 이름: cancel()
        기능: 진행 중 job을 멈추고 기록을 지운다(작업 폴더는 실행 스레드가 지운다). 없으면 무시한다.
        인자: workspace_id -> 범위, job_id -> job ID
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job.workspace_id == workspace_id:
                job.cancel.set()
                del self._jobs[job_id]

    def close(self) -> None:
        """
        함수 이름: close()
        기능: 모든 job을 취소하고 실행 스레드를 정리한다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        with self._lock:
            for job in self._jobs.values():
                job.cancel.set()
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _copy_source(self, job: PdfJob, target: Path) -> bool:
        """
        함수 이름: _copy_source()
        기능: 원본을 작업 폴더로 복사하며 SHA-256을 계산한다. 등록 해시와 다르면 False다.
        인자: job -> job, target -> 복사본 경로
        반환값: 해시가 같으면 True
        작성 날짜: 2026/11/10
        """
        resolved = self._registry.resolve(job.workspace_id, job.pointer)
        digest = hashlib.sha256()
        with (
            open_verified(resolved.root, resolved.record.relative_path) as source,
            target.open("wb") as copy,
        ):
            while chunk := source.read(COPY_CHUNK):
                digest.update(chunk)
                copy.write(chunk)
        return digest.hexdigest() == job.content_sha256

    def _run(self, job: PdfJob) -> None:
        """
        함수 이름: _run()
        기능: [작업 스레드] 복사·검증 → 격리 파싱 → 캐시 저장·참조 기록. 실패는 상태로 남긴다.
        인자: job -> job
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        work = self._work_root / uuid.uuid4().hex
        try:
            work.mkdir(mode=0o700)
            if job.cancel.is_set():
                raise ParseCancelledError
            job.state = "running"
            if not self._copy_source(job, work / "source.pdf"):
                job.state, job.reason = "stale", "source_changed"
                return
            source = work / "source.pdf"
            result = run_isolated(source, work / "out", MAX_PDF_PAGES, self.timeout, job.cancel)
            self._finish(job, work / "out", result)
        except ParseCancelledError:
            job.state, job.reason = "failed", "cancelled"
        except ServiceError as error:
            if error.code == ErrorCode.SOURCE_CHANGED:
                job.state, job.reason = "stale", "source_changed"
            else:
                job.state, job.reason = "failed", "parse_failed"
        except Exception:
            job.state, job.reason = "failed", "parse_failed"
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _finish(self, job: PdfJob, out: Path, result: WorkerResult) -> None:
        """
        함수 이름: _finish()
        기능: 결과를 manifest로 캐시하고 Source에 참조를 건다. 시간 초과는 캐시하지 않는다.
        인자: job -> job, out -> 자식이 쓴 폴더, result -> 자식 결과
        반환값: 없음
        작성 날짜: 2026/11/10
        """
        if job.cancel.is_set():
            raise ParseCancelledError
        if result.reason == "timeout":
            job.state, job.reason = "failed", "timeout"
            return
        out.mkdir(parents=True, exist_ok=True)
        state = result.state
        if state == "ok":
            state = "partial" if any("excluded" in page for page in result.pages) else "ready"
        manifest = {
            "content_sha256": job.content_sha256,
            "parser_version": PARSER_VERSION,
            "state": state,
            "reason": result.reason,
            "page_count": len(result.pages),
            "pages": result.pages,
        }
        self._cache.commit(job.key, out, manifest)
        try:
            self._registry.attach_derived(job.workspace_id, job.pointer, job.key)
        except ServiceError:
            self._cache.drop(job.key)
            raise
        job.state, job.reason = state, result.reason
