"""Tests for ContextProgress widget dependency checking."""

from __future__ import annotations

import shutil

from vibe.cli.textual_ui.widgets.context_progress import ContextProgress


class TestCheckDependencies:
    """Test _check_dependencies method."""

    def test_warns_when_claude_cli_missing(self, monkeypatch):
        """Verify warning when claude CLI is not installed."""
        monkeypatch.setattr(
            shutil, "which", lambda cmd: None if cmd == "claude" else f"/usr/bin/{cmd}"
        )
        widget = ContextProgress()
        warnings = widget._check_dependencies()
        assert "❗ claude CLI required" in warnings

    def test_warns_when_gemini_cli_missing(self, monkeypatch):
        """Verify warning when gemini CLI is not installed."""
        monkeypatch.setattr(
            shutil, "which", lambda cmd: None if cmd == "gemini" else f"/usr/bin/{cmd}"
        )
        widget = ContextProgress()
        warnings = widget._check_dependencies()
        assert "❗ gemini CLI required" in warnings

    def test_no_cli_warnings_when_all_installed(self, monkeypatch):
        """Verify no CLI warnings when all CLIs are present."""
        monkeypatch.setattr(shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
        widget = ContextProgress()
        warnings = widget._check_dependencies()
        assert "❗ claude CLI required" not in warnings
        assert "❗ gemini CLI required" not in warnings
