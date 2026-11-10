"""서비스 수명 동안의 정리 작업(4.10): TTL이 지난 Runtime 출력과 오래된 tombstone을 지운다.

만료 포인터는 읽기에서 이미 EXPIRED로 거절되지만, 이 작업이 없으면 파일이 디스크에 남는다.
시작 직후 한 번, 이후 SWEEP_INTERVAL_SECONDS마다 작업 스레드에서 실행한다.
"""

import asyncio
import logging
from collections.abc import Callable

from starlette.concurrency import run_in_threadpool

SWEEP_INTERVAL_SECONDS = 600.0
_LOG = logging.getLogger("securecode_context.maintenance")


async def sweep_forever(sweep: Callable[[], int], interval: float = SWEEP_INTERVAL_SECONDS) -> None:
    """
    함수 이름: sweep_forever()
    기능: sweep을 시작 직후와 interval마다 실행한다. 실패는 기록만 하고 다음 주기에 다시 시도한다.
    인자: sweep -> RuntimeStore.sweep_expired, interval -> 주기(초)
    반환값: 없음(취소될 때까지 실행)
    작성 날짜: 2026/11/10
    """
    while True:
        try:
            removed = await run_in_threadpool(sweep)
            if removed:
                _LOG.info("runtime sweep removed %d expired outputs", removed)
        except Exception:
            _LOG.warning("runtime sweep failed; retrying next interval")
        await asyncio.sleep(interval)
