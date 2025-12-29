"""DebateAgent - orchestrates multi-AI conversations."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
import logging
import re
import types
from typing import TYPE_CHECKING

from vibe.cli.textual_ui.widgets.ai_tools import CLIToolInfo
from vibe.cli_backends.claude.parser import ClaudeToolParser
from vibe.cli_backends.gemini.parser import GeminiToolParser
from vibe.cli_backends.models import ParsedConfirmation, ParsedResponse
from vibe.core.config import Backend, ProviderConfig
from vibe.core.llm.backend.tmux import TmuxBackend
from vibe.core.types import (
    AssistantEvent,
    BaseEvent,
    CLIToolResultEvent,
    LLMMessage,
    Role,
)
from vibe.debate.routing import Message, build_context, parse_routing_tag

if TYPE_CHECKING:
    from vibe.core.config import ModelConfig, VibeConfig

logger = logging.getLogger(__name__)


class DebateAgent:
    """Routes messages between Claude and Gemini backends."""

    def __init__(self, config: VibeConfig, timeout: float = 720.0) -> None:
        self._config = config
        self._timeout = timeout

        # Create provider configs for tmux backends
        self._claude_provider = ProviderConfig(
            name="claude", api_base="", backend=Backend.TMUX
        )
        self._gemini_provider = ProviderConfig(
            name="gemini", api_base="", backend=Backend.TMUX
        )

        self._claude_backend: TmuxBackend | None = None
        self._gemini_backend: TmuxBackend | None = None

        # Conversation state
        self.messages: list[Message] = []
        # -1 means "never responded", will see all messages from index 0
        self.last_seen: dict[str, int] = {"claude": -1, "gemini": -1}

        # Pending confirmation state
        self._pending_confirmation: dict | None = None
        self._pending_tool_info: CLIToolInfo | None = None
        self._action_contexts: list[
            str
        ] = []  # B55: Accumulate diffs for chained commands

        # Parsers per AI
        self._gemini_parser = GeminiToolParser()
        self._claude_parser = ClaudeToolParser()

    async def __aenter__(self) -> DebateAgent:
        """Start both tmux sessions. Continue if one fails (F8)."""
        self._backend_errors: dict[str, str] = {}

        # Claude
        try:
            self._claude_backend = TmuxBackend(
                provider=self._claude_provider, timeout=self._timeout
            )
            await self._claude_backend.__aenter__()
        except Exception as e:
            self._claude_backend = None
            self._backend_errors["claude"] = str(e)

        # Gemini
        try:
            self._gemini_backend = TmuxBackend(
                provider=self._gemini_provider, timeout=self._timeout
            )
            await self._gemini_backend.__aenter__()
        except Exception as e:
            self._gemini_backend = None
            self._backend_errors["gemini"] = str(e)

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Close both sessions."""
        if self._claude_backend:
            await self._claude_backend.__aexit__(exc_type, exc_val, exc_tb)
        if self._gemini_backend:
            await self._gemini_backend.__aexit__(exc_type, exc_val, exc_tb)

    def _get_backend(self, target: str) -> TmuxBackend:
        """Get backend for target."""
        if target == "claude":
            if not self._claude_backend:
                raise RuntimeError("Claude backend not initialized")
            return self._claude_backend
        elif target == "gemini":
            if not self._gemini_backend:
                raise RuntimeError("Gemini backend not initialized")
            return self._gemini_backend
        else:
            raise ValueError(f"Unknown target: {target}")

    def _get_parser(self, target: str) -> GeminiToolParser | ClaudeToolParser:
        """Get parser for target."""
        if target == "claude":
            return self._claude_parser
        elif target == "gemini":
            return self._gemini_parser
        else:
            raise ValueError(f"Unknown target: {target}")

    def _get_model_config(self) -> ModelConfig:
        """Get a dummy model config (not used for tmux backends)."""
        return self._config.get_active_model()

    async def route_message(
        self, user_input: str, target: str | None = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """Route message to appropriate AI and yield events.

        Args:
            user_input: Raw user message (may include @tag)
            target: Override target (if tag already parsed)

        Yields:
            AssistantEvent with streamed content
        """

        # Parse tag if not provided
        logger.debug("=== route_message START === input: %s...", user_input[:50])

        if target is None:
            target, clean_msg = parse_routing_tag(user_input)
            logger.debug("parsed tag: target=%s, clean_msg=%s...", target, clean_msg[:30])
            if target is None:
                # No tag - caller should show selector
                logger.debug("NO TARGET - returning (should show selector)")
                return
        else:
            _, clean_msg = parse_routing_tag(user_input)
            logger.debug("target provided: %s, clean_msg=%s...", target, clean_msg[:30])

        # Add user message to history
        self.messages.append(
            Message(role="user", content=clean_msg, timestamp=datetime.now())
        )

        # Build context for target
        context = build_context(
            self.messages[:-1],  # Exclude current message
            target,
            self.last_seen,
        )

        # Prepend context if any
        # B49 fix: No colons in labels - Gemini CLI interprets as bash command
        # Format: "Context:\n...\nUSER asks message" (all on same line, no colon after asks)
        if context:
            prompt = f"{context}\nUSER asks {clean_msg}"
        else:
            prompt = f"USER asks {clean_msg}"

        # Log prompt for debugging (B49: shell mode trigger)
        logger.debug("=== PROMPT SENT TO %s ===", target.upper())
        logger.debug("prompt built, length=%d", len(prompt))

        # Get backend and stream response
        backend = self._get_backend(target)
        logger.debug("got backend: %s", backend.__class__.__name__)
        model = self._get_model_config()
        messages = [LLMMessage(role=Role.user, content=prompt)]

        full_response = ""
        logger.debug("starting streaming loop...")

        async for chunk in backend.complete_streaming(
            model=model,
            messages=messages,
            temperature=0.2,
            tools=None,
            max_tokens=None,
            tool_choice=None,
            extra_headers=None,
        ):
            logger.debug(
                "chunk received: finish_reason=%s, content_len=%d",
                chunk.finish_reason,
                len(chunk.message.content or ""),
            )
            if chunk.finish_reason == "confirmation":
                logger.debug("Agent received confirmation from backend")
                # AI confirmation - parse tool info from the confirmation context
                # The context is in chunk.message.content (passed from TmuxBackend)
                confirmation_context = chunk.message.content or ""

                if confirmation_context:
                    logger.debug("=== CONFIRMATION CONTEXT ===")
                    logger.debug("%s", confirmation_context[:500])  # First 500 chars

                    # Use parser for this AI
                    parser = self._get_parser(target)
                    _, tool_info = parser.parse(confirmation_context, debug=True)
                    self._pending_tool_info = tool_info

                    if tool_info:
                        logger.debug(
                            "=== PARSED === tool_type=%s, file_path=%s, diff_lines=%d",
                            tool_info.tool_type,
                            tool_info.file_path,
                            len(tool_info.diff_lines),
                        )
                    else:
                        logger.debug("=== NO TOOL INFO PARSED ===")

                self._pending_confirmation = {
                    "target": target,
                    "context": confirmation_context,
                }
                # Don't yield anything - ApprovalApp will handle the UI
                return

            content = chunk.message.content or ""
            # Clean cursor
            clean_content = content.rstrip(" ▌").rstrip("▌")
            clean_full = full_response.rstrip(" ▌").rstrip("▌")

            if clean_content and clean_content != clean_full:
                full_response = content
                # B20 fix: Clean shell markers
                clean_content = re.sub(
                    r"__SHELL_OUTPUT__:.*", "", clean_content, flags=re.DOTALL
                )
                clean_content = re.sub(
                    r"Command exited with code:\s*\d+",
                    "",
                    clean_content,
                    flags=re.IGNORECASE,
                )
                if clean_content.strip():
                    # Send full content - widget will replace (not append)
                    yield AssistantEvent(content=clean_content)

        logger.debug("streaming loop DONE, full_response_len=%d", len(full_response))

        # Add AI response to history
        if full_response:
            # B20 fix: Clean shell markers before storing
            clean_response = re.sub(
                r"__SHELL_OUTPUT__:.*", "", full_response, flags=re.DOTALL
            )
            clean_response = re.sub(
                r"Command exited with code:\s*\d+",
                "",
                clean_response,
                flags=re.IGNORECASE,
            )
            clean_response = clean_response.rstrip(" ▌").strip()
            if clean_response:
                self.messages.append(
                    Message(
                        role=target, content=clean_response, timestamp=datetime.now()
                    )
                )

            # Update last_seen for this AI (index of last message, not length)
            self.last_seen[target] = len(self.messages) - 1

    async def handle_confirmation(
        self, approved: bool
    ) -> AsyncGenerator[BaseEvent, None]:
        """Handle AI confirmation response (Claude or Gemini)."""
        if not self._pending_confirmation:
            return

        target = self._pending_confirmation.get("target")
        self._pending_confirmation = None

        if not target:
            return

        # Get the correct backend for this AI
        backend = self._get_backend(target)

        choice = "yes" if approved else "no"
        await backend.respond_confirmation(choice)

        # If cancelled, don't wait for response (avoid capturing rejection noise)
        if not approved:
            return

        # Wait for response
        result = await backend.wait_response(timeout=int(self._timeout))

        # B67 fix: Handle ParsedResponse (uniform format from both CLIs)
        if isinstance(result, ParsedResponse):
            if self._pending_tool_info and self._pending_tool_info.tool_type == "shell":
                if result.exit_code is not None:
                    self._pending_tool_info.exit_code = result.exit_code
                if result.shell_output is not None:
                    self._pending_tool_info.shell_output = result.shell_output
            content = result.content or ""
        elif isinstance(result, str):
            # Fallback: backends now return ParsedResponse, but keep for safety
            content = result
        else:
            content = ""

        if isinstance(result, ParsedConfirmation):
            # Chained confirmation detected - extract data from prior command first
            prior_result = result.prior_result.content if result.prior_result else ""

            # B67 fix: Use structured data if available (Claude), else parse from text (Gemini)
            prior_exit_code = result.prior_exit_code
            prior_shell_output = result.prior_shell_output

            if self._pending_tool_info and self._pending_tool_info.tool_type == "shell":
                # Use structured data from CLI if available
                if prior_exit_code is not None:
                    self._pending_tool_info.exit_code = prior_exit_code
                if prior_shell_output is not None:
                    self._pending_tool_info.shell_output = prior_shell_output

                # Fallback: parse from prior_result text (Gemini format)
                if prior_result and self._pending_tool_info.exit_code is None:
                    exit_match = re.search(
                        r"(?:Command exited with code:|Error: Exit code)\s*(\d+)",
                        prior_result,
                        re.IGNORECASE,
                    )
                    if exit_match:
                        self._pending_tool_info.exit_code = int(exit_match.group(1))

                    output_match = re.search(
                        r"__SHELL_OUTPUT__:(.+?)(?=Command exited|$)",
                        prior_result,
                        re.DOTALL,
                    )
                    if output_match:
                        self._pending_tool_info.shell_output = output_match.group(
                            1
                        ).strip()
                    elif not self._pending_tool_info.shell_output:
                        # Clean exit code line from output
                        clean_output = re.sub(
                            r"(?:Command exited with code:|Error: Exit code)\s*\d+",
                            "",
                            prior_result,
                            flags=re.IGNORECASE,
                        ).strip()
                        if clean_output:
                            self._pending_tool_info.shell_output = clean_output

            # Yield event so app.py creates widget for cmd1
            if self._pending_tool_info:
                # B55: Accumulate action context for chained commands
                self._action_contexts.append(
                    self._build_action_context(self._pending_tool_info, target)
                )
                yield CLIToolResultEvent(tool_info=self._pending_tool_info)

            # Parse the NEW confirmation (cmd2)
            context = result.context
            self._pending_confirmation = {"target": target, "context": context}
            parser = self._get_parser(target)
            _, self._pending_tool_info = parser.parse(context, debug=True)
            yield AssistantEvent(content="[Another confirmation required]")
            return

        # Clean shell metadata from displayed content (shown in widget instead)
        if content:
            # Remove __SHELL_OUTPUT__:... marker (everything after it)
            content = re.sub(r"__SHELL_OUTPUT__:.*", "", content, flags=re.DOTALL)
            # Remove exit code line
            content = re.sub(
                r"Command exited with code:\s*\d+", "", content, flags=re.IGNORECASE
            )
            content = content.strip()

        # B55: Inject all action contexts into history so other AI sees diffs
        # Keep UI content separate from history content
        ui_content = content  # For display
        history_content = content  # For other AI

        if self._pending_tool_info:
            self._action_contexts.append(
                self._build_action_context(self._pending_tool_info, target)
            )

        if self._action_contexts:
            actions_text = "\n\n".join(self._action_contexts)
            history_content = (
                f"{content}\n\n{actions_text}" if content else actions_text
            )
            self._action_contexts = []  # Reset for next chain

        if history_content:
            self.messages.append(
                Message(role=target, content=history_content, timestamp=datetime.now())
            )
            self.last_seen[target] = len(self.messages) - 1

        if ui_content:
            yield AssistantEvent(content=ui_content)

    def has_pending_confirmation(self) -> bool:
        """Check if there's a pending AI confirmation."""
        return self._pending_confirmation is not None

    def get_pending_target(self) -> str | None:
        """Get target AI for pending confirmation."""
        if self._pending_confirmation:
            return self._pending_confirmation.get("target")
        return None

    def get_pending_confirmation_context(self) -> str | None:
        """Get raw context for pending confirmation."""
        if self._pending_confirmation:
            return self._pending_confirmation.get("context")
        return None

    def get_pending_tool_info(self) -> CLIToolInfo | None:
        """Get parsed tool info for pending confirmation."""
        return self._pending_tool_info

    def get_parser_for_pending(self) -> GeminiToolParser | ClaudeToolParser | None:
        """Get parser for pending confirmation's target AI."""
        target = self.get_pending_target()
        if target:
            return self._get_parser(target)
        return None

    def clear_pending_tool_info(self) -> None:
        """Clear pending tool info after handling."""
        self._pending_tool_info = None

    def _build_action_context(self, tool_info: CLIToolInfo, target: str) -> str:
        """B55: Build readable action context for history.

        Format:
            [GEMINI ACTION: WRITE_FILE /tmp/test.py]
            + line 1
            + line 2
        """
        lines = [
            f"[{target.upper()} ACTION: {tool_info.tool_type.upper()} {tool_info.file_path}]"
        ]

        # Diff lines (cap 50)
        diff = tool_info.diff_lines[:50]
        for line_type, line_content in diff:
            prefix = line_type if line_type in {"+", "-"} else " "
            lines.append(f"{prefix} {line_content}")
        if len(tool_info.diff_lines) > 50:
            lines.append(f"... ({len(tool_info.diff_lines) - 50} more lines)")

        # Shell output (cap 20)
        if tool_info.shell_output:
            out = tool_info.shell_output.split("\n")
            lines.extend(out[:20])
            if len(out) > 20:
                lines.append(f"... ({len(out) - 20} more lines)")

        if tool_info.exit_code is not None:
            lines.append(f"Exit: {tool_info.exit_code}")

        return "\n".join(lines)

    def clear_history(self) -> None:
        """Clear conversation history but keep sessions alive."""
        self.messages.clear()
        self.last_seen = {"claude": -1, "gemini": -1}
        self._action_contexts = []  # B55: Clear stale contexts
