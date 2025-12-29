"""Tests for Claude parser - R5.

Tests parse_tool_result() in parser.py.
"""

from __future__ import annotations

import pytest

from vibe.cli_backends.claude.parser import ClaudeToolParser

# Fixture: Bash tool success (exit_code=None implicit = success)
FIXTURE_BASH_SUCCESS = """
● Bash(command="echo hello")
  ⎿  hello
"""

# Fixture: Bash tool error
FIXTURE_BASH_ERROR = """
● Bash(command="cat nonexistent.txt")
  ⎿  Error: Exit code 1
     cat: nonexistent.txt: No such file or directory
"""

# Fixture: Multiple tools (doit s'arrêter au 2ème)
FIXTURE_MULTIPLE_TOOLS = """
● Bash(command="echo first")
  ⎿  first

● Bash(command="echo second")
  ⎿  second
"""

# Fixture: No Bash tool
FIXTURE_NO_BASH = """
I'll help you with that task.
Here's my response without any tool usage.
"""

# Fixture: Bash with multiline output
FIXTURE_BASH_MULTILINE = """
● Bash(command="ls -la")
  ⎿  total 8
     drwxr-xr-x  2 user user 4096 Jan  1 00:00 .
     drwxr-xr-x 10 user user 4096 Jan  1 00:00 ..
"""

# Fixture: Bash error with multiline stderr
FIXTURE_BASH_ERROR_MULTILINE = """
● Bash(command="invalid_command")
  ⎿  Error: Exit code 127
     bash: invalid_command: command not found
     Please check the command and try again.
"""


class TestParserParseToolResult:
    """Test parse_tool_result() in parser.py."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance for testing."""
        return ClaudeToolParser()

    def test_bash_success(self, parser: ClaudeToolParser):
        """Success case: no exit code, output captured."""
        exit_code, output = parser.parse_tool_result(FIXTURE_BASH_SUCCESS)
        assert exit_code is None  # Success = no explicit code
        assert output is not None
        assert "hello" in output

    def test_bash_error(self, parser: ClaudeToolParser):
        """Error case: exit code captured, stderr captured."""
        exit_code, output = parser.parse_tool_result(FIXTURE_BASH_ERROR)
        assert exit_code == 1
        assert output is not None
        assert "No such file" in output

    def test_multiple_tools_stops_at_second(self, parser: ClaudeToolParser):
        """Multiple tools: only first tool result extracted."""
        exit_code, output = parser.parse_tool_result(FIXTURE_MULTIPLE_TOOLS)
        assert output is not None
        assert "first" in output
        assert "second" not in output  # Must stop at 2nd tool

    def test_no_bash_tool(self, parser: ClaudeToolParser):
        """No Bash tool: returns (None, None)."""
        exit_code, output = parser.parse_tool_result(FIXTURE_NO_BASH)
        assert exit_code is None
        assert output is None

    def test_bash_multiline_success(self, parser: ClaudeToolParser):
        """Multiline output: all lines captured."""
        exit_code, output = parser.parse_tool_result(FIXTURE_BASH_MULTILINE)
        assert exit_code is None
        assert output is not None
        assert "total 8" in output
        assert "drwxr-xr-x" in output

    def test_bash_error_multiline(self, parser: ClaudeToolParser):
        """Error with multiline stderr: exit code and all stderr captured."""
        exit_code, output = parser.parse_tool_result(FIXTURE_BASH_ERROR_MULTILINE)
        assert exit_code == 127
        assert output is not None
        assert "command not found" in output
