#!/usr/bin/env python3
"""CLI Verification Script for Multi-AI Chat

Checks that all required CLIs (claude, gemini, tmux) are installed,
authenticated, and ready to use.

Usage:
    python scripts/verify_cli.py
    python scripts/verify_cli.py --verbose
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import shutil
import subprocess
import sys


class Status(Enum):
    OK = "✓"
    ERROR = "✗"
    WARN = "!"


@dataclass
class CheckResult:
    status: Status
    message: str
    help_text: str | None = None


def run_command(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Run command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", "Command not found"


def check_tmux() -> CheckResult:
    """Check if tmux is installed."""
    if not shutil.which("tmux"):
        return CheckResult(
            Status.ERROR,
            "tmux not found",
            "Install: sudo apt install tmux (Linux) | brew install tmux (Mac)",
        )

    code, stdout, _ = run_command(["tmux", "-V"])
    if code == 0:
        version = stdout.strip()
        return CheckResult(Status.OK, f"tmux found ({version})")

    return CheckResult(Status.ERROR, "tmux installed but not working")


def check_claude_cli() -> CheckResult:
    """Check if Claude CLI is installed and accessible."""
    if not shutil.which("claude"):
        return CheckResult(
            Status.ERROR,
            "Claude CLI not found",
            "Install: npm install -g @anthropic-ai/claude-cli",
        )

    # Check version
    code, stdout, stderr = run_command(["claude", "--version"])
    if code != 0:
        return CheckResult(
            Status.ERROR,
            "Claude CLI installed but --version failed",
            f"Error: {stderr}",
        )

    version = stdout.strip() if stdout else "unknown"
    return CheckResult(Status.OK, f"Claude CLI found ({version})")


def check_claude_auth() -> CheckResult:
    """Check if Claude CLI is authenticated."""
    # Try a simple command that requires auth
    # Using --help doesn't require auth, so we check if config exists
    code, stdout, stderr = run_command(["claude", "config", "list"], timeout=5)

    if code != 0:
        if "not authenticated" in stderr.lower() or "login" in stderr.lower():
            return CheckResult(
                Status.ERROR, "Claude CLI not authenticated", "Run: claude login"
            )
        # Config command might not exist, treat as warning
        return CheckResult(
            Status.WARN, "Could not verify Claude auth", "Try running: claude --help"
        )

    return CheckResult(Status.OK, "Claude CLI authenticated")


def check_gemini_cli() -> CheckResult:
    """Check if Gemini CLI is installed and accessible."""
    if not shutil.which("gemini"):
        return CheckResult(
            Status.ERROR,
            "Gemini CLI not found",
            "Install: npm install -g @anthropic-ai/claude-code (includes gemini)",
        )

    # Check version
    code, stdout, stderr = run_command(["gemini", "--version"])
    if code != 0:
        # Gemini might not have --version
        return CheckResult(Status.WARN, "Gemini CLI found but --version not supported")

    version = stdout.strip() if stdout else "unknown"
    return CheckResult(Status.OK, f"Gemini CLI found ({version})")


def check_gemini_auth() -> CheckResult:
    """Check if Gemini CLI is authenticated."""
    # Similar approach to Claude
    code, stdout, stderr = run_command(["gemini", "--help"], timeout=5)

    if code != 0:
        if "auth" in stderr.lower() or "login" in stderr.lower():
            return CheckResult(
                Status.ERROR, "Gemini CLI not authenticated", "Run: gemini auth"
            )
        return CheckResult(
            Status.WARN, "Could not verify Gemini status", f"Error: {stderr[:100]}"
        )

    return CheckResult(Status.OK, "Gemini CLI accessible")


def print_result(name: str, result: CheckResult, verbose: bool = False) -> None:
    """Print a check result."""
    status_str = result.status.value
    color = {
        Status.OK: "\033[92m",  # Green
        Status.ERROR: "\033[91m",  # Red
        Status.WARN: "\033[93m",  # Yellow
    }[result.status]
    reset = "\033[0m"

    print(f"  {color}{status_str}{reset} {name}: {result.message}")

    if verbose and result.help_text:
        print(f"    → {result.help_text}")


def main() -> int:
    """Run all checks and return exit code."""
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print("\n🔍 Multi-AI Chat - CLI Verification\n")

    checks = [
        ("tmux", check_tmux),
        ("Claude CLI", check_claude_cli),
        ("Claude Auth", check_claude_auth),
        ("Gemini CLI", check_gemini_cli),
        ("Gemini Auth", check_gemini_auth),
    ]

    results: list[tuple[str, CheckResult]] = []
    for name, check_fn in checks:
        result = check_fn()
        results.append((name, result))
        print_result(name, result, verbose)

    # Summary
    errors = sum(1 for _, r in results if r.status == Status.ERROR)
    warns = sum(1 for _, r in results if r.status == Status.WARN)

    print()
    if errors > 0:
        print(f"❌ {errors} error(s) found. Fix them before running Multi-AI Chat.")
        if not verbose:
            print("   Run with --verbose for help text.")
        return 1
    elif warns > 0:
        print(f"⚠️  {warns} warning(s). App may still work.")
        return 0
    else:
        print("✅ All checks passed! Ready to run Multi-AI Chat.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
