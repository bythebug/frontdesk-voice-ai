"""Typed tool registry. The LLM never executes arbitrary code — it can only
request one of these registered tools by name with arguments that get
validated against a Pydantic schema before the handler runs."""

import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

Handler = Callable[[AsyncSession, BaseModel], Awaitable[BaseModel]]
ModelT = TypeVar("ModelT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int


class ToolSpec:
    def __init__(
        self, name: str, description: str, input_model: type[BaseModel], handler: Handler
    ) -> None:
        self.name = name
        self.description = description
        self.input_model = input_model
        self.handler = handler

    def json_schema(self) -> dict[str, Any]:
        """Ollama-compatible tool schema (OpenAI-style function schema)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_model.model_json_schema(),
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self, name: str, description: str, input_model: type[ModelT]
    ) -> Callable[
        [Callable[[AsyncSession, ModelT], Awaitable[OutputT]]],
        Callable[[AsyncSession, ModelT], Awaitable[OutputT]],
    ]:
        def decorator(
            handler: Callable[[AsyncSession, ModelT], Awaitable[OutputT]],
        ) -> Callable[[AsyncSession, ModelT], Awaitable[OutputT]]:
            self._tools[name] = ToolSpec(name, description, input_model, cast(Handler, handler))
            return handler

        return decorator

    def schemas(self) -> list[dict[str, Any]]:
        return [spec.json_schema() for spec in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(
        self, name: str, arguments: dict[str, Any], session: AsyncSession
    ) -> ToolResult:
        start = time.monotonic()

        def elapsed_ms() -> int:
            return int((time.monotonic() - start) * 1000)

        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(success=False, error=f"Unknown tool: {name}", latency_ms=elapsed_ms())

        try:
            parsed_input = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            return ToolResult(
                success=False, error=f"Invalid arguments: {exc}", latency_ms=elapsed_ms()
            )

        try:
            output = await spec.handler(session, parsed_input)
        except ToolExecutionError as exc:
            return ToolResult(success=False, error=str(exc), latency_ms=elapsed_ms())
        except Exception as exc:  # noqa: BLE001 — a failing tool must not crash the conversation
            return ToolResult(
                success=False,
                error=f"Tool '{name}' failed unexpectedly: {exc}",
                latency_ms=elapsed_ms(),
            )

        return ToolResult(
            success=True, data=output.model_dump(mode="json"), latency_ms=elapsed_ms()
        )


class ToolExecutionError(Exception):
    """Raised by a tool handler for an expected, user-facing failure
    (not found, already booked, etc.) — distinct from a bug."""


registry = ToolRegistry()
