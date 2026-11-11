"""LM Studio의 실제 tokenizer와 도구를 포함한 chat template으로 MLX 요청을 센다."""

import json
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlparse

import lmstudio as lms

from securecode_context.common.tokens.counter import CounterStatus, measure_countable_text
from securecode_context.common.tokens.llama_cpp_counter import _unavailable
from securecode_context.common.tokens.models import CountMode, TokenCount
from securecode_context.common.tokens.request_framing import openai_input


def studio_history(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    함수 이름: studio_history()
    기능: OpenAI 텍스트·도구 호출·도구 결과를 LM Studio의 동일한 대화 표현으로 옮긴다.
    인자: messages -> 최종 outbound 메시지
    반환값: LM Studio Chat history
    작성 날짜: 2026/11/11
    """
    history: list[dict[str, Any]] = []
    for message in messages:
        role = message["role"]
        content = message.get("content") or ""
        if isinstance(content, list):
            if any(part.get("type") != "text" for part in content):
                raise _unavailable("multimodal_framing_unverified", False)
            content = "".join(part["text"] for part in content)
        if not isinstance(content, str):
            raise _unavailable("framing_unverified", False)
        parts: list[dict[str, Any]] = []
        if role == "tool":
            parts.append(
                {
                    "type": "toolCallResult",
                    "content": content,
                    "toolCallId": message["tool_call_id"],
                }
            )
        else:
            if content:
                parts.append({"type": "text", "text": content})
            for call in message.get("tool_calls", []):
                function = call["function"]
                parts.append(
                    {
                        "type": "toolCallRequest",
                        "toolCallRequest": {
                            "type": "function",
                            "name": function["name"],
                            "id": call["id"],
                            "arguments": json.loads(function["arguments"]),
                        },
                    }
                )
        history.append({"role": role, "content": parts})
    return {"messages": history}


class LmStudioTokenCounter:
    """
    클래스 이름: LmStudioTokenCounter
    기능: 로드된 모델의 SDK tokenizer와 prompt template을 이용한 정확 계수.
    작성 날짜: 2026/11/11
    """

    request_framing = "openai_chat"

    def __init__(self, base_url: str, model_id: str) -> None:
        """
        함수 이름: __init__()
        기능: 로컬 LM Studio 주소와 모델 식별자를 보관한다.
        인자: base_url -> 로컬 서버 URL, model_id -> 로드된 모델 식별자
        반환값: 없음
        작성 날짜: 2026/11/11
        """
        self.model_id = model_id
        self._host = urlparse(base_url).netloc

    def describe(self) -> CounterStatus:
        """
        함수 이름: describe()
        기능: 설정 여부를 반환한다. 도달 여부는 실제 계수 시 확인한다.
        인자: 없음
        반환값: 설정 상태
        작성 날짜: 2026/11/11
        """
        return CounterStatus(configured=True)

    def count(self, text: str, model_id: str | None = None) -> TokenCount:
        """
        함수 이름: count()
        기능: 실제 모델 tokenizer로 본문을 센다.
        인자: text -> 본문, model_id -> 생략 또는 활성 모델
        반환값: 정확 계수 결과
        작성 날짜: 2026/11/11
        """
        size = measure_countable_text(text)
        if model_id is not None and model_id != self.model_id:
            raise _unavailable("model_not_configured", False)
        try:
            with lms.Client(self._host) as client:
                count = len(client.llm.model(self.model_id).tokenize(text))
        except Exception as error:
            raise _unavailable("lm_studio_tokenize_failed", True) from error
        return TokenCount(
            count,
            CountMode.EXACT,
            "openai-compatible",
            self.model_id,
            "lm_studio_tokenize",
            "plain_text",
            size,
        )

    def count_request(self, request: Mapping[str, Any], model_id: str) -> TokenCount:
        """
        함수 이름: count_request()
        기능: 도구 정의와 호출 이력을 포함해 서버 template을 적용하고 실제 tokenizer로 센다.
        인자: request -> 최종 요청, model_id -> 요청 모델
        반환값: 정확 계수 결과
        작성 날짜: 2026/11/11
        """
        if model_id != self.model_id or request.get("model") != self.model_id:
            raise _unavailable("model_not_configured", False)
        inputs = openai_input(request)
        if inputs.get("tool_choice", "auto") != "auto":
            raise _unavailable("tool_choice_unverified", False)
        try:
            history = studio_history(inputs["messages"])
            with lms.Client(self._host) as client:
                model = client.llm.model(self.model_id)
                prompt = model.apply_prompt_template(
                    lms.Chat.from_history(
                        lms.ChatHistoryData.from_dict(cast(lms.ChatHistoryDataDict, history))
                    ),
                    {
                        "toolDefinitions": inputs.get("tools", []),
                    },
                )
                count = len(model.tokenize(prompt))
        except Exception as error:
            raise _unavailable("lm_studio_request_count_failed", True) from error
        size = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        return TokenCount(
            count,
            CountMode.EXACT,
            "openai-compatible",
            self.model_id,
            "lm_studio_tokenize",
            "provider_request",
            size,
        )
