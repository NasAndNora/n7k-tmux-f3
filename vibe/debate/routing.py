"""Routing logic for multi-AI debate - parses @tags and builds context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

# Target constants - single source of truth
TARGET_CLAUDE = "claude"
TARGET_GEMINI = "gemini"


def escape_for_cli(text: str) -> str:
    """DEPRECATED: Escape special characters to prevent CLI interpretation.

    B49 fix: No longer needed with tmux send-keys -l (literal mode).
    Kept for backwards compatibility if code mutates to shell=True in future.
    """
    text = text.replace("$", "\\$")
    text = text.replace("`", "\\`")
    text = text.replace("'", "'\\''")  # Escape single quotes
    return text


ROUTING_TAGS = {
    "@cc": TARGET_CLAUDE,
    "@claude": TARGET_CLAUDE,
    "@g": TARGET_GEMINI,
    "@gemini": TARGET_GEMINI,
}

TAG_PATTERN = re.compile(r"(?:^|\s)@(cc|claude|g|gemini)(?=\s|$)", re.IGNORECASE)


def parse_routing_tag(text: str) -> tuple[str | None, str]:
    """Parse routing tag from message.

    Returns (target, clean_message):
    - target: "claude" or "gemini" or None if no tag
    - clean_message: message with tag removed
    """
    if not text:
        return None, ""

    text = text.strip()
    match = TAG_PATTERN.search(text)

    if not match:
        return None, text

    tag = f"@{match.group(1).lower()}"
    target = ROUTING_TAGS.get(tag)

    # Remove the tag from message
    clean = TAG_PATTERN.sub("", text).strip()
    # Clean up extra spaces
    clean = re.sub(r"\s+", " ", clean).strip()

    return target, clean


@dataclass
class Message:
    """Single message in conversation history."""

    role: str  # "user" | "claude" | "gemini"
    content: str
    timestamp: datetime
    is_ephemeral: bool = False


def build_context(
    messages: list[Message], target: str, last_seen: dict[str, int], limit: int = 5
) -> str:
    """Build context string for target AI from messages it hasn't seen.

    Args:
        messages: Full conversation history
        target: "claude" or "gemini"
        last_seen: {"claude": idx, "gemini": idx} - last message index each AI saw
        limit: Max messages to include

    Returns:
        Formatted context string
    """
    if not messages:
        return ""

    # last_seen_idx is the index of the last message this AI saw (its own last response)
    # -1 means never responded, so should see all messages
    last_seen_idx = last_seen.get(target, -1)

    # Take everything AFTER last_seen_idx
    new_messages = messages[last_seen_idx + 1 :]

    # Cap to limit if too many
    if len(new_messages) > limit:
        new_messages = new_messages[-limit:]

    # Filter out ephemeral messages
    relevant = [m for m in new_messages if not m.is_ephemeral]

    if not relevant:
        return ""

    # B49 fix: Explicit header so AI understands this is chat, not shell
    # Double newline between each person for readability
    lines = ["[Chat context, reply to last USER message]"]
    for msg in relevant:
        role_label = _role_to_label(msg.role, is_current=False)
        lines.append(f"{role_label} {msg.content}")

    # Join: header + first msg with single \n, then double \n between messages
    header = lines[0]
    msg_lines = lines[1:]
    return header + "\n" + "\n\n".join(msg_lines)


def _role_to_label(role: str, is_current: bool = False) -> str:
    """Convert role to display label.

    B49 fix: Explicit names (CLAUDE/GEMINI) instead of generic "AI".
    Format: '[Context]' header + 'USER said' / 'CLAUDE said' / 'GEMINI said'
    """
    if role == "user":
        return "USER asks" if is_current else "USER said"
    elif role == "claude":
        return "CLAUDE said"
    elif role == "gemini":
        return "GEMINI said"
    # Fallback for unknown roles
    return f"{role.upper()} said"
