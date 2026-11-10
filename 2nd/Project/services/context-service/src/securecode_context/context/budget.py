"""검색 자료 예산 계산(4.8, 정책 3절). 고정 비용은 host가 넘긴 텍스트를 TokenCounter로 직접 센다.

길이/4나 바이트 수를 토큰으로 쓰지 않는다. 계수기가 없으면 TokenCounter가 TOKENIZER_UNAVAILABLE을 던진다.
"""

import math
from dataclasses import dataclass, field

from securecode_context.common.errors import ErrorCode, ServiceError
from securecode_context.common.tokens import TokenCounter
from securecode_context.common.tokens.models import CountMode

MIN_ESTIMATE_MARGIN = 1024
ESTIMATE_MARGIN_RATIO = 0.02


@dataclass(frozen=True)
class CostInput:
    """
    클래스 이름: CostInput
    기능: host가 넘긴 고정 비용 재료. 텍스트는 서비스가 세고 숫자 값은 host 설정이다.
        history는 다음 요청에 다시 실리는 메시지를 하나씩 직렬화한 텍스트다.
    작성 날짜: 2026/11/10
    """

    model_context_limit: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    message_overhead_tokens: int
    system: str
    tool_schema: str
    prompt: str
    history: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CountedCosts:
    """
    클래스 이름: CountedCosts
    기능: 센 고정 비용과 적용한 안전 마진, 계수 모드 집합.
    작성 날짜: 2026/11/10
    """

    source: CostInput
    system_tokens: int
    tool_schema_tokens: int
    prompt_tokens: int
    history_tokens: int
    safety_margin_tokens: int
    count_modes: frozenset[str]

    def base_budget(self) -> int:
        """
        함수 이름: base_budget()
        기능: 봉투 비용을 빼기 전 검색 자료 예산(정책 3.1 식).
        인자: 없음
        반환값: 음수일 수 있는 토큰 수
        작성 날짜: 2026/11/10
        """
        fixed = (
            self.system_tokens + self.tool_schema_tokens + self.prompt_tokens
            + self.history_tokens + self.source.message_overhead_tokens
            + self.source.reserved_output_tokens + self.safety_margin_tokens
        )  # fmt: skip
        return self.source.model_context_limit - fixed

    def to_wire(self, envelope_tokens: int) -> dict[str, int]:
        """
        함수 이름: to_wire()
        기능: 계약 ContextBudgetCosts. 메시지 overhead에 실제 넣은 fragment의 봉투 비용을 더한다.
        인자: envelope_tokens -> 넣은 fragment 봉투 합
        반환값: ContextBudgetCosts 사전
        작성 날짜: 2026/11/10
        """
        return {
            "model_context_limit": self.source.model_context_limit,
            "system_tokens": self.system_tokens,
            "tool_schema_tokens": self.tool_schema_tokens,
            "prompt_tokens": self.prompt_tokens,
            "history_tokens": self.history_tokens,
            "message_overhead_tokens": self.source.message_overhead_tokens + envelope_tokens,
            "reserved_output_tokens": self.source.reserved_output_tokens,
            "safety_margin_tokens": self.safety_margin_tokens,
        }


def minimum_margin(model_context_limit: int, exact: bool) -> int:
    """
    함수 이름: minimum_margin()
    기능: 계수 모드별 최소 안전 마진. exact가 아니면 max(1024, ceil(limit * 2%))다.
    인자: model_context_limit -> 모델 창, exact -> 모든 계수가 exact인지
    반환값: 최소 마진 토큰
    작성 날짜: 2026/11/10
    """
    if exact:
        return 0
    return max(MIN_ESTIMATE_MARGIN, math.ceil(model_context_limit * ESTIMATE_MARGIN_RATIO))


def plan_count_mode(modes: set[str] | frozenset[str]) -> str:
    """
    함수 이름: plan_count_mode()
    기능: 모든 계수가 exact일 때만 exact, 하나라도 추정이면 provider_estimate다.
    인자: modes -> 쓴 계수 모드
    반환값: 계약 CountMode 값
    작성 날짜: 2026/11/10
    """
    if modes and modes <= {CountMode.EXACT.value}:
        return CountMode.EXACT.value
    return CountMode.PROVIDER_ESTIMATE.value


def _count(counter: TokenCounter, text: str, modes: set[str]) -> int:
    """
    함수 이름: _count()
    기능: 빈 텍스트는 0, 아니면 TokenCounter로 센다.
    인자: counter -> 계수기, text -> 본문, modes -> 계수 모드를 모을 집합
    반환값: 토큰 수
    작성 날짜: 2026/11/10
    """
    if not text:
        return 0
    counted = counter.count(text)
    modes.add(counted.count_mode.value)
    return counted.token_count


def count_costs(counter: TokenCounter, costs: CostInput) -> CountedCosts:
    """
    함수 이름: count_costs()
    기능: system·도구 정의·프롬프트·이력을 세고 계수 모드에 맞는 안전 마진을 적용한다.
        예산이 음수면 계획 없이 BUDGET_EXCEEDED다(새 세션·범위 축소 안내).
    인자: counter -> TokenCounter, costs -> host 입력
    반환값: CountedCosts
    작성 날짜: 2026/11/10
    """
    modes: set[str] = set()
    system = _count(counter, costs.system, modes)
    tools = _count(counter, costs.tool_schema, modes)
    prompt = _count(counter, costs.prompt, modes)
    history = sum(_count(counter, message, modes) for message in costs.history)
    if len(costs.history) > 1:
        # 메시지별 합은 framing이 다르므로 exact가 아니다.
        modes.add(CountMode.PROVIDER_ESTIMATE.value)
    exact = plan_count_mode(modes) == CountMode.EXACT.value
    margin = max(costs.safety_margin_tokens, minimum_margin(costs.model_context_limit, exact))
    counted = CountedCosts(costs, system, tools, prompt, history, margin, frozenset(modes))
    if counted.base_budget() < 0:
        raise ServiceError(
            ErrorCode.BUDGET_EXCEEDED,
            "고정 비용이 모델 창을 넘습니다. 요청을 줄이거나 새 세션을 시작하세요.",
            {"reason": "fixed_costs", "budget_tokens": counted.base_budget()},
            retryable=False,
        )
    return counted
