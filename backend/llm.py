"""The single LLM entry point. Every agent call goes through Portkey to gpt-6-luna."""

from typing import Any, Protocol

from openai import AsyncOpenAI

from .config import MODEL, PORTKEY_BASE_URL, portkey_api_key


class ChatLLM(Protocol):
    async def __call__(self, *, messages: list[dict], tools: list[dict], tool_choice: Any,
                       max_completion_tokens: int) -> Any: ...


class PortkeyLLM:
    """Calls gpt-6-luna through Portkey with tool calling. No other model is allowed."""

    model = MODEL

    def __init__(self) -> None:
        key = portkey_api_key()
        self._client = AsyncOpenAI(
            api_key=key,
            base_url=PORTKEY_BASE_URL,
            default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"},
        )

    async def __call__(self, *, messages: list[dict], tools: list[dict], tool_choice: Any,
                       max_completion_tokens: int) -> Any:
        assert self.model == "gpt-6-luna", "Only gpt-6-luna may be used by the agents."
        return await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=False,
            max_completion_tokens=max_completion_tokens,
            # gpt-6-luna (served via Azure OpenAI behind Portkey) rejects function tools on
            # /chat/completions unless reasoning is turned off for the call.
            reasoning_effort="none",
        )
