"""CLI Tool widgets for Claude/Gemini/GPT/Codex results.

These AIs are accessed via tmux CLI parsing, not API.
This module provides widgets compatible with ToolResultMessage interface
for Ctrl+O toggle support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import difflib
from pathlib import Path
import re

from textual.app import ComposeResult
from textual.widgets import Static

from vibe.cli.textual_ui.widgets.tool_widgets import ToolResultWidget


@dataclass
class CLIToolInfo:
    """Parsed tool info from CLI-based AIs (Claude, Gemini, etc).

    Created by parsers (ClaudeToolParser, GeminiToolParser) from tmux output.
    Used by CLIToolResultWidget for rendering.

    Attributes:
        tool_type: "shell", "write_file", "edit", "read_file"
        file_path: File path, or "cmd [cwd] (desc)" for shell
        diff_lines: List of ("+"/"-"/" ", content) tuples
        exit_code: Shell command exit code (None if not shell or not executed)
        shell_output: Shell command output
        is_new_file: True if file didn't exist before write_file
    """

    tool_type: str
    file_path: str
    description: str = ""
    diff_lines: list[tuple[str, str]] = field(default_factory=list)
    exit_code: int | None = None
    shell_output: str | None = None
    is_new_file: bool = False

    @property
    def tool_name(self) -> str:
        """Alias for Ctrl+O toggle compatibility."""
        return self.tool_type


class CLIToolResultWidget(ToolResultWidget):
    """Widget for CLI-based AI tool results.

    Inherits from ToolResultWidget for:
    - _hint() method for "(ctrl+o to expand/collapse)"
    - collapsed/data pattern

    Custom CSS class .cli-tool-result (not .tool-result-widget) for proper styling.
    Custom rendering for shell (output multi-lines not supported by native).

    Compatible with event_handler.tool_results[] for Ctrl+O toggle.
    Required interface: .collapsed, .render_result(), .event.tool_name
    """

    def __init__(self, tool_info: CLIToolInfo, collapsed: bool = True) -> None:
        self.tool_info = tool_info

        # Build message
        self._message = self._build_message()

        # Check error state
        self._is_error = (
            tool_info.tool_type == "shell"
            and tool_info.exit_code is not None
            and tool_info.exit_code != 0
        )

        # Build data dict for parent
        data = {"message": self._message}
        super().__init__(data, collapsed=collapsed)

        # CSS: Use .cli-tool-result (width:100%, background) instead of
        # .tool-result-widget (width:auto) - CLI widgets are not nested in ToolResultMessage
        self.remove_class("tool-result-widget")
        self.add_class("cli-tool-result")

        # For Ctrl+O toggle compatibility (event_handler checks .event.tool_name)
        self.event = tool_info

        # Error styling
        if self._is_error:
            self.add_class("error-text")

    def _build_message(self) -> str:
        """Build display message based on tool type."""
        ti = self.tool_info
        filename = Path(ti.file_path).name if ti.file_path else ""

        if ti.tool_type == "shell":
            if ti.exit_code is not None and ti.exit_code != 0:
                return f"Error (code {ti.exit_code})"
            return "Success"

        elif ti.tool_type == "write_file":
            if ti.is_new_file:
                return f"Created {filename}"
            return f"Modified {filename}"

        elif ti.tool_type == "edit":
            return f"Modified {filename}"

        elif ti.tool_type == "read_file":
            lines = len(ti.diff_lines) if ti.diff_lines else 0
            return f"Read {lines} lines from {filename}"

        return "Completed"

    def compose(self) -> ComposeResult:
        """Render widget content."""
        # Header with message
        if self.collapsed:
            yield Static(f"{self._message} {self._hint()}", markup=False)
            return
        else:
            yield Static(self._message, markup=False)

        # Expanded content based on tool type
        if self.tool_info.tool_type == "shell":
            yield from self._render_shell()
        elif self.tool_info.tool_type in {"write_file", "edit"}:
            yield from self._render_diff()
        # read_file: no extra content (message is enough)

    def _render_shell(self) -> ComposeResult:
        """Render shell command + output."""
        ti = self.tool_info

        # Extract command from file_path (format: "cmd [cwd ...] (desc)")
        raw = ti.file_path
        match = re.match(r"^(.+?)\s*\[", raw)
        command = match.group(1).strip() if match else raw

        yield Static("")
        yield Static(f"$ {command}", markup=False, classes="shell-command")

        # Output with truncation
        if ti.shell_output:
            MAX_LINES = 200
            lines = ti.shell_output.split("\n")

            if len(lines) > MAX_LINES:
                truncated = "\n".join(lines[:MAX_LINES])
                yield Static(truncated, markup=False, classes="shell-output")
                yield Static(
                    f"... ({len(lines) - MAX_LINES} more lines)",
                    markup=False,
                    classes="shell-truncated",
                )
            else:
                yield Static(ti.shell_output, markup=False, classes="shell-output")

    def _render_diff(self) -> ComposeResult:
        """Render diff (same pattern as SearchReplaceResultWidget)."""
        if not self.tool_info.diff_lines:
            return

        # Convert to unified diff format
        diff_lines = self._to_unified_diff()

        if not diff_lines:
            return

        yield Static("")

        for line in diff_lines:
            if line.startswith("---") or line.startswith("+++"):
                yield Static(line, markup=False, classes="diff-header")
            elif line.startswith("-"):
                yield Static(line, markup=False, classes="diff-removed")
            elif line.startswith("+"):
                yield Static(line, markup=False, classes="diff-added")
            elif line.startswith("@@"):
                yield Static(line, markup=False, classes="diff-range")
            else:
                yield Static(line, markup=False, classes="diff-context")

    def _to_unified_diff(self) -> list[str]:
        """Convert diff_lines to unified diff format."""
        if not self.tool_info.diff_lines:
            return []

        search_lines: list[str] = []
        replace_lines: list[str] = []

        for line_type, content in self.tool_info.diff_lines:
            if line_type == "-":
                search_lines.append(content)
            elif line_type == "+":
                replace_lines.append(content)
            else:
                search_lines.append(content)
                replace_lines.append(content)

        diff = difflib.unified_diff(search_lines, replace_lines, lineterm="", n=2)
        return list(diff)[2:]  # Skip file headers (--- / +++)

    async def render_result(self) -> None:
        """Re-render when collapsed state changes (Ctrl+O toggle)."""
        await self.remove_children()
        await self.recompose()
