"""Tests for Claude session extraction functions."""

from __future__ import annotations


class TestExtractResponseNoiseFiltering:
    """Tests for noise pattern filtering in _extract_response()."""

    def test_noise_patterns_filtered(self):
        """
        Contrat: Les noise patterns (Thinking, ctrl-c, etc.) sont filtrés.
        Si fail: Noise visible dans le chat utilisateur.
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
        """
        Contrat: Les noise patterns sont case-insensitive.
        Si fail: 'THINKING' ou 'thinking' passent à travers.
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
