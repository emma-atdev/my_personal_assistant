"""ChatGPT PKCE OAuth 기반 LangChain BaseChatModel 래퍼.

오케스트레이터에서 OpenAI API 키 대신 ChatGPT Plus 구독을 사용할 수 있다.
토큰 파일(.chatgpt_tokens.json)이 없으면 자동으로 폴백하지 않으므로
로그인 후 사용해야 한다: uv run python -m auth.chatgpt_pkce login
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages import AIMessage as _AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable
from pydantic import Field

# ── 메시지 변환 ─────────────────────────────────────────────


def _to_responses_input(messages: list[BaseMessage]) -> tuple[str, list[dict[str, Any]]]:
    """LangChain 메시지를 Responses API 입력 형식으로 변환한다."""
    system = ""
    inputs: list[dict[str, Any]] = []

    for msg in messages:
        if isinstance(msg, SystemMessage):
            system = str(msg.content)

        elif isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, list):
                text = " ".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text")
            else:
                text = str(content)
            inputs.append({"role": "user", "content": text})

        elif isinstance(msg, AIMessage):
            # 툴 콜이 있으면 function_call 아이템으로 변환
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    inputs.append(
                        {
                            "type": "function_call",
                            "call_id": tc["id"],
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"]),
                        }
                    )
            # 텍스트 내용이 있으면 assistant 메시지로 추가
            if msg.content and not msg.tool_calls:
                inputs.append({"role": "assistant", "content": str(msg.content)})

        elif isinstance(msg, ToolMessage):
            inputs.append(
                {
                    "type": "function_call_output",
                    "call_id": msg.tool_call_id,
                    "output": str(msg.content),
                }
            )

    return system, inputs


# ── LangChain 모델 ───────────────────────────────────────────


class ChatGPTPKCEModel(BaseChatModel):
    """ChatGPT Plus PKCE OAuth 기반 LangChain 채팅 모델.

    create_deep_agent(model=ChatGPTPKCEModel(), ...) 형태로 사용한다.
    """

    model_name: str = Field(default="gpt-5.1-codex-mini", alias="model")

    model_config = {"populate_by_name": True}

    @property
    def _llm_type(self) -> str:
        return "chatgpt-pkce"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model_name}

    def bind_tools(  # type: ignore[override]
        self,
        tools: list[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[PromptValue | str | list[BaseMessage], _AIMessage]:
        """툴을 Responses API 형식으로 변환해 바인드한다."""
        formatted: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, dict):
                formatted.append(tool)
                continue
            schema: dict[str, Any] = {}
            if hasattr(tool, "args_schema") and tool.args_schema:
                try:
                    schema = tool.args_schema.model_json_schema()
                except Exception:  # noqa: BLE001
                    schema = {}
            formatted.append(
                {
                    "type": "function",
                    "name": getattr(tool, "name", str(tool)),
                    "description": getattr(tool, "description", ""),
                    "parameters": schema,
                }
            )
        return self.bind(tools=formatted, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        import asyncio

        try:
            asyncio.get_running_loop()
            # 이미 이벤트 루프 안에 있으면 새 스레드에서 실행
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self._agenerate(messages, stop, None, **kwargs))
                return future.result()
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop, None, **kwargs))

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        from auth.chatgpt_pkce import ChatGPTCodexClient

        system, inputs = _to_responses_input(messages)
        tools: list[dict[str, Any]] | None = kwargs.get("tools") or None

        text = ""
        tool_calls: dict[str, dict[str, Any]] = {}  # call_id → data
        input_tokens = 0
        output_tokens = 0

        async with ChatGPTCodexClient() as client:
            async for event in client.stream_responses(
                inputs=inputs,
                system=system,
                tools=tools,
                model=self.model_name,
            ):
                etype = event.get("type", "")

                if etype == "response.output_text.delta":
                    delta = event.get("delta", "")
                    if delta:
                        text += delta
                        if run_manager:
                            await run_manager.on_llm_new_token(delta)

                elif etype == "response.output_item.done":
                    item = event.get("item", {})
                    if item.get("type") == "function_call":
                        call_id = item.get("call_id") or item.get("id", "")
                        tool_calls[call_id] = {
                            "name": item.get("name", ""),
                            "args": item.get("arguments", "{}"),
                            "id": call_id,
                        }

                elif etype in ("response.done", "response.completed"):
                    usage = (event.get("response") or {}).get("usage", {})
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)

        # tool_calls dict → LangChain 형식
        lc_tool_calls: list[dict[str, Any]] = []
        for tc in tool_calls.values():
            try:
                args = json.loads(tc["args"]) if isinstance(tc["args"], str) else tc["args"]
            except json.JSONDecodeError:
                args = {}
            lc_tool_calls.append({"name": tc["name"], "args": args, "id": tc["id"], "type": "tool_call"})

        ai_msg = AIMessage(
            content=text,
            tool_calls=lc_tool_calls,
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])


# ── 편의 헬퍼 ────────────────────────────────────────────────

_PKCE_TOKENS_AVAILABLE: bool | None = None  # 프로세스 내 캐시


def get_model(pkce_model: str = "gpt-5.1-codex-mini", openai_fallback: str = "openai:gpt-4o-mini") -> Any:
    """PKCE 토큰이 있으면 ChatGPTPKCEModel, 없으면 OpenAI 모델 문자열을 반환한다.

    오케스트레이터·서브에이전트에서 공통으로 사용하는 팩토리 함수.

    Args:
        pkce_model: PKCE OAuth 사용 시 모델 ID
        openai_fallback: 토큰 없을 때 사용할 langchain init_chat_model 문자열
    """
    global _PKCE_TOKENS_AVAILABLE
    if _PKCE_TOKENS_AVAILABLE is None:
        try:
            from auth.chatgpt_pkce import load_tokens

            tokens = load_tokens()
            _PKCE_TOKENS_AVAILABLE = bool(tokens and tokens.get("access_token"))
        except Exception:  # noqa: BLE001
            _PKCE_TOKENS_AVAILABLE = False

    if _PKCE_TOKENS_AVAILABLE:
        return ChatGPTPKCEModel(model=pkce_model)

    from langchain.chat_models import init_chat_model

    return init_chat_model(openai_fallback)
