"""Shared fixtures for CLI backends tests."""

from __future__ import annotations

import pytest

from vibe.cli_backends.claude.parser import ClaudeToolParser
from vibe.cli_backends.gemini.parser import GeminiToolParser


@pytest.fixture
def claude_parser() -> ClaudeToolParser:
    """Create Claude parser instance."""
    return ClaudeToolParser()


@pytest.fixture
def gemini_parser() -> GeminiToolParser:
    """Create Gemini parser instance."""
    return GeminiToolParser()
