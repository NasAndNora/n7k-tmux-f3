# tmux_config.py - Constantes centralisees pour sessions tmux
#
# TODO: Ces constantes ne sont pas utilisées actuellement.
# Les sessions (claude/session.py, gemini/session.py) hardcodent les valeurs.
# Refactoring à faire: brancher ces constantes dans les sessions.
from __future__ import annotations

# Tmux dimensions
TMUX_WIDTH = 150
TMUX_HEIGHT = 50

# Timeouts (secondes)
DEFAULT_TIMEOUT = 120
POLL_INTERVAL = 2

# Claude
CLAUDE_SESSION = "claude_session"
CLAUDE_CMD = "claude --dangerously-skip-permissions"
CLAUDE_MARKERS = ["●"]

# Gemini
GEMINI_SESSION = "gemini_session"
GEMINI_CMD = "gemini"
GEMINI_MARKERS = ["✦", "✧"]
