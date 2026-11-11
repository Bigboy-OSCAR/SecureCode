"""모델 교체 및 LM Studio의 도구 이력 변환 회귀 시험."""

import lmstudio as lms

from securecode_context.common.tokens.counter import UnavailableTokenCounter
from securecode_context.common.tokens.lm_studio_counter import studio_history
from securecode_context.common.tokens.switchable_counter import SwitchableTokenCounter


def test_switch_updates_shared_references() -> None:
    """
    함수 이름: test_switch_updates_shared_references()
    기능: 포인터 서비스가 보관한 동일 객체도 새 모델의 상태를 읽는지 검증한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/11
    """
    counter = SwitchableTokenCounter(UnavailableTokenCounter("first"))
    pointer_counter = counter
    counter.replace(UnavailableTokenCounter("second"))
    assert pointer_counter.describe().reason == "second"


def test_studio_history_preserves_tool_call_and_result() -> None:
    """
    함수 이름: test_studio_history_preserves_tool_call_and_result()
    기능: 도구 호출을 텍스트로 평탄화하지 않고 실제 SDK의 표현으로 변환하는지 검증한다.
    인자: 없음
    반환값: 없음
    작성 날짜: 2026/11/11
    """
    history = studio_history(
        [
            {"role": "user", "content": "찾아 줘"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "find",
                            "arguments": '{"query":"한글"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "검색 결과"},
        ]
    )
    chat = lms.Chat.from_history(lms.ChatHistoryData.from_dict(history))
    assert chat is not None
    messages = history["messages"]
    call = messages[1]["content"][0]["toolCallRequest"]
    assert call["arguments"] == {"query": "한글"}
    assert call["id"] == messages[2]["content"][0]["toolCallId"]
