"""Conversation history management for multi-AI debate."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from vibe.debate.routing import Message, build_context


class ConversationHistory:
    """Manages conversation history between multiple AIs."""

    def __init__(self, max_messages: int = 100) -> None:
        self._max_messages = max_messages
        self._messages: list[Message] = []
        # -1 means "never responded", will see all messages from index 0
        self._last_seen: dict[str, int] = {"claude": -1, "gemini": -1}

    @property
    def messages(self) -> list[Message]:
        """Get all messages."""
        return self._messages

    @property
    def last_seen(self) -> dict[str, int]:
        """Get last seen indices per AI."""
        return self._last_seen

    def add_message(self, role: str, content: str, is_ephemeral: bool = False) -> None:
        """Add a message to history.

        Args:
            role: "user", "claude", or "gemini"
            content: Message content
            is_ephemeral: If True, message won't be included in context
        """
        msg = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            is_ephemeral=is_ephemeral,
        )
        self._messages.append(msg)

        # Trim if over limit
        if len(self._messages) > self._max_messages:
            excess = len(self._messages) - self._max_messages
            self._messages = self._messages[excess:]
            # Adjust last_seen indices
            for ai in self._last_seen:
                self._last_seen[ai] = max(0, self._last_seen[ai] - excess)

    def get_context_for(self, target: str, limit: int = 5) -> str:
        """Get context string for target AI (messages it hasn't seen).

        Args:
            target: "claude" or "gemini"
            limit: Max messages to include

        Returns:
            Formatted context string
        """
        return build_context(self._messages, target, self._last_seen, limit)

    def mark_seen(self, target: str) -> None:
        """Mark all current messages as seen by target AI."""
        self._last_seen[target] = len(self._messages) - 1 if self._messages else -1

    def clear(self) -> None:
        """Clear all messages and reset indices."""
        self._messages.clear()
        self._last_seen = {"claude": -1, "gemini": -1}

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self) -> Iterator[Message]:
        return iter(self._messages)
