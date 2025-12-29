"""Tests for Gemini parser contract.

Tests PUBLIC API only:
- parse_tool_result(content) -> (exit_code, shell_output)
- parse(raw_output) -> (text, CLIToolInfo | None)

Each test protects against CLI format changes.
If a test fails, check the regex in vibe/cli_backends/gemini/parser.py
"""

from __future__ import annotations

from pathlib import Path

from tests.cli_backends.fixtures.gemini_outputs import (
    EDIT_COMPLETED,
    NO_SHELL_TOOL,
    READFILE_TOOL,
    SHELL_ERROR_NO_EXIT_CODE_B66,
    SHELL_EXIT_CODE,
    SHELL_SUCCESS,
    SHELL_WITH_MARKER,
    WRITEFILE_CONFIRMATION,
)
from vibe.cli_backends.gemini.parser import GeminiToolParser

# =============================================================================
# parse_tool_result() tests
# =============================================================================


class TestGeminiParseToolResult:
    """Tests for parse_tool_result() - extracts exit_code and shell_output."""

    def test_exit_code_extracted(self, gemini_parser: GeminiToolParser):
        """Contrat: "Command exited with code: X" -> exit_code = X
        Si fail: Widget always shows success even on error
        Pattern: EXIT_CODE_PATTERN in parser.py line 62
        """
        exit_code, shell_output = gemini_parser.parse_tool_result(SHELL_EXIT_CODE)

        assert exit_code == 0

    def test_shell_output_marker_extracted(self, gemini_parser: GeminiToolParser):
        """Contrat: __SHELL_OUTPUT__:content -> shell_output = content
        Si fail: Shell output lost, widget shows nothing
        Pattern: __SHELL_OUTPUT__ marker injected by session
        """
        exit_code, shell_output = gemini_parser.parse_tool_result(SHELL_WITH_MARKER)

        assert exit_code == 0
        assert shell_output is not None
        assert "hello world" in shell_output

    def test_no_shell_returns_none(self, gemini_parser: GeminiToolParser):
        """Contrat: No shell marker -> (None, None)
        Si fail: Parser crashes or returns garbage
        """
        exit_code, shell_output = gemini_parser.parse_tool_result(NO_SHELL_TOOL)

        assert exit_code is None
        assert shell_output is None

    def test_implicit_failure_no_exit_code_b66(self, gemini_parser: GeminiToolParser):
        """Contrat B66: Implicit failure (cat nonexistent) -> exit_code = None
        Si fail: N/A - this documents a CLI limitation
        Note: Gemini CLI doesn't always emit exit codes for failures
        """
        exit_code, shell_output = gemini_parser.parse_tool_result(
            SHELL_ERROR_NO_EXIT_CODE_B66
        )

        # B66: No exit code emitted by Gemini CLI for this error
        # This is a known CLI limitation, not a parser bug
        assert exit_code is None


# =============================================================================
# parse() tests
# =============================================================================


class TestGeminiParse:
    """Tests for parse() - extracts CLIToolInfo from raw output."""

    def test_writefile_header_inside_box(self, gemini_parser: GeminiToolParser):
        """Contrat: "? WriteFile file.py" inside box -> tool_type = write_file
        Si fail: File creation not detected, no widget shown
        Pattern: TOOL_HEADER in parser.py line 39-42
        """
        text, tool_info = gemini_parser.parse(WRITEFILE_CONFIRMATION)

        assert tool_info is not None
        assert tool_info.tool_type == "write_file"
        # WriteFile "Writing to testest.py" -> file_path should contain testest.py
        assert "testest.py" in tool_info.file_path

    def test_shell_header_detected(self, gemini_parser: GeminiToolParser):
        """Contrat: "✓ Shell cmd" -> tool_type = shell
        Si fail: Shell commands not detected
        """
        text, tool_info = gemini_parser.parse(SHELL_SUCCESS)

        assert tool_info is not None
        assert tool_info.tool_type == "shell"

    def test_edit_header_detected(self, gemini_parser: GeminiToolParser):
        """Contrat: "✓ Edit file.py" -> tool_type = edit
        Si fail: File edits not detected
        """
        text, tool_info = gemini_parser.parse(EDIT_COMPLETED)

        assert tool_info is not None
        assert tool_info.tool_type == "edit"
        assert "config.py" in tool_info.file_path

    def test_readfile_header_detected(self, gemini_parser: GeminiToolParser):
        """Contrat: "✓ ReadFile file.py" -> tool_type = read_file
        Si fail: Read operations not detected
        """
        text, tool_info = gemini_parser.parse(READFILE_TOOL)

        assert tool_info is not None
        assert tool_info.tool_type == "read_file"

    def test_diff_lines_extracted(self, gemini_parser: GeminiToolParser):
        """Contrat: Diff lines with +/- markers extracted
        Si fail: Diff content lost, widget shows nothing
        Pattern: LINE_ADDED, LINE_REMOVED in parser.py line 45-46
        """
        text, tool_info = gemini_parser.parse(EDIT_COMPLETED)

        assert tool_info is not None
        assert tool_info.diff_lines is not None
        assert len(tool_info.diff_lines) > 0

        markers = [marker for marker, _ in tool_info.diff_lines]
        assert "+" in markers or "-" in markers

    def test_box_content_stripped(self, gemini_parser: GeminiToolParser):
        """Contrat: │ content │ -> content (box borders stripped)
        Si fail: Raw │ characters in widget
        Pattern: BOX_LINE in parser.py line 35
        """
        text, tool_info = gemini_parser.parse(SHELL_SUCCESS)

        # Text should not contain box characters
        assert "│" not in text or text.count("│") == 0

    def test_is_new_file_filesystem_check_b51(
        self, gemini_parser: GeminiToolParser, tmp_path: Path
    ):
        """Contrat: is_new_file based on filesystem (B51)
        Si fail: B51 regression - "Created" shown for existing file
        Location: parser.py line 250-257
        """
        existing_file = tmp_path / "existing.py"
        existing_file.write_text("content")

        raw = f"""╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ?  WriteFile Writing to {existing_file}                                                                                                                                                            │
│                                                                                                                                                                                                      │
│ 1 new content                                                                                                                                                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
"""
        text, tool_info = gemini_parser.parse(raw)

        assert tool_info is not None
        assert tool_info.is_new_file is False

    def test_is_new_file_true_for_nonexistent(
        self, gemini_parser: GeminiToolParser, tmp_path: Path
    ):
        """Contrat: is_new_file=True for file that doesn't exist
        Si fail: "Modified" shown for new file creation
        """
        nonexistent = tmp_path / "does_not_exist.py"

        raw = f"""╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ?  WriteFile Writing to {nonexistent}                                                                                                                                                              │
│                                                                                                                                                                                                      │
│ 1 new content                                                                                                                                                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
"""
        text, tool_info = gemini_parser.parse(raw)

        assert tool_info is not None
        assert tool_info.is_new_file is True
