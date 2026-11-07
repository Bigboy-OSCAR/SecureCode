"""Context 예산 계산 및 Token Counter 모듈.

작성일: 2026-11-07
"""

from typing import Any, Dict, List


class ContextBudgetCalculator:
    """모델 맥락 예산 및 토큰 잔여량 계산기."""

    def __init__(self, model_limit: int = 128000, reserved_output: int = 4096, safety_margin: int = 1024):
        self.model_limit = model_limit
        self.reserved_output = reserved_output
        self.safety_margin = safety_margin

    def estimate_tokens(self, text: str) -> int:
        """단순 추정 토큰 계산기 (문자 길이 4대비 추정)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def calculate_available_tokens(
        self,
        system_prompt: str,
        tool_schemas: List[Dict[str, Any]],
        history: List[Dict[str, Any]],
        user_message: str
    ) -> int:
        system_t = self.estimate_tokens(system_prompt)
        tools_t = self.estimate_tokens(str(tool_schemas))
        user_t = self.estimate_tokens(user_message)
        history_t = sum(self.estimate_tokens(str(m)) for m in history)

        overhead = system_t + tools_t + user_t + history_t + self.reserved_output + self.safety_margin
        available = self.model_limit - overhead
        return available
