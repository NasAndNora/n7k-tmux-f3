"""Test OPS INDEX validity."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Critical entries that MUST be in the index (if missing = index outdated)
MUST_BE_IN_INDEX = [
    # Core constants
    ("core/config_path", "LOG_FILE"),
    ("core/config_path", "CONFIG_FILE"),
    ("core/utils", "CANCELLATION_TAG"),
    ("debate/routing", "TARGET_CLAUDE"),
    # Core types/enums
    ("core/config", "Backend"),
    ("core/types", "Role"),
    ("core/types", "LLMMessage"),
    # Core classes
    ("core/config", "VibeConfig"),
    ("core/agent", "Agent"),
    ("debate/agent", "DebateAgent"),
    ("cli_backends/claude/parser", "ClaudeToolParser"),
    ("cli_backends/gemini/parser", "GeminiToolParser"),
]

# Critical entries that MUST exist in code (if missing = code broken)
MUST_EXIST_IN_CODE = [
    ("vibe/core/config.py", "Backend"),
    ("vibe/core/config.py", "VibeConfig"),
    ("vibe/core/types.py", "Role"),
    ("vibe/debate/agent.py", "DebateAgent"),
    ("vibe/core/config_path.py", "LOG_FILE"),
]


@pytest.fixture
def index_content() -> str:
    index_path = Path("_OPS_INDEX.md")
    if not index_path.exists():
        pytest.skip("_OPS_INDEX.md not found")
    return index_path.read_text()


def find_name_in_ast(tree: ast.Module, name: str) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return True
    return False


@pytest.mark.parametrize("path,name", MUST_BE_IN_INDEX)
def test_critical_entry_in_index(path: str, name: str, index_content: str) -> None:
    """Critical entries must appear in the index."""
    assert path in index_content, f"Path {path} not in index"
    assert name in index_content, f"{name} not in index - run: uv run ops.py"


@pytest.mark.parametrize("filepath,name", MUST_EXIST_IN_CODE)
def test_critical_code_exists(filepath: str, name: str) -> None:
    """Critical code must exist (index points to real code)."""
    path = Path(filepath)
    assert path.exists(), f"File not found: {filepath}"
    tree = ast.parse(path.read_text())
    assert find_name_in_ast(tree, name), f"{name} not found in {filepath}"


def test_index_structure(index_content: str) -> None:
    """Index must have correct structure."""
    assert "## CONSTANTS" in index_content
    assert "## TYPES" in index_content
    assert "## FUNCTIONS" in index_content
    assert "**Legend:**" in index_content
    assert "**Rules:**" in index_content


def test_index_minimum_size(index_content: str) -> None:
    """Index must have minimum content."""
    lines = [l for l in index_content.splitlines() if l.strip() and not l.startswith(("#", "**"))]
    assert len(lines) >= 50, f"Index too small: {len(lines)} lines - run: uv run ops.py"
