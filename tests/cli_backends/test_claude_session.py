"""Tests for Claude session extraction functions."""

from __future__ import annotations


class TestExtractResponseNoiseFiltering:
    """Tests for noise pattern filtering in _extract_response()."""

    def test_noise_patterns_filtered(self):
        """Contract: Noise patterns (Thinking, ctrl-c, etc.) are filtered.
        If fail: Noise visible in user chat.
        """
        from vibe.cli_backends.claude.session import ClaudeSessionTmux

        # Simule un buffer tmux avec noise + contenu réel
        raw_with_noise = """● Here is the response.
This is the actual content.
Thinking about the problem.
More content here.
ctrl-c to cancel
Final content."""

        # Instancie sans __init__ (on teste juste _extract_response)
        session = ClaudeSessionTmux.__new__(ClaudeSessionTmux)

        # Act
        result, idx = session._extract_response(raw_with_noise)

        # Assert - noise filtré
        assert "Thinking" not in result, "Noise 'Thinking' should be filtered"
        assert "ctrl-c" not in result, "Noise 'ctrl-c' should be filtered"

        # Assert - contenu réel présent
        assert "actual content" in result, "Real content should be present"
        assert "More content here" in result, "Real content should be present"
        assert "Final content" in result, "Real content should be present"

    def test_noise_patterns_case_insensitive(self):
        """Contract: Noise patterns are case-insensitive.
        If fail: 'THINKING' or 'thinking' pass through filter.
        """
        from vibe.cli_backends.claude.session import ClaudeSessionTmux

        raw = """● Response start.
Real content here.
THINKING loudly.
thinking quietly.
More real content."""

        session = ClaudeSessionTmux.__new__(ClaudeSessionTmux)
        result, idx = session._extract_response(raw)

        assert "THINKING" not in result, "Uppercase noise should be filtered"
        assert "thinking" not in result, "Lowercase noise should be filtered"
        assert "Real content" in result
        assert "More real content" in result

    def test_empty_buffer_returns_empty(self):
        """Contract: Empty or whitespace-only buffer returns ("", -1).
        If fail: Stale content may leak through.
        """
        from vibe.cli_backends.claude.session import ClaudeSessionTmux

        session = ClaudeSessionTmux.__new__(ClaudeSessionTmux)

        # Empty string
        result, idx = session._extract_response("")
        assert result == ""
        assert idx == -1

        # Whitespace only
        result, idx = session._extract_response("   \n\t  \n  ")
        assert result == ""
        assert idx == -1

    def test_no_marker_returns_empty(self):
        """Contract: Buffer without ● marker returns ("", -1).
        If fail: Content before first marker incorrectly treated as response.
        """
        from vibe.cli_backends.claude.session import ClaudeSessionTmux

        session = ClaudeSessionTmux.__new__(ClaudeSessionTmux)

        raw = """Some content without marker.
Another line here.
No bullet point anywhere."""

        result, idx = session._extract_response(raw)
        assert result == ""
        assert idx == -1
