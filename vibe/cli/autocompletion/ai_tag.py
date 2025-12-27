from __future__ import annotations

from textual import events

from vibe.cli.autocompletion.base import CompletionResult, CompletionView
from vibe.core.autocompletion.completers import AITagCompleter

MAX_SUGGESTIONS_COUNT = 4  # Only 4 tags: @cc, @claude, @g, @gemini


class AITagController:
    """Controller for AI routing tag autocompletion (@cc, @claude, @g, @gemini)."""

    def __init__(self, completer: AITagCompleter, view: CompletionView) -> None:
        self._completer = completer
        self._view = view
        self._suggestions: list[tuple[str, str]] = []
        self._selected_index = 0

    def can_handle(self, text: str, cursor_index: int) -> bool:
        """Check if text contains @ that could be a tag (not a file path)."""
        if cursor_index < 0 or cursor_index > len(text):
            return False

        before_cursor = text[:cursor_index]
        if "@" not in before_cursor:
            return False

        at_idx = before_cursor.rfind("@")
        fragment = before_cursor[at_idx + 1 :]

        # Don't handle if there's a space after @ (tag finished)
        if " " in fragment:
            return False

        # Don't handle file paths - let PathCompletionController handle those
        if "/" in fragment or "." in fragment:
            return False

        # Only handle if fragment could match an AI tag
        # Otherwise let PathCompletionController handle file completions
        fragment_lower = fragment.lower()
        for tag in self._completer.AI_TAGS:
            if tag.startswith(fragment_lower):
                return True

        return False

    def reset(self) -> None:
        if self._suggestions:
            self._suggestions.clear()
            self._selected_index = 0
            self._view.clear_completion_suggestions()

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        if cursor_index < 0 or cursor_index > len(text):
            self.reset()
            return

        if not self.can_handle(text, cursor_index):
            self.reset()
            return

        suggestions = self._completer.get_completion_items(text, cursor_index)
        if len(suggestions) > MAX_SUGGESTIONS_COUNT:
            suggestions = suggestions[:MAX_SUGGESTIONS_COUNT]

        if suggestions:
            self._suggestions = suggestions
            self._selected_index = 0
            self._view.render_completion_suggestions(
                self._suggestions, self._selected_index
            )
        else:
            self.reset()

    def on_key(
        self, event: events.Key, text: str, cursor_index: int
    ) -> CompletionResult:
        if not self._suggestions:
            return CompletionResult.IGNORED

        match event.key:
            case "tab":
                if self._apply_selected_completion(text, cursor_index):
                    return CompletionResult.HANDLED
                return CompletionResult.IGNORED
            case "enter":
                if self._apply_selected_completion(text, cursor_index):
                    # Don't submit - user still needs to type their message
                    return CompletionResult.HANDLED
                return CompletionResult.IGNORED
            case "down":
                self._move_selection(1)
                return CompletionResult.HANDLED
            case "up":
                self._move_selection(-1)
                return CompletionResult.HANDLED
            case _:
                return CompletionResult.IGNORED

    def _move_selection(self, delta: int) -> None:
        if not self._suggestions:
            return

        count = len(self._suggestions)
        self._selected_index = (self._selected_index + delta) % count
        self._view.render_completion_suggestions(
            self._suggestions, self._selected_index
        )

    def _apply_selected_completion(self, text: str, cursor_index: int) -> bool:
        if not self._suggestions:
            return False

        tag, _ = self._suggestions[self._selected_index]
        replacement_range = self._completer.get_replacement_range(text, cursor_index)
        if replacement_range is None:
            self.reset()
            return False

        start, end = replacement_range
        self._view.replace_completion_range(start, end, tag)
        self.reset()
        return True
