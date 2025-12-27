"""F6: Startup screen with intro animation."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Static

# Full text on one line
WELCOME_TEXT = "THE ONE - Multi-Agent Chat - by Nas & Nora"
BUTTON_TEXT = "Press Enter ↵"

# Gradient colors (orange theme - user can modify later)
GRADIENT_COLORS = [
    "#ff6b00",
    "#ff7b00",
    "#ff8c00",
    "#ff9d00",
    "#ffae00",
    "#ffbf00",
    "#ffae00",
    "#ff9d00",
    "#ff8c00",
    "#ff7b00",
]


def _apply_gradient(text: str, offset: int) -> str:
    """Apply oscillating gradient to text."""
    result = []
    for i, char in enumerate(text):
        color = GRADIENT_COLORS[(i + offset) % len(GRADIENT_COLORS)]
        result.append(f"[bold {color}]{char}[/]")
    return "".join(result)


class StartupScreen(Screen):
    """Startup intro screen with typing animation."""

    CSS_PATH = "startup.tcss"

    def __init__(self) -> None:
        super().__init__()
        self._char_index = 0
        self._gradient_offset = 0
        self._typing_done = False
        self._paused = False

        # Timers
        self._typing_timer: Timer | None = None
        self._gradient_timer: Timer | None = None

        # Widgets
        self._welcome_text: Static
        self._enter_hint: Static

        # Button typing
        self._button_char_index = 0
        self._button_typing_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="startup-container"):
            with Center():
                yield Static("", id="startup-text")
            with Center():
                yield Static("", id="startup-enter-hint", classes="hidden")

    def on_mount(self) -> None:
        self._welcome_text = self.query_one("#startup-text", Static)
        self._enter_hint = self.query_one("#startup-enter-hint", Static)

        # Start typing animation (70ms per char for ~3s total)
        self._typing_timer = self.set_interval(0.07, self._type_next_char)
        # Start gradient animation
        self._gradient_timer = self.set_interval(0.12, self._animate_gradient)
        self.focus()

    def _type_next_char(self) -> None:
        """Type next character with gradient."""
        if self._char_index >= len(WELCOME_TEXT):
            if not self._typing_done:
                self._typing_done = True
                if self._typing_timer:
                    self._typing_timer.stop()
                self.set_timer(0.5, self._show_button)
            return

        self._char_index += 1
        self._welcome_text.update(
            _apply_gradient(WELCOME_TEXT[: self._char_index], self._gradient_offset)
        )

    def _animate_gradient(self) -> None:
        """Animate gradient on text."""
        self._gradient_offset = (self._gradient_offset + 1) % len(GRADIENT_COLORS)
        if self._char_index > 0:
            self._welcome_text.update(
                _apply_gradient(WELCOME_TEXT[: self._char_index], self._gradient_offset)
            )

    def _show_button(self) -> None:
        """Show 'Press any key' with typing effect."""
        self._enter_hint.remove_class("hidden")
        self._button_typing_timer = self.set_interval(0.06, self._type_button_char)

    def _type_button_char(self) -> None:
        """Type button text character by character."""
        if self._button_char_index >= len(BUTTON_TEXT):
            if self._button_typing_timer:
                self._button_typing_timer.stop()
            return
        self._button_char_index += 1
        self._enter_hint.update(f"[dim]{BUTTON_TEXT[: self._button_char_index]}[/]")

    def on_key(self, event: Key) -> None:
        """Dismiss screen on any key press after animation is done."""
        if self._typing_done:
            event.stop()
            self.dismiss()
