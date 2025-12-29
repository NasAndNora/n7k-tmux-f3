"""Raw Gemini CLI outputs for contract tests.

Captured: 29 Dec 2025
Source: tmux capture-pane from live Gemini CLI sessions

These fixtures test the PUBLIC API of GeminiToolParser:
- parse_tool_result(content) -> (exit_code, shell_output)
- parse(raw_output) -> (text, CLIToolInfo | None)

Unused fixtures (kept as reserve for future bugs):
- HEADER_OUTSIDE_BOX: Alternative format, covered by WRITEFILE_CONFIRMATION
"""

# =============================================================================
# parse_tool_result() fixtures - Shell tool outputs
# =============================================================================

# Shell with explicit exit code
SHELL_EXIT_CODE = """╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ✓  Shell echo hello                                                                                                                                                                                     │
│                                                                                                                                                                                                      │
│ hello                                                                                                                                                                                                │
│ Command exited with code: 0                                                                                                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
"""

# Shell error - B66: NO EXIT CODE for implicit failure!
SHELL_ERROR_NO_EXIT_CODE_B66 = """╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ✓  Shell cat nonexistent.txt [current working directory /home/nasf/dev/projects/mistral-vibe-unit-tests] (Attempting to cat a nonexistent file to demonstrate error handling.)                       │
│                                                                                                                                                                                                      │
│ cat: nonexistent.txt: No such file or directory                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
  Responding with gemini-2.5-flash
✦ cat nonexistent.txt exécuté. Le fichier n'existe pas.
"""

# Shell with __SHELL_OUTPUT__ marker (injected by session)
SHELL_WITH_MARKER = """Some response text
__SHELL_OUTPUT__:hello world
More text here
Command exited with code: 0
"""

# No shell in output
NO_SHELL_TOOL = """✦ I'll help you with that task.
Here's my response without any tool usage.
"""

# =============================================================================
# parse() fixtures - Tool headers and boxes
# =============================================================================

# Shell confirmation (pending)
SHELL_CONFIRMATION_PENDING = """╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ?  Shell cat nonexistent.txt [current working directory /home/nasf/dev/projects/mistral-vibe-unit-tests] (Attempting to cat a nonexistent file to demonstrate error handling.)                     ← │
│                                                                                                                                                                                                      │
│ cat nonexistent.txt                                                                                                                                                                                  │
│                                                                                                                                                                                                      │
│ Allow execution of: 'cat'?                                                                                                                                                                           │
│                                                                                                                                                                                                      │
│ ● 1. Allow once                                                                                                                                                                                      │
│   2. Allow for this session                                                                                                                                                                          │
│   3. No, suggest changes (esc)                                                                                                                                                                       │
│                                                                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
⠏ Waiting for user confirmation...
"""

# WriteFile confirmation
WRITEFILE_CONFIRMATION = """╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ?  WriteFile Writing to testest.py                                                                                                                                                                 ← │
│                                                                                                                                                                                                      │
│ 1 hello                                                                                                                                                                                              │
│                                                                                                                                                                                                      │
│ Apply this change?                                                                                                                                                                                   │
│                                                                                                                                                                                                      │
│ ● 1. Allow once                                                                                                                                                                                      │
│   2. Allow for this session                                                                                                                                                                          │
│   3. Modify with external editor                                                                                                                                                                     │
│   4. No, suggest changes (esc)                                                                                                                                                                       │
│                                                                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
⠏ Waiting for user confirmation...
"""

# Response marker
RESPONSE_WITH_MARKER = """✦ Compris. J'obéis, tu es précis. Qu'est-ce que tu veux faire?
"""

# Edit tool completed
EDIT_COMPLETED = """╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ✓  Edit config.py                                                                                                                                                                                    │
│                                                                                                                                                                                                      │
│ 10 -old_value = 1                                                                                                                                                                                    │
│ 10 +new_value = 2                                                                                                                                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
"""

# ReadFile tool
READFILE_TOOL = """╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ✓  ReadFile config.py                                                                                                                                                                                │
│                                                                                                                                                                                                      │
│ 1 # Configuration file                                                                                                                                                                               │
│ 2 DEBUG = True                                                                                                                                                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
"""

# Shell success with exit code 0
SHELL_SUCCESS = """╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ✓  Shell echo hello                                                                                                                                                                                  │
│                                                                                                                                                                                                      │
│ hello                                                                                                                                                                                                │
│ Command exited with code: 0                                                                                                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
"""

# Header outside box format (? marker)
HEADER_OUTSIDE_BOX = """?  WriteFile test.py
╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ 1 print("hello")                                                                                                                                                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
"""
