"""Parser for Gemini CLI tool boxes.

Extracts file paths and diff information from Gemini's box-formatted output
to enable proper rendering via Vibe's SearchReplaceRenderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from vibe.cli.textual_ui.widgets.ai_tools import AIToolInfo


@dataclass
class GeminiToolInfo(AIToolInfo):
    """Information extracted from a Gemini tool box."""

    pass  # All fields inherited from AIToolInfo


class GeminiToolParser:
    """Parser for Gemini CLI output that extracts tool boxes.

    Gemini outputs tool actions in boxes like:
        ╭──────────────────────────────────────────────────╮
        │ ✓  Edit test.py: old => new                      │
        │                                                  │
        │ 36           raise ValueError("Cannot...")       │
        │ 37           return x / y                        │
        │ 38                                               │
        │ 39 +     def power(self, x, y):                  │
        │ 40 +         return x ** y                       │
        ╰──────────────────────────────────────────────────╯

    This parser extracts the tool type, file path, and diff lines.
    """

    # Box structure patterns
    BOX_START = re.compile(r"^╭─+╮?$")
    BOX_END = re.compile(r"^╰─+╯?$")
    BOX_LINE = re.compile(r"^│(.*)│$")

    # Tool header patterns (inside or outside box)
    # Note: ? pending, ✓ completed, ✗ failed, ⊷ queued
    TOOL_HEADER = re.compile(
        r"^\s*[✓✗?⊷]?\s*(WriteFile|Edit|ReadFile|Shell|DeleteFile)\s+(.+?)\s*$",
        re.IGNORECASE,
    )

    # Diff line patterns (inside box) - line number + marker + content
    LINE_ADDED = re.compile(r"^\s*(\d+)\s*\+\s*(.*)$")
    LINE_REMOVED = re.compile(r"^\s*(\d+)\s*-\s*(.*)$")
    LINE_CONTEXT = re.compile(
        r"^\s*(\d+)\s+(.*)$"
    )  # 1+ spaces (Gemini uses 1 space for new files)

    # Tool type normalization map (Gemini uses CamelCase, Vibe uses snake_case)
    TOOL_TYPE_MAP = {
        "writefile": "write_file",
        "editfile": "edit",
        "edit": "edit",
        "readfile": "read_file",
        "deletefile": "delete_file",
        "shell": "shell",
    }

    # Shell exit code pattern (appears after command execution)
    EXIT_CODE_PATTERN = re.compile(r"Command exited with code:\s*(\d+)", re.IGNORECASE)

    def _normalize_tool_type(self, raw_type: str) -> str:
        """Normalize Gemini tool type to Vibe format.

        Gemini uses: WriteFile, EditFile, Shell
        Vibe expects: write_file, edit, shell
        """
        normalized = raw_type.lower()
        return self.TOOL_TYPE_MAP.get(normalized, normalized)

    def parse(
        self, raw_output: str, debug: bool = False
    ) -> tuple[str, GeminiToolInfo | None]:
        """Parse Gemini output and extract tool info.

        Handles two formats:
        1. Header INSIDE box (original design): ╭─...─╮ │ ✓ Edit file.py │ ╰─...─╯
        2. Header OUTSIDE box (actual Gemini): ? WriteFile file.py ╭─...─╮ │ content │ ╰─...─╯

        Also handles tmux capture wrapper where each line is wrapped in │...│

        Args:
            raw_output: Raw output from Gemini CLI (with box characters).
            debug: If True, write debug info to /tmp/gemini_debug.txt

        Returns:
            Tuple of (text_without_boxes, tool_info_or_none).
        """
        # Pre-process: strip tmux capture wrapper (│ ... │) from each line
        raw_lines = raw_output.strip().split("\n")
        lines = []
        for raw_line in raw_lines:
            stripped = raw_line.strip()
            # Remove outer tmux box wrapper if present (│ content │)
            if (
                stripped.startswith("│")
                and stripped.endswith("│")
                and len(stripped) > 2
            ):
                # Check if this is a tmux wrapper (has spaces after first │)
                inner = stripped[1:-1]
                # Only strip if it looks like tmux wrapper (content has leading space)
                if (
                    inner.startswith(" ")
                    or inner.startswith("╭")
                    or inner.startswith("╰")
                ):
                    stripped = inner.strip()
            lines.append(stripped)

        # Debug: log preprocessed lines
        if debug:
            with open("/tmp/gemini_debug.txt", "a") as f:
                f.write("\n=== PREPROCESSED LINES ===\n")
                for i, line in enumerate(lines):
                    f.write(f"{i}: [{line}]\n")
                f.write("=== END PREPROCESSED ===\n")

        text_lines: list[str] = []
        tool_info: GeminiToolInfo | None = None

        # Track header found outside box (Gemini's actual format)
        pending_header: tuple[str, str, str] | None = None

        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for tool header OUTSIDE box (not inside a box line)
            header_match = self.TOOL_HEADER.match(line)
            if header_match and not self.BOX_LINE.match(line):
                tool_type = self._normalize_tool_type(header_match.group(1))
                rest = header_match.group(2).strip()

                # Parse "Writing to X" format (Gemini uses this)
                # Note: Gemini pads lines with spaces + scroll indicator (←), strip that pattern
                def clean_path(p: str) -> str:
                    return re.sub(r"\s+←?\s*$", "", p).strip()

                if rest.lower().startswith("writing to "):
                    file_path = clean_path(rest[11:])
                elif ":" in rest:
                    file_path = clean_path(rest.split(":")[0])
                else:
                    file_path = clean_path(rest)
                pending_header = (tool_type, file_path, "")
                i += 1
                continue

            # Check for box start
            if self.BOX_START.match(line):
                box_lines, end_idx = self._extract_box(lines, i)
                if box_lines:
                    # Try parsing box content first (header-inside-box format)
                    parsed = self._parse_box(box_lines)
                    if parsed:
                        tool_info = parsed
                    elif pending_header:
                        # Use header found before box (header-outside-box format)
                        tool_type, file_path, desc = pending_header
                        is_new_file = tool_type == "write_file"
                        diff_lines = self._extract_diff_from_box(box_lines, is_new_file)
                        tool_info = GeminiToolInfo(
                            tool_type=tool_type,
                            file_path=file_path,
                            description=desc,
                            diff_lines=diff_lines,
                        )
                pending_header = None  # Clear after processing box
                i = end_idx + 1
            else:
                text_lines.append(lines[i])
                i += 1

        # Handle header without box - extract diff lines from remaining text
        if pending_header and not tool_info:
            tool_type, file_path, desc = pending_header
            # Try to extract diff lines from text_lines (lines after header, no box)
            is_new_file = tool_type == "write_file"
            diff_lines = self._extract_diff_from_lines(text_lines, is_new_file)
            tool_info = GeminiToolInfo(
                tool_type=tool_type,
                file_path=file_path,
                description=desc,
                diff_lines=diff_lines,
            )

        # Extract exit code for shell commands
        if tool_info and tool_info.tool_type == "shell":
            for line in lines:
                exit_match = self.EXIT_CODE_PATTERN.search(line)
                if exit_match:
                    tool_info.exit_code = int(exit_match.group(1))
                    break

        # B51 fix: Check if file exists BEFORE execution (for Created vs Modified)
        if (
            tool_info
            and tool_info.file_path
            and tool_info.tool_type in {"write_file", "edit"}
        ):
            file_path = Path(tool_info.file_path)
            tool_info.is_new_file = not file_path.exists()

        text_content = "\n".join(text_lines).strip()
        return text_content, tool_info

    def _extract_box(self, lines: list[str], start_idx: int) -> tuple[list[str], int]:
        """Extract all lines within a box.

        Returns:
            Tuple of (box_content_lines, end_index).
        """
        box_lines: list[str] = []
        i = start_idx + 1  # Skip the opening ╭─

        while i < len(lines):
            line = lines[i].strip()

            if self.BOX_END.match(line):
                return box_lines, i

            # Extract content from box line (strip │ from both ends)
            match = self.BOX_LINE.match(line)
            if match:
                content = match.group(1)
                box_lines.append(content)
            elif line.startswith("│"):
                # Partial match - just strip leading │
                content = line[1:].rstrip("│").rstrip()
                box_lines.append(content)

            i += 1

        # No closing found - return what we have
        return box_lines, i - 1

    def _extract_diff_from_box(
        self, box_lines: list[str], is_new_file: bool = False
    ) -> list[tuple[str, str]]:
        """Extract diff lines from box content when header is outside.

        Used when the tool header (e.g., "? WriteFile file.py") appears before
        the box rather than inside it.

        Args:
            box_lines: Lines extracted from inside a box.
            is_new_file: If True, treat context lines as additions (for write_file).

        Returns:
            List of (type, content) tuples where type is '+', '-', or ' '.
        """
        return self._extract_diff_from_lines(box_lines, is_new_file)

    def _extract_diff_from_lines(
        self, lines: list[str], is_new_file: bool = False
    ) -> list[tuple[str, str]]:
        """Extract diff lines from any list of lines.

        Handles Gemini's format: "line_number +/- content" or "line_number   content" (context)

        Args:
            lines: Lines to parse for diff patterns.
            is_new_file: If True, treat context lines as additions (for write_file creation).

        Returns:
            List of (type, content) tuples where type is '+', '-', or ' '.
        """
        diff_lines: list[tuple[str, str]] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Try to match diff patterns (line_number + content)
            added = self.LINE_ADDED.match(stripped)
            if added:
                diff_lines.append(("+", added.group(2)))
                continue

            removed = self.LINE_REMOVED.match(stripped)
            if removed:
                diff_lines.append(("-", removed.group(2)))
                continue

            context = self.LINE_CONTEXT.match(stripped)
            if context:
                # For new file creation, treat context lines as additions
                line_type = "+" if is_new_file else " "
                diff_lines.append((line_type, context.group(2)))

        return diff_lines

    def _parse_box(self, box_lines: list[str]) -> GeminiToolInfo | None:
        """Parse box content and create GeminiToolInfo.

        Returns:
            GeminiToolInfo if this is a recognized tool box, None otherwise.
        """
        if not box_lines:
            return None

        tool_type: str | None = None
        file_path: str = ""
        description: str = ""
        diff_lines: list[tuple[str, str]] = []

        for line in box_lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Try to match tool header
            header_match = self.TOOL_HEADER.match(stripped)
            if header_match:
                tool_type = self._normalize_tool_type(header_match.group(1))
                rest = header_match.group(2).strip()

                # Extract file path from rest (e.g., "test.py: old => new" or "test.py")
                if ":" in rest:
                    file_path = rest.split(":")[0].strip()
                    description = rest.split(":", 1)[1].strip() if ":" in rest else ""
                else:
                    file_path = rest
                continue

            # Try to match diff lines
            added_match = self.LINE_ADDED.match(stripped)
            if added_match:
                diff_lines.append(("+", added_match.group(2)))
                continue

            removed_match = self.LINE_REMOVED.match(stripped)
            if removed_match:
                diff_lines.append(("-", removed_match.group(2)))
                continue

            context_match = self.LINE_CONTEXT.match(stripped)
            if context_match:
                diff_lines.append((" ", context_match.group(2)))
                continue

        # Only return if we found a recognized tool
        if tool_type and file_path:
            return GeminiToolInfo(
                tool_type=tool_type,
                file_path=file_path,
                description=description,
                diff_lines=diff_lines,
            )

        return None

    def to_search_replace_format(self, info: AIToolInfo) -> str:
        """Convert GeminiToolInfo to Vibe's search/replace format.

        The format expected by SearchReplaceRenderer is:
            <<<<<<< SEARCH
            old content here
            =======
            new content here
            >>>>>>> REPLACE

        Args:
            info: Parsed tool information.

        Returns:
            Content string in search/replace format.
        """
        if not info.diff_lines:
            # No diff lines - just return description or empty
            return info.description or f"{info.tool_type}: {info.file_path}"

        # Separate context/removed (SEARCH) from context/added (REPLACE)
        search_lines: list[str] = []
        replace_lines: list[str] = []

        for line_type, content in info.diff_lines:
            if line_type == "-":
                # Removed line - only in SEARCH
                search_lines.append(content)
            elif line_type == "+":
                # Added line - only in REPLACE
                replace_lines.append(content)
            else:
                # Context line - in both
                search_lines.append(content)
                replace_lines.append(content)

        search_content = "\n".join(search_lines)
        replace_content = "\n".join(replace_lines)

        return f"""<<<<<<< SEARCH
{search_content}
=======
{replace_content}
>>>>>>> REPLACE"""

    def to_raw_context(self, info: AIToolInfo) -> str:
        """Convert GeminiToolInfo to raw text for fallback display.

        Used when we can't render as a proper diff.

        Args:
            info: Parsed tool information.

        Returns:
            Human-readable description of the tool action.
        """
        lines = [f"{info.tool_type.upper()}: {info.file_path}"]

        if info.description:
            lines.append(info.description)

        if info.diff_lines:
            lines.append("")
            for line_type, content in info.diff_lines:
                prefix = line_type if line_type in {"+", "-"} else " "
                lines.append(f"{prefix} {content}")

        return "\n".join(lines)
