"""Shared models for CLI backends transport.

These models handle data transport between session and agent layers.
NOT for UI (use CLIToolInfo in widgets/ai_tools.py for that).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParsedResponse:
    """Response from CLI session after command execution.

    Used by session.wait_response() to return structured data to agent.
    """

    content: str
    exit_code: int | None = None
    shell_output: str | None = None


@dataclass
class ParsedConfirmation:
    """Confirmation request from CLI requiring user approval.

    Used when CLI detects a confirmation prompt (e.g., file overwrite).
    """

    context: str
    prior_result: ParsedResponse | None = None
    prior_exit_code: int | None = None
    prior_shell_output: str | None = None
