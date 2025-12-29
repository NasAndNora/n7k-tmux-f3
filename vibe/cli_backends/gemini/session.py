from __future__ import annotations

from collections.abc import Callable
import logging
import re
import subprocess
import time
from typing import Any

from vibe.cli_backends.gemini.parser import GeminiToolParser
from vibe.cli_backends.models import ParsedConfirmation, ParsedResponse


class GeminiSessionTmux:
    def __init__(self, session_name: str = "gemini_session") -> None:
        self.session_name = session_name
        self._parser = GeminiToolParser()

    def _capture_pane(self, lines: int = 500) -> str:
        """Capture tmux pane content (plain text, no ANSI)."""
        cmd = ["tmux", "capture-pane", "-t", self.session_name, "-p", "-S", f"-{lines}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout

    def start(self) -> None:
        subprocess.run(
            ["tmux", "kill-session", "-t", self.session_name], capture_output=True
        )
        # B49: Use gemini-2.5-flash instead of flash-lite (more stable, less shell mode bugs)
        # B69: Set SHELL=/bin/bash to prevent user shell config pollution (banners, hooks)
        subprocess.run([
            "tmux",
            "new-session",
            "-d",
            "-s",
            self.session_name,
            "-x",
            "200",
            "-y",
            "50",
            "env",
            "SHELL=/bin/bash",
            "gemini",
            "--model",
            "gemini-2.5-flash",
        ])

        # Wait for Gemini to be ready (F8: raise on timeout, 15s max)
        for _ in range(15):
            time.sleep(1)
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", self.session_name, "-p"],
                capture_output=True,
                text=True,
            )
            if "Type your message" in result.stdout:
                return
        raise RuntimeError("Gemini CLI timeout. Check: gemini auth status")

    def ask(
        self,
        prompt: str,
        timeout: int = 120,
        on_update: Callable[[str], Any] | None = None,
    ) -> str | dict:
        try:
            check = subprocess.run(
                ["tmux", "has-session", "-t", self.session_name], capture_output=True
            )
            if check.returncode != 0:
                return "❌ Tmux session dead. Click Restart."

            before = self._capture_pane()
            responses_before = before.count("✦") + before.count("✧")

            # B49 fix: load-buffer + paste-buffer with -p (bracketed paste) and -r (preserve newlines)
            subprocess.run(["tmux", "load-buffer", "-"], input=prompt.encode("utf-8"))
            subprocess.run([
                "tmux",
                "paste-buffer",
                "-p",
                "-r",
                "-t",
                self.session_name,
            ])
            time.sleep(0.3)
            subprocess.run(["tmux", "send-keys", "-t", self.session_name, "Enter"])

            start_time = time.time()
            spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            last_output = ""  # B44/B53: Cache to skip parse if buffer unchanged

            while time.time() - start_time < timeout:
                time.sleep(1)

                # TODO B44/B53: Measure polling performance (capture + parse)
                t_poll_start = time.time()
                output = self._capture_pane()
                t_capture = time.time()

                if on_update:
                    # B44/B53 fix: Skip parse if buffer unchanged (AI thinking, no new content)
                    if output == last_output:
                        continue

                    partial = self._extract_response(output, responses_before)
                    t_parse = time.time()

                    # Log if polling took > 500ms (potential UI freeze cause)
                    poll_time = t_parse - t_poll_start
                    if poll_time > 0.5:
                        logging.warning(
                            f"B44/B53: Slow polling cycle: {poll_time:.2f}s (capture: {t_capture - t_poll_start:.2f}s, parse: {t_parse - t_capture:.2f}s)"
                        )

                    on_update((partial or "") + " ▌")
                    last_output = output  # Update cache

                if (
                    "Waiting for user confirmation" in output
                    or "Apply this change?" in output
                ):
                    # TODO B44: Log before returning confirmation to trace freeze
                    logging.debug(
                        "B44: Gemini confirmation detected, returning to agent"
                    )
                    return ParsedConfirmation(
                        context=self._extract_confirmation_context(output)
                    )

                responses_now = output.count("✦") + output.count("✧")

                if responses_now > responses_before and "Type your message" in output:
                    if (
                        not any(s in output for s in spinners)
                        and "esc to cancel" not in output
                    ):
                        time.sleep(1)
                        output = self._capture_pane()
                        return self._extract_response(output, responses_before)

            return "⚠️ Timeout"

        except FileNotFoundError:
            return "❌ tmux not found. Install: sudo apt install tmux"
        except Exception as e:
            return f"❌ Error: {e!s}"

    def _extract_response(self, raw: str, skip_count: int = 0) -> str:
        """Extract response keeping tool boxes for parser to handle.

        NOTE: Box characters (╭─│╰) are KEPT in output so GeminiToolParser
        can extract file paths and diffs. Only noise patterns are stripped.
        """
        noise_patterns = [
            r"^───+$",
            r"Type your message",
            r"esc to cancel",
            r"auto \|",
            r"sandbox",
            r"GEMINI\.md",
            r"^Using:",
            r"YOLO mode",
            r"^╭─+╮?$",
            r"^╰─+╯?$",  # Input box borders
            r"^│\s*>\s*Type your",
            r"^│\s*$",  # Empty box lines
            # Tool execution noise (B49 fix attempt)
            r"Responding with gemini",
            r"Waiting for user confirmation",
            r"Request cancelled",
            r"^│\s*[✓⊷\-\+\?]\s*(ReadFile|WriteFile|EditFile|DeleteFile|Shell)",
            r"^│\s*\d+\s*[\-\+]",  # Diff lines inside boxes
            # NOTE: Tool box chars still captured in shell_output_lines section
        ]

        lines = raw.strip().split("\n")
        all_responses = []
        current_response = []
        in_response = False

        # B12 fix: Find response markers to scope shell box search
        # Gemini format: ╭box with exit code╯ ✦ response text
        response_markers = []
        for i, line in enumerate(lines):
            if line.strip().startswith("✦") or line.strip().startswith("✧"):
                response_markers.append(i)

        last_response_idx = response_markers[-1] if response_markers else 0

        # B20 fix: Only search between second-last and last ✦ (current response zone)
        # Prevents old shell boxes from polluting new messages
        exit_code_line = None
        shell_output_lines = []
        if len(response_markers) > 1:
            search_start = response_markers[-2]
        else:
            search_start = max(0, last_response_idx - 210)
        in_shell_box = False

        for line in lines[search_start : last_response_idx + 1]:
            stripped = line.strip()
            # Clean box chars for content check
            clean_line = re.sub(r"^[│\s]+", "", stripped)
            clean_line = re.sub(r"[│\s]+$", "", clean_line)

            # Detect shell box start - reset output for each new box
            if "✓" in stripped and "Shell" in stripped:
                in_shell_box = True
                shell_output_lines = []  # Reset for this box
                exit_code_line = None  # Reset exit code too
                continue

            # Detect box end
            if (
                stripped.startswith("╰")
                or stripped.startswith("✦")
                or stripped.startswith("✧")
            ):
                in_shell_box = False
                continue

            if in_shell_box and clean_line:
                if (
                    "Command exited with code:" in clean_line
                    or "Error: Exit code" in clean_line
                ):
                    exit_code_line = clean_line
                elif not clean_line.startswith("╭"):
                    # This is output content
                    shell_output_lines.append(clean_line)

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("✦") or stripped.startswith("✧"):
                if current_response:
                    all_responses.append("\n".join(current_response))
                text = re.sub(r"^[✦✧]\s*", "", stripped)
                current_response = [text] if text else []
                in_response = True
            elif in_response:
                if "Type your message" in stripped:
                    if current_response:
                        all_responses.append("\n".join(current_response))
                        current_response = []
                    in_response = False
                else:
                    is_noise = any(
                        re.search(p, stripped, re.IGNORECASE) for p in noise_patterns
                    )
                    if not is_noise and stripped:
                        current_response.append(stripped)

        # Only add current_response if we're actually in a response (after ✦)
        if current_response and in_response:
            all_responses.append("\n".join(current_response))

        result = ""
        if len(all_responses) > skip_count:
            result = all_responses[-1]

        # B12/B13 fix: For shell, add markers for widget (but keep text response)
        if shell_output_lines:
            shell_marker = f"__SHELL_OUTPUT__:{chr(10).join(shell_output_lines)}"
            if exit_code_line:
                shell_marker = f"{shell_marker}\n{exit_code_line}"
            # Append marker AFTER result so regex cleanup preserves text response
            result = f"{result}\n{shell_marker}" if result else shell_marker
        elif exit_code_line and result:
            result = f"{result}\n{exit_code_line}"

        return result

    def _extract_confirmation_context(self, raw: str) -> str:
        """Extract raw confirmation context WITH box characters intact.

        The parser needs box chars (╭─│╰) to identify tool boxes and extract diffs.
        """
        lines = raw.strip().split("\n")

        # Find the LAST tool pattern (not the first)
        tool_patterns = ["WriteFile", "Shell", "EditFile", "DeleteFile"]
        last_tool_idx = -1
        for i, line in enumerate(lines):
            is_tool_line = any(p in line for p in tool_patterns) or (
                "?" in line and "Edit" in line
            )
            if is_tool_line:
                last_tool_idx = i

        if last_tool_idx == -1:
            return "Action pending confirmation"

        # Extract from last tool pattern to "Apply this change?" - KEEP RAW
        context_lines = []
        for line in lines[last_tool_idx:]:
            if "Apply this change?" in line:
                break
            # Keep line as-is (preserve box characters for parser)
            if line.strip():
                context_lines.append(line.strip())

        return (
            "\n".join(context_lines) if context_lines else "Action pending confirmation"
        )

    def respond_confirmation(self, choice: str) -> None:
        if choice == "yes":
            subprocess.run(["tmux", "send-keys", "-t", self.session_name, "Enter"])
        else:
            subprocess.run(["tmux", "send-keys", "-t", self.session_name, "Escape"])

    def wait_response(
        self, timeout: int = 120, on_update: Callable[[str], Any] | None = None
    ) -> str | dict:
        start_time = time.time()
        spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        last_partial = ""
        last_output = ""  # B44/B53: Cache to skip parse if buffer unchanged

        before = self._capture_pane()
        responses_before = before.count("✦") + before.count("✧")

        while time.time() - start_time < timeout:
            time.sleep(1)
            output = self._capture_pane()

            if on_update:
                # B44/B53 fix: Skip parse if buffer unchanged (AI thinking, no new content)
                if output == last_output:
                    continue

                partial = self._extract_response(output, responses_before - 1)
                if partial and partial != last_partial:
                    on_update(partial + " ▌")
                    last_partial = partial

                last_output = output  # Update cache

            if (
                "Waiting for user confirmation" in output
                or "Apply this change?" in output
            ):
                # Extract result before confirmation (for chained commands)
                prior_result = self._extract_response(output, responses_before - 1)
                # Parse structured data (align with Claude)
                prior_exit_code, prior_shell_output = (
                    self._parser.parse_tool_result(prior_result)
                    if prior_result
                    else (None, None)
                )
                return ParsedConfirmation(
                    context=self._extract_confirmation_context(output),
                    prior_result=ParsedResponse(content=prior_result)
                    if prior_result
                    else None,
                    prior_exit_code=prior_exit_code,
                    prior_shell_output=prior_shell_output,
                )

            if "Type your message" in output:
                if (
                    not any(s in output for s in spinners)
                    and "esc to cancel" not in output
                ):
                    content = self._extract_response(output, responses_before - 1)

                    # Parse structured data from content (uses parser)
                    exit_code, shell_output = self._parser.parse_tool_result(content)
                    # Clean content (remove markers)
                    if isinstance(content, str):
                        content = re.sub(
                            r"__SHELL_OUTPUT__:.*", "", content, flags=re.DOTALL
                        ).strip()

                    return ParsedResponse(
                        content=content, exit_code=exit_code, shell_output=shell_output
                    )

        return ParsedResponse(content="⚠️ Timeout")

    def close(self) -> None:
        subprocess.run(["tmux", "send-keys", "-t", self.session_name, "/exit", "Enter"])
        time.sleep(1)
        subprocess.run(
            ["tmux", "kill-session", "-t", self.session_name], capture_output=True
        )
