"""CUSTOM WIDGET - Multi-AI Debate Fork
=====================================
Target selector for routing messages to AI backends.
Designed to be extensible for future AI additions (Codex, Mistral, etc.)
Not part of original Mistral Vibe.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Static

from vibe.debate.routing import TARGET_CLAUDE, TARGET_GEMINI


@dataclass(frozen=True)
class AITarget:
    """Definition of an AI target for the selector."""

    id: str
    label: str
    icon: str
    key: str
    css_class: str


# Available targets - add new AI here
TARGETS: list[AITarget] = [
    AITarget(TARGET_CLAUDE, "Claude", "●", "c", "target-btn-claude"),
    AITarget(TARGET_GEMINI, "Gemini", "✦", "g", "target-btn-gemini"),
    # Future: AITarget(TARGET_CODEX, "Codex", "◆", "x", "target-btn-codex"),
    # Future: AITarget(TARGET_MISTRAL, "Mistral", "▲", "m", "target-btn-mistral"),
]


class TargetSelector(Static):
    """Compact button bar for choosing AI target. Extensible for future AI."""

    BINDINGS = [
        Binding("c", "select('claude')", "Claude", show=False),
        Binding("g", "select('gemini')", "Gemini", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
        # Future: Binding("x", "select('codex')", "Codex", show=False),
        # Future: Binding("m", "select('mistral')", "Mistral", show=False),
    ]

    class TargetSelected(Message):
        """Posted when user selects an AI target."""

        def __init__(self, target: str, user_message: str) -> None:
            super().__init__()
            self.target = target
            self.user_message = user_message

    class SelectionCancelled(Message):
        """Posted when user cancels selection."""

        pass

    def __init__(self, user_msg: str, disabled_targets: set[str] | None = None) -> None:
        super().__init__(classes="target-selector")
        self._user_msg = user_msg
        self._disabled_targets = disabled_targets or set()

    def compose(self) -> ComposeResult:
        with Horizontal(classes="target-selector-buttons"):
            for target in TARGETS:
                btn = Button(
                    f"{target.icon} {target.label}",
                    id=f"btn-{target.id}",
                    classes=f"target-btn {target.css_class}",
                )
                # B59: Disable button if backend is dead
                if target.id in self._disabled_targets:
                    btn.disabled = True
                yield btn

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id and btn_id.startswith("btn-"):
            target_id = btn_id[4:]  # Remove "btn-" prefix
            self._select(target_id)

    def action_select(self, target: str) -> None:
        """Action handler for keyboard shortcuts."""
        self._select(target)

    def action_cancel(self) -> None:
        self.post_message(self.SelectionCancelled())

    def _select(self, target: str) -> None:
        # B59: Ignore selection if target is disabled
        if target in self._disabled_targets:
            return
        self.post_message(self.TargetSelected(target, self._user_msg))
