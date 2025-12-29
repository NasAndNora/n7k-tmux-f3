"""Raw Claude CLI outputs for contract tests.

Captured: 29 Dec 2025
Source: tmux capture-pane from live Claude CLI sessions

These fixtures test the PUBLIC API of ClaudeToolParser:
- parse_tool_result(raw) -> (exit_code, shell_output)
- parse(raw_output) -> (text, CLIToolInfo | None)

Unused fixtures (kept as reserve for future bugs):
- TOOL_BOX_FORMAT: ╭─╮ format, covered by Gemini tests using same structure
- READ_TOOL: Read doesn't affect Ctrl+O widget (no diff), out of scope
- DELETE_TOOL: Delete not priority, no related bug
"""

# =============================================================================
# parse_tool_result() fixtures - Bash tool outputs
# =============================================================================

# Bash success (exit_code=None implicit = success)
from __future__ import annotations

BASH_SUCCESS = """● Bash(command="echo hello")
  ⎿  hello
"""

# Bash error with exit code
BASH_ERROR_EXIT_CODE = """● Bash(cat nonexistent.txt)
  ⎿  Error: Exit code 1
     cat: nonexistent.txt: No such file or directory
"""

# Bash multiline output
BASH_MULTILINE_OUTPUT = """● Bash(command="ls -la")
  ⎿  total 8
     drwxr-xr-x  2 user user 4096 Jan  1 00:00 .
     drwxr-xr-x 10 user user 4096 Jan  1 00:00 ..
"""

# Multiple tools (parser must stop at 2nd tool)
BASH_MULTIPLE_TOOLS = """● Bash(command="echo first")
  ⎿  first

● Bash(command="echo second")
  ⎿  second
"""

# No Bash tool in output
NO_BASH_TOOL = """I'll help you with that task.
Here's my response without any tool usage.
"""

# Bash error with multiline stderr
BASH_ERROR_MULTILINE = """● Bash(command="invalid_command")
  ⎿  Error: Exit code 127
     bash: invalid_command: command not found
     Please check the command and try again.
"""

# =============================================================================
# parse() fixtures - Tool headers and boxes
# =============================================================================

# Write file with ╌ separator (B57 pattern) - CREATE new file
WRITE_FILE_CREATE = """● Write(testing.py)

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Create file testing.py
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 hello
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to create testing.py?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. Type here to tell Claude what to do differently

 Esc to cancel
"""

# Edit file with diff (B57 separator) - UPDATE existing file
EDIT_FILE_UPDATE = """● Update(testest.py)

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Edit file testest.py
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 1 -hello
 1   No newline at end of file
 2 +ligne1
 3 +ligne2
 4 +ligne3
 5 +ligne4
 6 +ligne5
 7 +ligne6
 8   No newline at end of file
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to make this edit to testest.py?
 ❯ 1. Yes
"""

# Tool with box format (╭─╮ │ │ ╰─╯)
TOOL_BOX_FORMAT = """╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ✓  Edit vibe/cli_backends/claude/parser.py                                                                                                           │
│                                                                                                                                                      │
│  42 +    EDIT_SEPARATOR = re.compile(r"^╌+$")                                                                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
"""

# Read tool (no file modification)
READ_TOOL = """● Read(file="config.py")
  ⎿  Read 50 lines from config.py
"""

# Delete tool
DELETE_TOOL = """● Delete(file="temp.py")
  ⎿  Deleted temp.py
"""
