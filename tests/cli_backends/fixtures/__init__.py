"""CLI backends test fixtures.

Raw outputs captured from live Claude/Gemini CLI sessions.
"""

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
    # Claude - parse_tool_result()
    "BASH_SUCCESS",
    "BASH_ERROR_EXIT_CODE",
    "BASH_ERROR_MULTILINE",
    "BASH_MULTILINE_OUTPUT",
    "BASH_MULTIPLE_TOOLS",
    "NO_BASH_TOOL",
    # Claude - parse()
    "WRITE_FILE_CREATE",
    "EDIT_FILE_UPDATE",
    "TOOL_BOX_FORMAT",
    "READ_TOOL",
    "DELETE_TOOL",
    # Gemini - parse_tool_result()
    "SHELL_EXIT_CODE",
    "SHELL_ERROR_NO_EXIT_CODE_B66",
    "SHELL_WITH_MARKER",
    "NO_SHELL_TOOL",
    # Gemini - parse()
    "SHELL_CONFIRMATION_PENDING",
    "WRITEFILE_CONFIRMATION",
    "RESPONSE_WITH_MARKER",
    "EDIT_COMPLETED",
    "READFILE_TOOL",
    "SHELL_SUCCESS",
    "HEADER_OUTSIDE_BOX",
]
