"""기존 서비스 객체가 보유한 참조를 보존하며 로컬 모델 계수기를 교체한다."""

import threading
from collections.abc import Mapping
from typing import Any

from securecode_context.common.tokens.counter import CounterStatus, TokenCounter
from securecode_context.common.tokens.models import TokenCount
from securecode_context.common.tokens.request_framing import count_provider_request


class SwitchableTokenCounter:
    """
    클래스 이름: SwitchableTokenCounter
    기능: 포인터·색인·예산 서비스가 공유하는 계수기 참조와 원자적 교체를 제공한다.
    작성 날짜: 2026/11/11
    """

    def __init__(self, counter: TokenCounter) -> None:
        """
        함수 이름: __init__()
        기능: 최초 계수기와 교체 잠금을 보관한다.
        인자: counter -> 최초 계수기
        반환값: 없음
        작성 날짜: 2026/11/11
        """
        self._counter = counter
        self._lock = threading.RLock()

    @property
    def request_framing(self) -> str | None:
        """
        함수 이름: request_framing()
        기능: 활성 계수기의 요청 형식을 반환한다.
        인자: 없음
        반환값: 요청 형식 또는 None
        작성 날짜: 2026/11/11
        """
        return getattr(self._counter, "request_framing", None)

    def replace(self, counter: TokenCounter) -> None:
        """
        함수 이름: replace()
        기능: 진행 중 계수가 끝난 후 새 계수기로 바꾸고 이전 연결을 닫는다.
        인자: counter -> 검증된 새 계수기
        반환값: 없음
        작성 날짜: 2026/11/11
        """
        with self._lock:
            old = self._counter
            self._counter = counter
            close = getattr(old, "close", None)
            if close:
                close()

    def close(self) -> None:
        """
        함수 이름: close()
        기능: 활성 계수기의 연결을 닫는다.
        인자: 없음
        반환값: 없음
        작성 날짜: 2026/11/11
        """
        with self._lock:
            close = getattr(self._counter, "close", None)
            if close:
                close()

    def count(self, text: str, model_id: str | None = None) -> TokenCount:
        """
        함수 이름: count()
        기능: 활성 모델로 본문을 센다.
        인자: text -> 본문, model_id -> 선택 모델
        반환값: 계수 결과
        작성 날짜: 2026/11/11
        """
        with self._lock:
            return self._counter.count(text, model_id)

    def describe(self) -> CounterStatus:
        """
        함수 이름: describe()
        기능: 활성 계수기의 준비 상태를 반환한다.
        인자: 없음
        반환값: 준비 상태
        작성 날짜: 2026/11/11
        """
        return self._counter.describe()

    def count_request(self, request: Mapping[str, Any], model_id: str) -> TokenCount:
        """
        함수 이름: count_request()
        기능: 활성 계수기로 최종 요청 전체를 센다.
        인자: request -> 직렬화 요청, model_id -> 요청 모델
        반환값: 계수 결과
        작성 날짜: 2026/11/11
        """
        with self._lock:
            provider = (
                "anthropic" if self.request_framing == "anthropic_messages" else "openai-compatible"
            )
            return count_provider_request(self._counter, provider, model_id, request)
