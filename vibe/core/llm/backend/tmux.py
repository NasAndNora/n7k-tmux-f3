"""TmuxBackend - Wraps CLI sessions (Claude/Gemini) via tmux."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import types
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from vibe.cli_backends.models import ParsedConfirmation
from vibe.core.types import (
    AvailableTool,
    LLMChunk,
    LLMMessage,
    LLMUsage,
    Role,
    StrToolChoice,
)

if TYPE_CHECKING:
    from vibe.core.config import ModelConfig, ProviderConfig


class TmuxBackend:
    """Backend that wraps tmux-based CLI sessions (Claude/Gemini)."""

    def __init__(self, provider: ProviderConfig, timeout: float = 720.0) -> None:
        self._provider = provider
        self._timeout = timeout
        self._session: Any = None
        self._session_class: type | None = None

    def _get_session_class(self) -> type:
        """Lazy import session class based on provider name."""
        if self._session_class is not None:
            return self._session_class

        provider_name = self._provider.name.lower()
        if provider_name == "claude":
            from vibe.cli_backends.claude.session import ClaudeSessionTmux

            self._session_class = ClaudeSessionTmux
        elif provider_name == "gemini":
            from vibe.cli_backends.gemini.session import GeminiSessionTmux

            self._session_class = GeminiSessionTmux
        else:
            raise ValueError(f"Unknown tmux provider: {provider_name}")

        return self._session_class

    async def __aenter__(self) -> TmuxBackend:
        session_class = self._get_session_class()
        session_name = f"{self._provider.name}_{uuid4().hex[:8]}"
        self._session = session_class(session_name=session_name)
        await asyncio.to_thread(self._session.start)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        if self._session is not None:
            await asyncio.to_thread(self._session.close)
            self._session = None

    async def interrupt(self) -> None:
        """Interrupt current generation (no-op if not generating)."""
        if self._session:
            await asyncio.to_thread(self._session.interrupt)

    def _messages_to_prompt(self, messages: list[LLMMessage]) -> str:
        """Convert LLMMessage list to single prompt string."""
        if not messages:
            return ""
        # Just use the last user message as prompt
        # Context is built by DebateAgent before calling
        last = messages[-1]
        return last.content or ""

    async def complete(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        tools: list[AvailableTool] | None = None,
        max_tokens: int | None = None,
        tool_choice: StrToolChoice | AvailableTool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> LLMChunk:
        """Non-streaming completion."""
        prompt = self._messages_to_prompt(messages)
        timeout = int(self._timeout)

        response = await asyncio.to_thread(self._session.ask, prompt, timeout)

        # Handle confirmation (Claude/Gemini)
        if isinstance(response, ParsedConfirmation):
            return LLMChunk(
                message=LLMMessage(role=Role.assistant, content=""),
                usage=LLMUsage(),
                finish_reason="confirmation",
            )

        content = response if isinstance(response, str) else str(response)
        return LLMChunk(
            message=LLMMessage(role=Role.assistant, content=content),
            usage=LLMUsage(),
            finish_reason="stop",
        )

    async def complete_streaming(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        tools: list[AvailableTool] | None = None,
        max_tokens: int | None = None,
        tool_choice: StrToolChoice | AvailableTool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncGenerator[LLMChunk, None]:
        """Streaming completion using queue to bridge sync callback."""
        prompt = self._messages_to_prompt(messages)
        timeout = int(self._timeout)

        queue: asyncio.Queue[str | dict | None] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def on_update(text: str) -> None:
            asyncio.run_coroutine_threadsafe(queue.put(text), loop)

        async def run_ask() -> Any:
            result = await asyncio.to_thread(
                self._session.ask, prompt, timeout, on_update
            )
            await queue.put(None)  # Signal completion
            return result

        task = asyncio.create_task(run_ask())
        final_result: Any = None

        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
                if chunk is None:
                    break
                if isinstance(chunk, str):
                    yield LLMChunk(
                        message=LLMMessage(role=Role.assistant, content=chunk),
                        usage=LLMUsage(),
                        finish_reason=None,
                    )
            except TimeoutError:
                if task.done():
                    break
                continue

        # Get final result
        try:
            final_result = await task
        except Exception:
            pass

        # Handle confirmation
        if isinstance(final_result, ParsedConfirmation):
            # Pass the confirmation context (contains the tool box with diff)
            context = final_result.context
            yield LLMChunk(
                message=LLMMessage(role=Role.assistant, content=context),
                usage=LLMUsage(),
                finish_reason="confirmation",
            )
        else:
            yield LLMChunk(
                message=LLMMessage(role=Role.assistant, content=""),
                usage=LLMUsage(),
                finish_reason="stop",
            )

    async def count_tokens(
        self,
        *,
        model: ModelConfig,
        messages: list[LLMMessage],
        temperature: float = 0.0,
        tools: list[AvailableTool] | None = None,
        tool_choice: StrToolChoice | AvailableTool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> int:
        """Estimate token count (rough: chars / 4)."""
        total = 0
        for msg in messages:
            if msg.content:
                total += len(msg.content)
        return total // 4

    async def close(self) -> None:
        """Close the session."""
        if self._session is not None:
            await asyncio.to_thread(self._session.close)
            self._session = None

    # Gemini-specific methods
    async def respond_confirmation(self, choice: str) -> None:
        """Respond to Gemini confirmation prompt."""
        if self._session is None:
            return
        await asyncio.to_thread(self._session.respond_confirmation, choice)

    async def wait_response(self, timeout: int = 120) -> Any:
        """Wait for response after confirmation (Gemini)."""
        if self._session is None:
            return ""
        return await asyncio.to_thread(self._session.wait_response, timeout)

    def is_gemini(self) -> bool:
        """Check if this is a Gemini backend."""
        return self._provider.name.lower() == "gemini"
