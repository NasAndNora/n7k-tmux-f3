"""Tests for Claude parser contract.

Tests PUBLIC API only:
- parse_tool_result(raw) -> (exit_code, shell_output)
- parse(raw_output) -> (text, CLIToolInfo | None)

Each test protects against CLI format changes.
If a test fails, check the regex in vibe/cli_backends/claude/parser.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vibe.cli_backends.claude.parser import ClaudeToolParser

from tests.cli_backends.fixtures.claude_outputs import (
    BASH_ERROR_EXIT_CODE,
    BASH_ERROR_MULTILINE,
    BASH_MULTILINE_OUTPUT,
    BASH_MULTIPLE_TOOLS,
    BASH_SUCCESS,
    EDIT_FILE_UPDATE,
    NO_BASH_TOOL,
    WRITE_FILE_CREATE,
)


# =============================================================================
# parse_tool_result() tests
# =============================================================================


class TestClaudeParseToolResult:
    """Tests for parse_tool_result() - extracts exit_code and shell_output."""

    def test_bash_success_no_exit_code(self, claude_parser: ClaudeToolParser):
        """
        Contrat: Success = no explicit exit code in output
        Si fail: Parser expects exit code where there is none
        """
        exit_code, output = claude_parser.parse_tool_result(BASH_SUCCESS)

        assert exit_code is None
        assert output is not None
        assert "hello" in output

    def test_bash_error_exit_code_extracted(self, claude_parser: ClaudeToolParser):
        """
        Contrat: "Error: Exit code X" -> exit_code = X
        Si fail: Widget always shows success (blue) even on error
        Pattern: EXIT_CODE_PATTERN in parser.py line 70-72
        """
        exit_code, output = claude_parser.parse_tool_result(BASH_ERROR_EXIT_CODE)

        assert exit_code == 1
        assert output is not None
        assert "No such file" in output

    def test_bash_multiline_output_captured(self, claude_parser: ClaudeToolParser):
        """
        Contrat: Multi-line shell output fully captured
        Si fail: Only first line of output shown
        """
        exit_code, output = claude_parser.parse_tool_result(BASH_MULTILINE_OUTPUT)

        assert exit_code is None
        assert output is not None
        assert "total 8" in output
        assert "drwxr-xr-x" in output

    def test_bash_error_multiline_stderr(self, claude_parser: ClaudeToolParser):
        """
        Contrat: Error with multi-line stderr fully captured
        Si fail: Stderr truncated, user doesn't see full error
        """
        exit_code, output = claude_parser.parse_tool_result(BASH_ERROR_MULTILINE)

        assert exit_code == 127
        assert output is not None
        assert "command not found" in output

    def test_multiple_tools_stops_at_second(self, claude_parser: ClaudeToolParser):
        """
        Contrat: Only first tool result extracted
        Si fail: Output from multiple tools mixed together
        """
        exit_code, output = claude_parser.parse_tool_result(BASH_MULTIPLE_TOOLS)

        assert output is not None
        assert "first" in output
        assert "second" not in output

    def test_no_bash_returns_none(self, claude_parser: ClaudeToolParser):
        """
        Contrat: No Bash tool -> (None, None)
        Si fail: Parser crashes or returns garbage
        """
        exit_code, output = claude_parser.parse_tool_result(NO_BASH_TOOL)

        assert exit_code is None
        assert output is None


# =============================================================================
# parse() tests
# =============================================================================


class TestClaudeParse:
    """Tests for parse() - extracts CLIToolInfo from raw output."""

    def test_write_file_header_detected(self, claude_parser: ClaudeToolParser):
        """
        Contrat: "● Write(file.py)" -> tool_type = write_file
        Si fail: File creation not detected, no widget shown
        Pattern: TOOL_HEADER in parser.py line 43-45
        """
        text, tool_info = claude_parser.parse(WRITE_FILE_CREATE)

        assert tool_info is not None
        assert tool_info.tool_type == "write_file"
        assert tool_info.file_path == "testing.py"

    def test_edit_file_header_detected(self, claude_parser: ClaudeToolParser):
        """
        Contrat: "● Update(file.py)" -> tool_type = edit
        Si fail: File edits not detected, no widget shown
        """
        text, tool_info = claude_parser.parse(EDIT_FILE_UPDATE)

        assert tool_info is not None
        assert tool_info.tool_type == "edit"
        assert tool_info.file_path == "testest.py"

    def test_edit_separator_b57_parsed(self, claude_parser: ClaudeToolParser):
        """
        Contrat: ╌╌╌ separator marks diff boundaries (B57)
        Si fail: B57 regression - diff content not extracted
        Pattern: EDIT_SEPARATOR in parser.py line 39
        """
        text, tool_info = claude_parser.parse(EDIT_FILE_UPDATE)

        assert tool_info is not None
        assert tool_info.diff_lines is not None
        assert len(tool_info.diff_lines) > 0
        # Check diff contains expected changes
        diff_content = "".join(line for _, line in tool_info.diff_lines)
        assert "ligne1" in diff_content or "hello" in diff_content

    def test_diff_lines_have_markers(self, claude_parser: ClaudeToolParser):
        """
        Contrat: Diff lines have +/- markers
        Si fail: Diff shown without add/remove indicators
        Pattern: LINE_ADDED, LINE_REMOVED in parser.py line 55-56
        """
        text, tool_info = claude_parser.parse(EDIT_FILE_UPDATE)

        assert tool_info is not None
        assert tool_info.diff_lines is not None

        markers = [marker for marker, _ in tool_info.diff_lines]
        # Should have at least one + or - marker
        assert "+" in markers or "-" in markers

    def test_is_new_file_filesystem_check_b51(
        self, claude_parser: ClaudeToolParser, tmp_path: Path
    ):
        """
        Contrat: is_new_file based on filesystem, not tool_type (B51)
        Si fail: B51 regression - "Created" shown for existing file
        Location: parser.py line 380-387
        """
        # Create a file that exists
        existing_file = tmp_path / "existing.py"
        existing_file.write_text("content")

        # Create fixture with existing file path
        raw = f"""● Write({existing_file})

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Create file {existing_file}
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 new content
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
"""
        text, tool_info = claude_parser.parse(raw)

        assert tool_info is not None
        # File exists -> is_new_file should be False
        assert tool_info.is_new_file is False

    def test_is_new_file_true_for_nonexistent(
        self, claude_parser: ClaudeToolParser, tmp_path: Path
    ):
        """
        Contrat: is_new_file=True for file that doesn't exist
        Si fail: "Modified" shown for new file creation
        """
        nonexistent = tmp_path / "does_not_exist.py"

        raw = f"""● Write({nonexistent})

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Create file {nonexistent}
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 new content
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
"""
        text, tool_info = claude_parser.parse(raw)

        assert tool_info is not None
        # File doesn't exist -> is_new_file should be True
        assert tool_info.is_new_file is True
