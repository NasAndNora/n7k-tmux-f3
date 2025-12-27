from __future__ import annotations

from collections.abc import Callable
import logging
import re
import subprocess
import time
from typing import Any


class ClaudeSessionTmux:
    def __init__(
        self, session_name: str = "claude_session", model: str = "haiku"
    ) -> None:
        self.session_name = session_name
        self.model = model

    def start(self) -> None:
        subprocess.run(
            ["tmux", "kill-session", "-t", self.session_name], capture_output=True
        )
        subprocess.run([
            "tmux",
            "new-session",
            "-d",
            "-s",
            self.session_name,
            "-x",
            "150",
            "-y",
            "50",
            "claude",
            "--permission-mode",
            "default",
            "--model",
            self.model,
        ])

        # Wait for Claude to be ready (F8: raise on timeout, 15s max)
        for _ in range(15):
            time.sleep(1)
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", self.session_name, "-p"],
                capture_output=True,
                text=True,
            )
            if "Yes, I accept" in result.stdout:
                subprocess.run(["tmux", "send-keys", "-t", self.session_name, "Down"])
                time.sleep(0.2)
                subprocess.run(["tmux", "send-keys", "-t", self.session_name, "Enter"])
                continue
            if ">" in result.stdout:
                return
        raise RuntimeError("Claude CLI timeout. Check: claude auth status")

    def ask(
        self,
        prompt: str,
        timeout: int = 120,
        on_update: Callable[[str], Any] | None = None,
    ) -> str | dict[str, str]:
        try:
            check = subprocess.run(
                ["tmux", "has-session", "-t", self.session_name], capture_output=True
            )
            if check.returncode != 0:
                return "❌ Tmux session dead. Click Restart."

            # B35 fix: Capture the CONTENT of old message marker line BEFORE sending
            # This handles buffer scroll when user sends message during AI response
            # B39 fix: Also count total markers to detect new response with identical content
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", self.session_name, "-p", "-S", "-500"],
                capture_output=True,
                text=True,
            )
            old_lines = result.stdout.strip().split("\n")
            _, old_text_idx = self._extract_response(result.stdout, 0)
            # Store the actual line content, not just index (index shifts when buffer scrolls)
            last_marker_line = (
                old_lines[old_text_idx].strip()
                if old_text_idx >= 0 and old_text_idx < len(old_lines)
                else ""
            )
            # B39 fix: Count markers to detect new response even if content is identical
            last_marker_count = sum(
                1 for line in old_lines if line.strip().startswith("●")
            )

            # TODO: Remove debug logging before prod
            with open("/tmp/claude_polling_debug.txt", "a") as f:
                f.write(f"\n{'=' * 60}\n")
                f.write(f"=== NEW TURN: {prompt[:50]}... ===\n")
                f.write(f"{'=' * 60}\n")
                f.write(
                    f"Initial last_marker_line: {repr(last_marker_line[:80]) if last_marker_line else 'EMPTY'}\n"
                )

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
            last_output = ""  # B44/B53: Cache to skip parse if buffer unchanged

            while time.time() - start_time < timeout:
                time.sleep(1)

                # TODO B44/B53: Measure polling performance (capture + parse)
                t_poll_start = time.time()
                result = subprocess.run(
                    [
                        "tmux",
                        "capture-pane",
                        "-t",
                        self.session_name,
                        "-p",
                        "-S",
                        "-500",
                    ],
                    capture_output=True,
                    text=True,
                )
                output = result.stdout
                t_capture = time.time()

                if on_update:
                    # B44/B53 fix: Skip parse if buffer unchanged (AI thinking, no new content)
                    if output == last_output:
                        continue

                    current_lines = output.strip().split("\n")
                    partial, current_text_idx = self._extract_response(output, 0)
                    t_parse = time.time()

                    # Log if polling took > 500ms (potential UI freeze cause)
                    poll_time = t_parse - t_poll_start
                    if poll_time > 0.5:
                        logging.warning(
                            f"B44/B53: Slow polling cycle: {poll_time:.2f}s (capture: {t_capture - t_poll_start:.2f}s, parse: {t_parse - t_capture:.2f}s)"
                        )

                    # B35 fix: Compare marker line CONTENT, not index (handles buffer scroll)
                    current_marker_line = (
                        current_lines[current_text_idx].strip()
                        if current_text_idx >= 0
                        and current_text_idx < len(current_lines)
                        else ""
                    )
                    # B39 fix: Also check if marker count increased (new response with identical content)
                    current_marker_count = sum(
                        1 for line in current_lines if line.strip().startswith("●")
                    )
                    is_new_message = (
                        current_marker_line != last_marker_line
                        or current_marker_count > last_marker_count
                    )

                    # TODO: Remove debug logging before prod
                    has_spinner = "✻" in output
                    will_stream = partial and is_new_message
                    with open("/tmp/claude_polling_debug.txt", "a") as f:
                        f.write(f"\n--- POLL {time.time() - start_time:.1f}s ---\n")
                        f.write(f"has_spinner: {has_spinner}\n")
                        f.write(
                            f"last_marker: {repr(last_marker_line[:50]) if last_marker_line else 'EMPTY'}\n"
                        )
                        f.write(
                            f"current_marker: {repr(current_marker_line[:50]) if current_marker_line else 'EMPTY'}\n"
                        )
                        f.write(f"is_new_message: {is_new_message}\n")
                        f.write(f"partial_empty: {not partial}\n")
                        f.write(f"DECISION: {'STREAM' if will_stream else 'SKIP'}\n")
                        if partial:
                            f.write(f"partial (100 chars): {partial[:100]!r}\n")

                    # B35 fix: Only stream if new marker line (new ● message started)
                    # B39 fix: Or if marker count increased (new response with identical content)
                    if partial and is_new_message:
                        on_update(partial + " ▌")
                        last_marker_line = current_marker_line
                        last_marker_count = current_marker_count

                    last_output = output  # Update cache

                # Check for confirmation prompt (Claude shows menu with "Do you want to" + "1. Yes")
                has_confirmation = "Do you want to" in output and "1. Yes" in output

                # DEBUG B36: Log confirmation detection
                with open("/tmp/claude_b36_debug.txt", "a") as f:
                    f.write(f"\n=== POLL {time.time() - start_time:.1f}s ===\n")
                    f.write(f"has_confirmation: {has_confirmation}\n")
                    if has_confirmation:
                        f.write("=== LAST 30 LINES OF OUTPUT ===\n")
                        for i, line in enumerate(output.strip().split("\n")[-30:]):
                            f.write(f"{i}: {line!r}\n")

                if has_confirmation:
                    return {
                        "type": "confirmation",
                        "context": self._extract_confirmation_context(output),
                    }

                # Detect end: prompt visible + no spinner
                # Claude spinner always starts with ✻ (unicode) - unique marker
                has_spinner = "✻" in output

                # Check if prompt '>' exists in last 5 lines (not necessarily last line due to footer)
                last_5_lines = [l.strip() for l in output.strip().split("\n")[-5:]]
                prompt_ready = any(l == ">" or l.startswith("> ") for l in last_5_lines)

                if prompt_ready and not has_spinner:
                    time.sleep(0.5)
                    result = subprocess.run(
                        [
                            "tmux",
                            "capture-pane",
                            "-t",
                            self.session_name,
                            "-p",
                            "-S",
                            "-500",
                        ],
                        capture_output=True,
                        text=True,
                    )
                    final_content, _ = self._extract_response(result.stdout, 0)
                    return final_content

            return "⚠️ Timeout"

        except FileNotFoundError:
            return "❌ tmux not found. Install: sudo apt install tmux"
        except Exception as e:
            return f"❌ Error: {e!s}"

    def _extract_first_tool_result(self, raw: str) -> tuple[int | None, str | None]:
        """Extract exit_code and output from the first completed Bash tool in buffer.

        Used for chained commands and final response extraction.

        Claude format (error):
            ● Bash(command)
              ⎿  Error: Exit code 1
                 [stderr line]

        Claude format (success):
            ● Bash(command)
              ⎿  output line

        Note: Leading whitespace in error output may be lost during parsing.
        This is a known limitation accepted for parser safety.

        Returns:
            tuple: (exit_code, shell_output) or (None, None) if not found
        """
        lines = raw.strip().split("\n")
        exit_code = None
        shell_output_lines = []
        in_tool_result = False
        found_first_tool = False

        for line in lines:
            stripped = line.strip()

            # Find Bash tool
            if re.match(r"^●\s*Bash\(", stripped):
                if found_first_tool:
                    break  # 2nd tool = stop
                found_first_tool = True
                continue

            # After first tool, look for result block (⎿)
            if found_first_tool and stripped.startswith("⎿"):
                in_tool_result = True
                # Check for exit code (error case)
                exit_match = re.search(r"Error: Exit code (\d+)", stripped)
                if exit_match:
                    exit_code = int(exit_match.group(1))
                else:
                    # Success case - content is inline after ⎿
                    inline_content = re.sub(r"^⎿\s*", "", stripped)
                    if inline_content:
                        shell_output_lines.append(inline_content)
                continue

            # Collect stderr lines (5+ spaces indent for error case)
            if in_tool_result:
                # Stop conditions
                if (
                    not stripped
                    or stripped.startswith("●")
                    or stripped.startswith(">")
                    or stripped.startswith("─")
                ):
                    break
                # 5 spaces = content under ⎿ Error line
                if line.startswith("     "):
                    shell_output_lines.append(stripped)

        shell_output = "\n".join(shell_output_lines) if shell_output_lines else None
        return (exit_code, shell_output)

    def _extract_response(
        self, raw: str, skip_count: int = 0, prev_text_idx: int = -1
    ) -> tuple[str, int]:
        """Extract the last Claude text response with tool summaries.

        Simple approach: find last text response, attach tool summaries.

        B35 fix: Returns (content, last_text_idx) tuple.
        If last_text_idx == prev_text_idx, it's the old message -> caller should ignore.

        Args:
            raw: tmux buffer content
            skip_count: deprecated, kept for compatibility
            prev_text_idx: previous poll's text index (-1 for new turn)

        Returns:
            tuple: (extracted_content, current_text_idx)
        """
        lines = raw.strip().split("\n")

        noise_patterns = [
            r"^✻.*interrupt",
            r"^─+$",
            r"Thinking",
            r"Philosophising",
            r"Pondering",
            r"Reasoning",
            r"ctrl-[gc]",
            r"tab to toggle",
            r"shift\+tab",
            r"Shift \+ Enter",
            r"^>\s*Try",
            r"^>\s*$",
            r"bypass permissions",
            r"to cycle",
            r"^nasf@",
            r"Welcome back",
            r"Tips for getting",
            r"default mode",
            r"plan mode",
            r"esc to interrupt",
            # Confirmation UI elements only (not content)
            r"^Do you want to",
            r"^❯?\s*\d+\.\s*(Yes|No|Type)",
            r"^Esc to cancel",
        ]

        # Build last response: find last ● text (not tool), collect content + tool summaries
        result_lines = []
        in_response = False
        in_tool = False
        in_tool_box = False  # Inside ╭─...─╯ box
        in_diff_block = False  # Inside ╌╌╌...╌╌╌ diff block
        tool_info = None
        tool_has_error = False

        # Find the last text ● (not a tool call) to start from
        last_text_idx = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Tool patterns: ● Write(...), ● Update:, ● Bash(...)
            is_tool_line = (
                re.match(r"^●\s*\w+\(", stripped)  # ● Write(file)
                or re.match(
                    r"^●\s*(Write|Update|Read|Bash|Delete):", stripped
                )  # ● Update: file
            )
            if stripped.startswith("●") and not is_tool_line:
                last_text_idx = i

        if last_text_idx == -1:
            return "", -1

        # B35 fix: Same index as previous poll = old message, return empty
        if prev_text_idx != -1 and last_text_idx == prev_text_idx:
            return "", last_text_idx

        # Parse from last text response
        for line in lines[last_text_idx:]:
            stripped = line.strip()

            # Track tool box state (╭─ starts, ╰─ ends)
            if stripped.startswith("╭─"):
                in_tool_box = True
                continue
            if stripped.startswith("╰─"):
                in_tool_box = False
                continue
            if in_tool_box:
                continue  # Skip all content inside box

            # Track diff block state (╌╌╌ toggles)
            if re.match(r"^╌{3,}$", stripped):
                in_diff_block = not in_diff_block
                continue
            if in_diff_block:
                continue  # Skip all content inside diff block

            # Skip tool labels that appear outside boxes
            if re.match(r"^(Edit file|Create file|Bash command)\s*", stripped):
                continue

            # Tool call: ● ToolName(args...) or ● ToolName: args
            tool_match = re.match(r"^●\s*(\w+)\((.*)$", stripped)
            tool_match_colon = re.match(r"^●\s*(\w+):\s*(.*)$", stripped)
            if tool_match or tool_match_colon:
                # Finalize previous tool
                if tool_info:
                    status = "✗" if tool_has_error else "✓"
                    result_lines.append(f"  ⎿ {tool_info} {status}")

                # Extract tool name and args from whichever pattern matched
                match = tool_match or tool_match_colon
                assert match is not None  # Guaranteed by if condition above
                tool_name = match.group(1)
                tool_args = match.group(2).rstrip(")").strip()
                # Strip status indicators like ✓ or ✗ from args
                tool_args = re.sub(r"\s*[✓✗]\s*$", "", tool_args)
                if len(tool_args) > 50:
                    tool_args = tool_args[:47] + "..."
                tool_info = f"{tool_name}: {tool_args}"
                tool_has_error = False
                in_tool = True
                continue

            # Tool output
            if stripped.startswith("⎿"):
                in_tool = True
                if "error" in stripped.lower():
                    tool_has_error = True
                continue

            # Tool output continuation
            if in_tool:
                if stripped.startswith("…") or "(ctrl+o" in stripped:
                    continue
                if "error" in stripped.lower():
                    tool_has_error = True
                if line.startswith("     ") or line.startswith("\t"):
                    continue
                # End of tool output
                if tool_info:
                    status = "✗" if tool_has_error else "✓"
                    result_lines.append(f"  ⎿ {tool_info} {status}")
                    tool_info = None
                in_tool = False

            # Text line ●
            if stripped.startswith("●"):
                text = re.sub(r"^●\s*", "", stripped)
                if text:
                    result_lines.append(text)
                in_response = True
                continue

            # Stop before user prompt (> [User] or >\xa0[User])
            # B35 fix: Pattern matches "> [" which is tmux-specific, not markdown
            if re.match(r"^>\s*\[", stripped):
                break

            # Normal content
            if in_response:
                is_noise = any(
                    re.search(p, stripped, re.IGNORECASE) for p in noise_patterns
                )
                if not is_noise and stripped:
                    result_lines.append(stripped)

        # Finalize last tool if any
        if tool_info:
            status = "✗" if tool_has_error else "✓"
            result_lines.append(f"  ⎿ {tool_info} {status}")

        # B12 fix: Re-attach exit code from raw output (filtered by tool box logic above)
        exit_code_match = re.search(r"Error: Exit code\s*(\d+)", raw, re.IGNORECASE)
        if exit_code_match and result_lines:
            result_text = "\n".join(result_lines)
            if "Error: Exit code" not in result_text:
                result_text += f"\nError: Exit code {exit_code_match.group(1)}"
                result_lines = result_text.split("\n")

        return "\n".join(result_lines), last_text_idx

    def _extract_confirmation_context(self, raw: str) -> str:
        """Extract confirmation context from Claude's UI separator.

        B36 fix: Claude CLI shows confirmation after a separator line (─────).
        We extract content BETWEEN the separator and "Do you want to".
        """
        lines = raw.strip().split("\n")

        # Find "Do you want to" line
        confirm_idx = -1
        for i, line in enumerate(lines):
            if "Do you want to" in line:
                confirm_idx = i
                break

        if confirm_idx == -1:
            return "Action pending confirmation"

        # B36 fix: Find separator (─────) BEFORE confirmation
        # Claude UI uses ~150 tirets as separator before confirmation dialogs
        separator_idx = -1
        for i in range(confirm_idx - 1, -1, -1):
            if re.match(r"^─{3,}$", lines[i].strip()):
                separator_idx = i
                break

        if separator_idx != -1:
            # Extract from separator+1 to confirm_idx
            start_idx = separator_idx + 1
        else:
            # Fallback: old behavior - find "Tool use" or last ●
            tool_use_idx = -1
            for i, line in enumerate(lines):
                if line.strip() == "Tool use":
                    tool_use_idx = i
                    break

            if tool_use_idx != -1 and tool_use_idx < confirm_idx:
                start_idx = tool_use_idx
            else:
                # Fallback: find last ● before confirmation
                last_bullet_idx = -1
                for i in range(confirm_idx - 1, -1, -1):
                    if "●" in lines[i]:
                        last_bullet_idx = i
                        break
                start_idx = (
                    last_bullet_idx
                    if last_bullet_idx != -1
                    else max(0, confirm_idx - 10)
                )

        # Extract context
        context_lines = []
        for line in lines[start_idx:confirm_idx]:
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
        last_marker_line = ""  # B35 fix: track marker content (not index) across polls
        last_marker_count = (
            0  # B39 fix: track marker count for identical content detection
        )
        last_output = ""  # B44/B53: Cache to skip parse if buffer unchanged

        while time.time() - start_time < timeout:
            time.sleep(1)

            # TODO B44/B53: Measure polling performance (capture + parse)
            t_poll_start = time.time()
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", self.session_name, "-p", "-S", "-500"],
                capture_output=True,
                text=True,
            )
            output = result.stdout
            t_capture = time.time()

            if on_update:
                # B44/B53 fix: Skip parse if buffer unchanged (AI thinking, no new content)
                if output == last_output:
                    continue

                current_lines = output.strip().split("\n")
                partial, current_text_idx = self._extract_response(output, 0)
                t_parse = time.time()

                # Log if polling took > 500ms (potential UI freeze cause)
                poll_time = t_parse - t_poll_start
                if poll_time > 0.5:
                    logging.warning(
                        f"B44/B53: Slow polling cycle in wait_response: {poll_time:.2f}s (capture: {t_capture - t_poll_start:.2f}s, parse: {t_parse - t_capture:.2f}s)"
                    )

                # B35 fix: Compare marker line CONTENT, not index (handles buffer scroll)
                current_marker_line = (
                    current_lines[current_text_idx].strip()
                    if current_text_idx >= 0 and current_text_idx < len(current_lines)
                    else ""
                )
                # B39 fix: Also check if marker count increased (new response with identical content)
                current_marker_count = sum(
                    1 for line in current_lines if line.strip().startswith("●")
                )
                is_new_message = (
                    current_marker_line != last_marker_line
                    or current_marker_count > last_marker_count
                )

                if partial and is_new_message:
                    on_update(partial + " ▌")
                    last_marker_line = current_marker_line
                    last_marker_count = current_marker_count

                last_output = output  # Update cache

            # Check for confirmation prompt (Claude shows menu with "Do you want to" + "Esc to cancel")
            if "Do you want to" in output and "1. Yes" in output:
                # Extract result before confirmation (for chained commands)
                prior_result, _ = self._extract_response(output, 0)

                # B67 fix: If no text response (chained tools), extract from tool output directly
                prior_exit_code = None
                prior_shell_output = None
                if not prior_result:
                    prior_exit_code, prior_shell_output = (
                        self._extract_first_tool_result(output)
                    )

                return {
                    "type": "confirmation",
                    "context": self._extract_confirmation_context(output),
                    "prior_result": prior_result,
                    "prior_exit_code": prior_exit_code,
                    "prior_shell_output": prior_shell_output,
                }

            # Detect end: same logic as ask() - prompt visible + no spinner
            has_spinner = "✻" in output
            last_5_lines = [l.strip() for l in output.strip().split("\n")[-5:]]
            prompt_ready = any(l == ">" or l.startswith("> ") for l in last_5_lines)

            # DEBUG: Log wait_response polling
            with open("/tmp/claude_wait_debug.txt", "a") as f:
                f.write(f"\n=== WAIT {time.time() - start_time:.1f}s ===\n")
                f.write(f"has_spinner: {has_spinner}\n")
                f.write(f"prompt_ready: {prompt_ready}\n")
                f.write(f"last_5_lines: {last_5_lines}\n")

            if prompt_ready and not has_spinner:
                final_content, _ = self._extract_response(output, 0)
                exit_code, shell_output = self._extract_first_tool_result(output)
                return {
                    "type": "response",
                    "content": final_content,
                    "exit_code": exit_code,
                    "shell_output": shell_output,
                }

        return {
            "type": "response",
            "content": "⚠️ Timeout",
            "exit_code": None,
            "shell_output": None,
        }

    def close(self) -> None:
        subprocess.run(["tmux", "send-keys", "-t", self.session_name, "/exit", "Enter"])
        time.sleep(1)
        subprocess.run(
            ["tmux", "kill-session", "-t", self.session_name], capture_output=True
        )
