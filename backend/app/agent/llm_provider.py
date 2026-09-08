"""LLM abstraction over Ollama. The rest of the app never talks to Ollama's
HTTP API directly — swapping providers means implementing this interface."""

from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import get_settings

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    content: str
    tool_calls: list[ToolCallRequest] = []


class LLMUnavailableError(Exception):
    """The LLM backend couldn't be reached or returned an error."""


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse: ...

    @abstractmethod
    async def generate_structured(
        self, messages: list[dict[str, str]], response_model: type[StructuredT]
    ) -> StructuredT: ...


class OllamaProvider(LLMProvider):
    def __init__(
        self, host: str | None = None, model: str | None = None, timeout: float | None = None
    ) -> None:
        settings = get_settings()
        self.host = host or settings.ollama_host
        self.model = model or settings.ollama_model
        self.timeout = timeout if timeout is not None else settings.ollama_timeout_seconds

    async def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.host}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama request failed: {exc}") from exc
        result: dict[str, Any] = response.json()
        return result

    async def generate(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools

        body = await self._chat(payload)
        message = body.get("message", {})
        tool_calls = [
            ToolCallRequest(
                name=call["function"]["name"], arguments=call["function"].get("arguments", {})
            )
            for call in message.get("tool_calls") or []
        ]
        return LLMResponse(content=message.get("content", ""), tool_calls=tool_calls)

    async def generate_structured(
        self, messages: list[dict[str, str]], response_model: type[StructuredT]
    ) -> StructuredT:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": response_model.model_json_schema(),
        }
        body = await self._chat(payload)
        content = body.get("message", {}).get("content", "{}")
        return response_model.model_validate_json(content)
