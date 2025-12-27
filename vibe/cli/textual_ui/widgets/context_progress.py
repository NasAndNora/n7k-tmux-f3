from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
from typing import Any

from textual.reactive import reactive
from textual.widgets import Static


@dataclass
class TokenState:
    max_tokens: int = 0
    current_tokens: int = 0


class ContextProgress(Static):
    tokens = reactive(TokenState())

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    # F17: Token display disabled, show dependency warnings instead
    # def watch_tokens(self, new_state: TokenState) -> None:
    #     if new_state.max_tokens == 0:
    #         self.update("")
    #         return
    #     percentage = min(
    #         100, int((new_state.current_tokens / new_state.max_tokens) * 100)
    #     )
    #     text = f"{percentage}% of {new_state.max_tokens // 1000}k tokens"
    #     self.update(text)

    def watch_tokens(self, new_state: TokenState) -> None:
        """F17: Ignore token updates."""
        pass

    def on_mount(self) -> None:
        """F17: Check dependencies and display warnings."""
        warnings = self._check_dependencies()
        if warnings:
            self.update("[yellow]" + " · ".join(warnings) + "[/]")

    def _check_dependencies(self) -> list[str]:
        """Check system dependencies."""
        warnings = []
        if not shutil.which("tmux"):
            warnings.append("❗ tmux required")
        node = shutil.which("node")
        if not node:
            warnings.append("❗ Node.js >= v20 required")
        else:
            try:
                result = subprocess.run(
                    [node, "--version"], capture_output=True, text=True
                )
                version = int(result.stdout.strip().lstrip("v").split(".")[0])
                if version < 20:  # Node.js minimum version
                    warnings.append(f"❗ Node.js >= v20 required (found v{version})")
            except Exception:
                pass
        if not shutil.which("claude"):
            warnings.append("❗ claude CLI required")
        if not shutil.which("gemini"):
            warnings.append("❗ gemini CLI required")
        return warnings
