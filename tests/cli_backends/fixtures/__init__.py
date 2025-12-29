"""CLI backends test fixtures.

Raw outputs captured from live Claude/Gemini CLI sessions.
"""

from __future__ import annotations

from tests.cli_backends.fixtures.claude_outputs import (
    BASH_ERROR_EXIT_CODE,
    BASH_ERROR_MULTILINE,
    BASH_MULTILINE_OUTPUT,
    BASH_MULTIPLE_TOOLS,
    BASH_SUCCESS,
    DELETE_TOOL,
    EDIT_FILE_UPDATE,
    NO_BASH_TOOL,
    READ_TOOL,
    TOOL_BOX_FORMAT,
    WRITE_FILE_CREATE,
)
from tests.cli_backends.fixtures.gemini_outputs import (
    EDIT_COMPLETED,
    HEADER_OUTSIDE_BOX,
    NO_SHELL_TOOL,
    READFILE_TOOL,
    RESPONSE_WITH_MARKER,
    SHELL_CONFIRMATION_PENDING,
    SHELL_ERROR_NO_EXIT_CODE_B66,
    SHELL_EXIT_CODE,
    SHELL_SUCCESS,
    SHELL_WITH_MARKER,
    WRITEFILE_CONFIRMATION,
)

__all__ = [
    "BASH_ERROR_EXIT_CODE",
    "BASH_ERROR_MULTILINE",
    "BASH_MULTILINE_OUTPUT",
    "BASH_MULTIPLE_TOOLS",
    # Claude - parse_tool_result()
    "BASH_SUCCESS",
    "DELETE_TOOL",
    "EDIT_COMPLETED",
    "EDIT_FILE_UPDATE",
    "HEADER_OUTSIDE_BOX",
    "NO_BASH_TOOL",
    "NO_SHELL_TOOL",
    "READFILE_TOOL",
    "READ_TOOL",
    "RESPONSE_WITH_MARKER",
    # Gemini - parse()
    "SHELL_CONFIRMATION_PENDING",
    "SHELL_ERROR_NO_EXIT_CODE_B66",
    # Gemini - parse_tool_result()
    "SHELL_EXIT_CODE",
    "SHELL_SUCCESS",
    "SHELL_WITH_MARKER",
    "TOOL_BOX_FORMAT",
    "WRITEFILE_CONFIRMATION",
    # Claude - parse()
    "WRITE_FILE_CREATE",
]
