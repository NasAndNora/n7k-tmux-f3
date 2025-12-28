from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_cli_detection():
    """Mock CLI detection to ensure consistent snapshots across environments.

    Problem: ContextProgress widget shows warnings when CLIs (claude, gemini, etc.)
    are not installed. CI has no CLIs → warnings shown. Local dev has CLIs → no warnings.
    This causes snapshot mismatches.

    Solution: Patch shutil.which at the module where it's used to simulate all
    dependencies being installed. This ensures identical rendering everywhere.
    """
    def fake_which(cmd: str) -> str:
        return f"/usr/bin/{cmd}"

    with patch(
        "vibe.cli.textual_ui.widgets.context_progress.shutil.which", side_effect=fake_which
    ):
        yield
