"""Parser for Claude CLI tool boxes.

Extracts file paths and diff information from Claude's box-formatted output
to enable proper rendering via Vibe's SearchReplaceRenderer.

Note: Claude CLI uses same box format (╭─│╰) as Gemini.
"""

from __future__ import annotations

from pathlib import Path
import re

from vibe.cli.textual_ui.widgets.ai_tools import CLIToolInfo


class ClaudeToolParser:
    """Parser for Claude CLI output that extracts tool boxes.

    Claude outputs tool actions in boxes like:
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
    # Claude Edit uses dashed separator ╌ instead of box
    EDIT_SEPARATOR = re.compile(r"^╌+$")

    # Tool header patterns (inside or outside box)
    # Claude format: ● Write(filename) or ● Update(filename) or ● Bash(command)
    TOOL_HEADER = re.compile(
        r"^\s*●?\s*(Write|Update|Bash|Read|Delete)\s*\((.+?)\)?\s*$", re.IGNORECASE
    )
    # Alternative Edit format: "Edit file filename.py"
    EDIT_FILE_HEADER = re.compile(r"^Edit file\s+(.+?)\s*$", re.IGNORECASE)
    # Overwrite/Create file format (Claude uses these for confirmations)
    # File path is on first line inside box
    FILE_ACTION_HEADER = re.compile(r"^(Overwrite|Create) file\s*$", re.IGNORECASE)
    # B50 fix: Simple "Bash command" format (no box, command on next line)
    BASH_COMMAND_HEADER = re.compile(r"^Bash command\s*$", re.IGNORECASE)

    # Diff line patterns (inside box) - line number + marker + content
    LINE_ADDED = re.compile(r"^\s*(\d+)\s*\+\s*(.*)$")
    LINE_REMOVED = re.compile(r"^\s*(\d+)\s*-\s*(.*)$")
    LINE_CONTEXT = re.compile(r"^\s*(\d+)\s+(.*)$")  # 1+ spaces

    # Tool type normalization map (Claude uses Write/Update/Bash, Vibe uses snake_case)
    TOOL_TYPE_MAP = {
        "write": "write_file",
        "update": "edit",
        "bash": "shell",
        "read": "read_file",
        "delete": "delete_file",
    }

    # Shell exit code pattern (appears after command execution)
    # Gemini: "Command exited with code: X", Claude: "Error: Exit code X"
    EXIT_CODE_PATTERN = re.compile(
        r"(?:Command exited with code:|Error: Exit code)\s*(\d+)", re.IGNORECASE
    )

    def _normalize_tool_type(self, raw_type: str) -> str:
        """Normalize Claude tool type to Vibe format.

        Claude uses: Write, Update, Bash, Read, Delete
        Vibe expects: write_file, edit, shell, read_file, delete_file
        """
        normalized = raw_type.lower()
        return self.TOOL_TYPE_MAP.get(normalized, normalized)

    def parse(
        self, raw_output: str, debug: bool = False
    ) -> tuple[str, CLIToolInfo | None]:
        """Parse Claude output and extract tool info.

        Handles two formats:
        1. Header INSIDE box (original design): ╭─...─╮ │ ✓ Edit file.py │ ╰─...─╯
        2. Header OUTSIDE box (Claude format): ● Write(file.py) ╭─...─╮ │ content │ ╰─...─╯

        Also handles tmux capture wrapper where each line is wrapped in │...│

        Args:
            raw_output: Raw output from Claude CLI (with box characters).
            debug: If True, write debug info to /tmp/claude_debug.txt

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
            with open("/tmp/claude_debug.txt", "a") as f:
                f.write("\n=== PREPROCESSED LINES ===\n")
                for i, line in enumerate(lines):
                    f.write(f"{i}: [{line}]\n")
                f.write("=== END PREPROCESSED ===\n")

        text_lines: list[str] = []
        tool_info: CLIToolInfo | None = None

        # Track header found outside box (Claude's actual format)
        pending_header: tuple[str, str, str] | None = None

        i = 0
        while i < len(lines):
            line = lines[i]

            # Clean path helper
            def clean_path(p: str) -> str:
                return re.sub(r"\s+←?\s*$", "", p).strip()

            # Check for "Edit file filename" format (Claude's edit format)
            edit_match = self.EDIT_FILE_HEADER.match(line)
            if edit_match:
                file_path = clean_path(edit_match.group(1))
                pending_header = ("edit", file_path, "")
                i += 1
                continue

            # Check for "Overwrite file" or "Create file" format
            # B37 fix: File path is on next line (first line inside box)
            file_action_match = self.FILE_ACTION_HEADER.match(line)
            if file_action_match:
                # File path will be extracted from first line of box
                pending_header = ("write_file", "__FROM_BOX__", "")
                i += 1
                continue

            # B50 fix: Check for "Bash command" format (command on next line, description after)
            bash_header_match = self.BASH_COMMAND_HEADER.match(line)
            if bash_header_match:
                # Next line is the command, line after is description
                command = lines[i + 1].strip() if i + 1 < len(lines) else ""
                description = lines[i + 2].strip() if i + 2 < len(lines) else ""
                tool_info = CLIToolInfo(
                    tool_type="shell",
                    file_path=command,  # For shell, file_path holds the command
                    description=description,
                    diff_lines=[],
                )
                if debug:
                    with open("/tmp/claude_debug.txt", "a") as f:
                        f.write("\n=== BASH COMMAND PARSED (B50) ===\n")
                        f.write(f"command: {command}\n")
                        f.write(f"description: {description}\n")
                i += 3  # Skip header + command + description
                continue

            # Check for tool header OUTSIDE box (not inside a box line)
            header_match = self.TOOL_HEADER.match(line)
            if header_match and not self.BOX_LINE.match(line):
                tool_type = self._normalize_tool_type(header_match.group(1))
                rest = header_match.group(2).strip()

                # Detect Bash(cat > file) or Bash(cat >> file) pattern - treat as write_file/edit
                if tool_type == "shell":
                    cat_match = re.match(r"cat\s*>>?\s*([^\s<]+)", rest)
                    if cat_match:
                        # >> is append (edit), > is create (write_file)
                        tool_type = "edit" if ">>" in rest else "write_file"
                        file_path = clean_path(cat_match.group(1))
                    else:
                        file_path = clean_path(rest)
                elif rest.lower().startswith("writing to "):
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
                if debug:
                    with open("/tmp/claude_debug.txt", "a") as f:
                        f.write(f"\n=== BOX FOUND at line {i} ===\n")
                        f.write(f"pending_header: {pending_header}\n")
                        f.write(f"box_lines count: {len(box_lines)}\n")
                        for j, bl in enumerate(box_lines[:10]):
                            f.write(f"  box[{j}]: [{bl}]\n")
                        if len(box_lines) > 10:
                            f.write(f"  ... +{len(box_lines) - 10} more lines\n")
                if box_lines:
                    # Try parsing box content first (header-inside-box format)
                    parsed = self._parse_box(box_lines)
                    if parsed:
                        tool_info = parsed
                    elif pending_header:
                        # Use header found before box (header-outside-box format)
                        tool_type, file_path, desc = pending_header

                        # B37 fix: If file_path is placeholder, extract from first box line
                        if file_path == "__FROM_BOX__" and box_lines:
                            # First line of box should be filename
                            file_path = clean_path(box_lines[0])
                            # Remove first line from box_lines (it's not diff content)
                            box_lines = box_lines[1:]

                        is_new_file = tool_type == "write_file"
                        diff_lines = self._extract_diff_from_box(box_lines, is_new_file)
                        tool_info = CLIToolInfo(
                            tool_type=tool_type,
                            file_path=file_path,
                            description=desc,
                            diff_lines=diff_lines,
                        )
                        if debug:
                            with open("/tmp/claude_debug.txt", "a") as f:
                                f.write("=== TOOL INFO CREATED ===\n")
                                f.write(f"tool_type: {tool_info.tool_type}\n")
                                f.write(f"file_path: {tool_info.file_path}\n")
                                f.write(
                                    f"diff_lines count: {len(tool_info.diff_lines)}\n"
                                )
                pending_header = None  # Clear after processing box
                i = end_idx + 1

            # Check for Edit separator (╌╌╌) - diff lines follow until next separator
            elif self.EDIT_SEPARATOR.match(line) and pending_header:
                # Extract diff lines until next separator or end
                diff_content_lines = []
                i += 1
                while i < len(lines):
                    if self.EDIT_SEPARATOR.match(lines[i]):
                        i += 1  # Skip closing separator
                        break
                    diff_content_lines.append(lines[i])
                    i += 1

                tool_type, file_path, desc = pending_header
                is_new_file = tool_type == "write_file"
                diff_lines = self._extract_diff_from_lines(
                    diff_content_lines, is_new_file
                )
                tool_info = CLIToolInfo(
                    tool_type=tool_type,
                    file_path=file_path,
                    description=desc,
                    diff_lines=diff_lines,
                )
                if debug:
                    with open("/tmp/claude_debug.txt", "a") as f:
                        f.write("\n=== EDIT DIFF FOUND ===\n")
                        f.write(f"tool_type: {tool_info.tool_type}\n")
                        f.write(f"file_path: {tool_info.file_path}\n")
                        f.write(f"diff_lines count: {len(tool_info.diff_lines)}\n")
                pending_header = None

            else:
                text_lines.append(lines[i])
                i += 1

        # Handle header without box - extract diff lines from remaining text
        if pending_header and not tool_info:
            tool_type, file_path, desc = pending_header
            # Try to extract diff lines from text_lines (lines after header, no box)
            is_new_file = tool_type == "write_file"
            diff_lines = self._extract_diff_from_lines(text_lines, is_new_file)
            tool_info = CLIToolInfo(
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

        Note: After preprocessing, box lines may no longer have │ wrappers.
        We just collect everything between BOX_START and BOX_END.

        Returns:
            Tuple of (box_content_lines, end_index).
        """
        box_lines: list[str] = []
        i = start_idx + 1  # Skip the opening ╭─

        while i < len(lines):
            line = lines[i].strip()

            if self.BOX_END.match(line):
                return box_lines, i

            # Extract content from box line (strip │ from both ends if present)
            match = self.BOX_LINE.match(line)
            if match:
                content = match.group(1)
                box_lines.append(content)
            elif line.startswith("│"):
                # Partial match - just strip leading │
                content = line[1:].rstrip("│").rstrip()
                box_lines.append(content)
            else:
                # After preprocessing, │ may be stripped - just add the line as-is
                box_lines.append(line)

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

        Claude format: raw code lines WITHOUT line numbers (unlike Gemini).
        Falls back to treating all non-empty lines as content.

        Args:
            lines: Lines to parse for diff patterns.
            is_new_file: If True, treat all lines as additions (for write_file creation).

        Returns:
            List of (type, content) tuples where type is '+', '-', or ' '.
        """
        diff_lines: list[tuple[str, str]] = []
        has_numbered_lines = False

        # First pass: try to match numbered diff patterns (Gemini-style)
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Try to match diff patterns (line_number + content)
            added = self.LINE_ADDED.match(stripped)
            if added:
                diff_lines.append(("+", added.group(2)))
                has_numbered_lines = True
                continue

            removed = self.LINE_REMOVED.match(stripped)
            if removed:
                diff_lines.append(("-", removed.group(2)))
                has_numbered_lines = True
                continue

            context = self.LINE_CONTEXT.match(stripped)
            if context:
                line_type = "+" if is_new_file else " "
                diff_lines.append((line_type, context.group(2)))
                has_numbered_lines = True

        # If no numbered lines found, treat as raw content (Claude format)
        if not has_numbered_lines:
            diff_lines = []
            # Filter noise lines from Claude's output
            noise_patterns = [
                r"^cat\s*>",  # cat > file command
                r"^EOF$",  # heredoc markers
                r"^<<\s*'?EOF'?",  # heredoc start
                r"^⎿",  # Claude's tool indicator
                r"^─+$",  # separator lines
                r"^Bash command$",  # label
                r"^Create .* file$",  # description
                r"^Running",  # status
            ]

            # Skip first line if it's the filename
            start_idx = 0
            if lines:
                first_line = lines[0].strip()
                # Skip if looks like a filename (has extension or is a path)
                if (
                    "." in first_line
                    and "/" not in first_line
                    and len(first_line) < 100
                ) or first_line.startswith("/"):
                    start_idx = 1

            for line in lines[start_idx:]:
                stripped = line.strip()
                # Skip noise lines
                if any(re.match(p, stripped, re.IGNORECASE) for p in noise_patterns):
                    continue
                # Keep original indentation, just strip trailing whitespace
                content = line.rstrip()
                # For new file, all lines are additions
                line_type = "+" if is_new_file else " "
                diff_lines.append((line_type, content))

        return diff_lines

    def _parse_box(self, box_lines: list[str]) -> CLIToolInfo | None:
        """Parse box content and create CLIToolInfo.

        Returns:
            CLIToolInfo if this is a recognized tool box, None otherwise.
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
            return CLIToolInfo(
                tool_type=tool_type,
                file_path=file_path,
                description=description,
                diff_lines=diff_lines,
            )

        return None

    def to_search_replace_format(self, info: CLIToolInfo) -> str:
        """Convert CLIToolInfo to Vibe's search/replace format.

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

    def to_raw_context(self, info: CLIToolInfo) -> str:
        """Convert CLIToolInfo to raw text for fallback display.

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
