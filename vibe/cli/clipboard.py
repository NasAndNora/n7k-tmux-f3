from __future__ import annotations

import base64
from collections.abc import Callable
import os
import platform
import shutil
import subprocess

import pyperclip
from textual.app import App
from textual.dom import NoScreen

_PREVIEW_MAX_LENGTH = 40


def _copy_osc52(text: str) -> None:
    """Copy text via OSC52 escape sequence (works in tmux/SSH)."""
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    osc52_seq = f"\033]52;c;{encoded}\a"
    if os.environ.get("TMUX"):
        osc52_seq = f"\033Ptmux;\033{osc52_seq}\033\\"

    with open("/dev/tty", "w") as tty:
        tty.write(osc52_seq)
        tty.flush()


def _copy_x11_clipboard(text: str) -> None:
    """Copy text via xclip (X11 Linux)."""
    subprocess.run(
        ["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True
    )


def _copy_wayland_clipboard(text: str) -> None:
    """Copy text via wl-copy (Wayland Linux)."""
    subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True)


def _get_copy_fns(app: App) -> list[Callable[[str], None]]:
    """Build clipboard method list, prioritized by platform.

    Order: native Linux tools first (faster), then OSC52, then fallbacks.
    All methods are tried to ensure clipboard is populated even if OSC52
    succeeds silently without actually copying.
    """
    copy_fns: list[Callable[[str], None]] = [
        _copy_osc52,
        pyperclip.copy,
        app.copy_to_clipboard,
    ]
    if platform.system() == "Linux":
        if shutil.which("wl-copy"):
            copy_fns = [_copy_wayland_clipboard, *copy_fns]
        if shutil.which("xclip"):
            copy_fns = [_copy_x11_clipboard, *copy_fns]
    return copy_fns


def _shorten_preview(texts: list[str]) -> str:
    dense_text = "⏎".join(texts).replace("\n", "⏎")
    if len(dense_text) > _PREVIEW_MAX_LENGTH:
        return f"{dense_text[: _PREVIEW_MAX_LENGTH - 1]}…"
    return dense_text


def copy_selection_to_clipboard(app: App) -> None:
    """Copy selected text from all widgets to clipboard.

    Tries multiple clipboard methods to ensure robustness.
    Handles NoScreen exception for unmounted widgets.
    """
    selected_texts = []

    for widget in app.query("*"):
        # CRITICAL: hasattr() calls property getter which may raise NoScreen
        # if widget is unmounted. Upstream v1.3.0 doesn't handle this (bug).
        try:
            if not hasattr(widget, "text_selection"):
                continue
            selection = widget.text_selection
        except NoScreen:
            continue

        if not selection:
            continue

        try:
            result = widget.get_selection(selection)
        except Exception:
            continue

        if not result:
            continue

        selected_text, _ = result
        if selected_text.strip():
            selected_texts.append(selected_text)

    if not selected_texts:
        return

    combined_text = "\n".join(selected_texts)

    # Try-all pattern: don't break on first success.
    # OSC52 can "succeed" (no exception) without actually copying
    # in terminals that don't support it. Trying all methods ensures
    # clipboard is populated if ANY method works.
    success = False
    for copy_fn in _get_copy_fns(app):
        try:
            copy_fn(combined_text)
        except:
            pass
        else:
            success = True

    if success:
        app.notify(
            f'"{_shorten_preview(selected_texts)}" copied to clipboard',
            severity="information",
            timeout=2,
        )
    else:
        app.notify(
            "Failed to copy - no clipboard method available",
            severity="warning",
            timeout=3,
        )
