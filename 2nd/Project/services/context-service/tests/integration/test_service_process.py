"""실제 프로세스로 context-service를 띄워 loopback 바인딩·인증·health·종료를 확인한다."""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from support.helpers import TEST_TOKEN

pytestmark = pytest.mark.integration


def find_free_port() -> int:
    """
    함수 이름: find_free_port()
    기능: 127.0.0.1에서 비어 있는 포트를 하나 고른다.
    인자: 없음
    반환값: 포트 번호
    작성 날짜: 2026/11/04
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture
def service_process(tmp_path: Path) -> Iterator[tuple[subprocess.Popen[bytes], int]]:
    """
    함수 이름: service_process()
    기능: 키 없는 환경으로 서비스를 기동하고 시험 뒤 종료한다.
    인자: tmp_path -> 데이터 디렉토리로 쓸 임시 경로
    반환값: (프로세스, 포트)
    작성 날짜: 2026/11/04
    """
    port = find_free_port()
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("ANTHROPIC_", "SECURECODE_"))
    }
    environment.update(
        {
            "SECURECODE_INTERNAL_TOKEN": TEST_TOKEN,
            "SECURECODE_DATA_DIR": str(tmp_path / "data"),
            "SECURECODE_CONTEXT_SERVICE_PORT": str(port),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "securecode_context.app"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        yield process, port
    finally:
        process.terminate()
        process.wait(timeout=15)


def wait_for_health(port: int, timeout_seconds: float = 20.0) -> httpx.Response:
    """
    함수 이름: wait_for_health()
    기능: health가 응답할 때까지 짧게 재시도한다.
    인자: port -> 서비스 포트
        timeout_seconds -> 최대 대기 시간
    반환값: 첫 성공 응답
    작성 날짜: 2026/11/04
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            return httpx.get(
                f"http://127.0.0.1:{port}/internal/v1/health",
                headers={"Authorization": f"Bearer {TEST_TOKEN}"},
                timeout=2.0,
            )
        except httpx.TransportError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def test_service_starts_authenticates_and_stops(
    service_process: tuple[subprocess.Popen[bytes], int],
) -> None:
    """
    함수 이름: test_service_starts_authenticates_and_stops()
    기능: 기동 후 health 200, 토큰 없는 요청 401, 로그에 토큰 미기록, 종료 신호 후 프로세스 종료를 확인한다.
    인자: service_process -> 기동된 서비스와 포트
    반환값: 없음
    작성 날짜: 2026/11/04
    """
    process, port = service_process
    health = wait_for_health(port)
    assert health.status_code == 200
    assert health.json()["service"] == "context-service"

    anonymous = httpx.get(f"http://127.0.0.1:{port}/internal/v1/health", timeout=2.0)
    assert anonymous.status_code == 401

    process.terminate()
    process.wait(timeout=15)
    logs = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
    assert TEST_TOKEN not in logs
    assert "starting context-service on 127.0.0.1" in logs
