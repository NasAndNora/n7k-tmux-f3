from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, mock_open, patch

import pytest
from textual.app import App

from vibe.cli.clipboard import _copy_osc52, copy_selection_to_clipboard


class MockWidget:
    def __init__(
        self,
        text_selection: object | None = None,
        get_selection_result: tuple[str, object] | None = None,
        get_selection_raises: Exception | None = None,
    ) -> None:
        self.text_selection = text_selection
        self._get_selection_result = get_selection_result
        self._get_selection_raises = get_selection_raises

    def get_selection(self, selection: object) -> tuple[str, object]:
        if self._get_selection_raises:
            raise self._get_selection_raises
        if self._get_selection_result is None:
            return ("", None)
        return self._get_selection_result


@pytest.fixture
def mock_app() -> App:
    app = MagicMock(spec=App)
    app.query = MagicMock(return_value=[])
    app.notify = MagicMock()
    app.copy_to_clipboard = MagicMock()
    return cast(App, app)


@pytest.mark.parametrize(
    "widgets,description",
    [
        ([], "no widgets"),
        ([MockWidget(text_selection=None)], "no selection"),
        ([MockWidget()], "widget without text_selection attr"),
        (
            [
                MockWidget(
                    text_selection=SimpleNamespace(),
                    get_selection_raises=ValueError("Error getting selection"),
                )
            ],
            "get_selection raises",
        ),
        (
            [MockWidget(text_selection=SimpleNamespace(), get_selection_result=None)],
            "empty result",
        ),
        (
            [
                MockWidget(
                    text_selection=SimpleNamespace(), get_selection_result=("   ", None)
                )
            ],
            "empty text",
        ),
    ],
)
def test_copy_selection_to_clipboard_no_notification(
    mock_app: MagicMock, widgets: list[MockWidget], description: str
) -> None:
    if description == "widget without text_selection attr":
        del widgets[0].text_selection
    mock_app.query.return_value = widgets

    copy_selection_to_clipboard(mock_app)
    mock_app.notify.assert_not_called()


@patch("vibe.cli.clipboard._get_copy_fns")
def test_copy_selection_to_clipboard_success(
    mock_get_copy_fns: MagicMock, mock_app: MagicMock
) -> None:
    """Test that copy succeeds and notification is shown."""
    widget = MockWidget(
        text_selection=SimpleNamespace(), get_selection_result=("selected text", None)
    )
    mock_app.query.return_value = [widget]

    mock_copy_fn = MagicMock()
    mock_get_copy_fns.return_value = [mock_copy_fn]

    copy_selection_to_clipboard(mock_app)

    mock_copy_fn.assert_called_once_with("selected text")
    mock_app.notify.assert_called_once_with(
        '"selected text" copied to clipboard', severity="information", timeout=2
    )


@patch("vibe.cli.clipboard._get_copy_fns")
def test_copy_selection_to_clipboard_tries_all_methods(
    mock_get_copy_fns: MagicMock, mock_app: MagicMock
) -> None:
    """Test that ALL methods are tried even after first success (try-all pattern)."""
    widget = MockWidget(
        text_selection=SimpleNamespace(), get_selection_result=("selected text", None)
    )
    mock_app.query.return_value = [widget]

    fn_1 = MagicMock(side_effect=Exception("failed"))
    fn_2 = MagicMock()  # succeeds
    fn_3 = MagicMock()  # also called (try-all)
    mock_get_copy_fns.return_value = [fn_1, fn_2, fn_3]

    copy_selection_to_clipboard(mock_app)

    fn_1.assert_called_once_with("selected text")
    fn_2.assert_called_once_with("selected text")
    fn_3.assert_called_once_with("selected text")
    mock_app.notify.assert_called_once_with(
        '"selected text" copied to clipboard', severity="information", timeout=2
    )


@patch("vibe.cli.clipboard._get_copy_fns")
def test_copy_selection_to_clipboard_all_methods_fail(
    mock_get_copy_fns: MagicMock, mock_app: MagicMock
) -> None:
    """Test failure notification when all methods fail."""
    widget = MockWidget(
        text_selection=SimpleNamespace(), get_selection_result=("selected text", None)
    )
    mock_app.query.return_value = [widget]

    failing_fn1 = MagicMock(side_effect=Exception("failed 1"))
    failing_fn2 = MagicMock(side_effect=Exception("failed 2"))
    failing_fn3 = MagicMock(side_effect=Exception("failed 3"))
    mock_get_copy_fns.return_value = [failing_fn1, failing_fn2, failing_fn3]

    copy_selection_to_clipboard(mock_app)

    failing_fn1.assert_called_once_with("selected text")
    failing_fn2.assert_called_once_with("selected text")
    failing_fn3.assert_called_once_with("selected text")
    mock_app.notify.assert_called_once_with(
        "Failed to copy - no clipboard method available", severity="warning", timeout=3
    )


@patch("vibe.cli.clipboard._get_copy_fns")
def test_copy_selection_to_clipboard_multiple_widgets(
    mock_get_copy_fns: MagicMock, mock_app: MagicMock
) -> None:
    """Test combining text from multiple widgets."""
    widget1 = MockWidget(
        text_selection=SimpleNamespace(), get_selection_result=("first selection", None)
    )
    widget2 = MockWidget(
        text_selection=SimpleNamespace(),
        get_selection_result=("second selection", None),
    )
    widget3 = MockWidget(text_selection=None)
    mock_app.query.return_value = [widget1, widget2, widget3]

    mock_copy_fn = MagicMock()
    mock_get_copy_fns.return_value = [mock_copy_fn]

    copy_selection_to_clipboard(mock_app)

    mock_copy_fn.assert_called_once_with("first selection\nsecond selection")
    mock_app.notify.assert_called_once_with(
        '"first selection⏎second selection" copied to clipboard',
        severity="information",
        timeout=2,
    )


@patch("vibe.cli.clipboard._get_copy_fns")
def test_copy_selection_to_clipboard_preview_shortening(
    mock_get_copy_fns: MagicMock, mock_app: MagicMock
) -> None:
    """Test that long text is shortened in notification preview."""
    long_text = "a" * 100
    widget = MockWidget(
        text_selection=SimpleNamespace(), get_selection_result=(long_text, None)
    )
    mock_app.query.return_value = [widget]

    mock_copy_fn = MagicMock()
    mock_get_copy_fns.return_value = [mock_copy_fn]

    copy_selection_to_clipboard(mock_app)

    mock_copy_fn.assert_called_once_with(long_text)
    notification_call = mock_app.notify.call_args
    assert notification_call is not None
    assert '"' in notification_call[0][0]
    assert "copied to clipboard" in notification_call[0][0]
    assert len(notification_call[0][0]) < len(long_text) + 30


@patch("builtins.open", new_callable=mock_open)
def test_copy_osc52_writes_correct_sequence(
    mock_file: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test OSC52 escape sequence is correctly formatted."""
    monkeypatch.delenv("TMUX", raising=False)
    test_text = "héllo wörld 🎉"

    _copy_osc52(test_text)

    encoded = base64.b64encode(test_text.encode("utf-8")).decode("ascii")
    expected_seq = f"\033]52;c;{encoded}\a"
    mock_file.assert_called_once_with("/dev/tty", "w")
    handle = mock_file()
    handle.write.assert_called_once_with(expected_seq)
    handle.flush.assert_called_once()


@patch("builtins.open", new_callable=mock_open)
def test_copy_osc52_with_tmux(
    mock_file: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test OSC52 is wrapped for tmux passthrough."""
    monkeypatch.setenv("TMUX", "1")
    test_text = "test text"

    _copy_osc52(test_text)

    encoded = base64.b64encode(test_text.encode("utf-8")).decode("ascii")
    expected_seq = f"\033Ptmux;\033\033]52;c;{encoded}\a\033\\"
    handle = mock_file()
    handle.write.assert_called_once_with(expected_seq)


@patch("vibe.cli.clipboard.subprocess.run")
def test_copy_x11_clipboard(mock_subprocess: MagicMock) -> None:
    """Test xclip command is called correctly."""
    from vibe.cli.clipboard import _copy_x11_clipboard

    test_text = "test text"

    _copy_x11_clipboard(test_text)

    mock_subprocess.assert_called_once_with(
        ["xclip", "-selection", "clipboard"],
        input=test_text.encode("utf-8"),
        check=True,
    )


@patch("vibe.cli.clipboard.subprocess.run")
def test_copy_wayland_clipboard(mock_subprocess: MagicMock) -> None:
    """Test wl-copy command is called correctly."""
    from vibe.cli.clipboard import _copy_wayland_clipboard

    test_text = "test text"

    _copy_wayland_clipboard(test_text)

    mock_subprocess.assert_called_once_with(
        ["wl-copy"], input=test_text.encode("utf-8"), check=True
    )


@patch("vibe.cli.clipboard.shutil.which")
@patch("vibe.cli.clipboard.platform.system")
def test_get_copy_fns_linux_with_tools(
    mock_system: MagicMock, mock_which: MagicMock, mock_app: MagicMock
) -> None:
    """Test _get_copy_fns adds Linux tools when available."""
    import pyperclip

    from vibe.cli.clipboard import (
        _copy_osc52,
        _copy_wayland_clipboard,
        _copy_x11_clipboard,
        _get_copy_fns,
    )

    mock_system.return_value = "Linux"
    mock_which.side_effect = (
        lambda cmd: f"/usr/bin/{cmd}" if cmd in ["wl-copy", "xclip"] else None
    )

    copy_fns = _get_copy_fns(mock_app)

    # Order: xclip, wl-copy, osc52, pyperclip, app.copy_to_clipboard
    assert len(copy_fns) == 5
    assert copy_fns[0] == _copy_x11_clipboard
    assert copy_fns[1] == _copy_wayland_clipboard
    assert copy_fns[2] == _copy_osc52
    assert copy_fns[3] == pyperclip.copy
    assert copy_fns[4] == mock_app.copy_to_clipboard


@patch("vibe.cli.clipboard.shutil.which")
@patch("vibe.cli.clipboard.platform.system")
def test_get_copy_fns_non_linux(
    mock_system: MagicMock, mock_which: MagicMock, mock_app: MagicMock
) -> None:
    """Test _get_copy_fns skips Linux tools on other platforms."""
    import pyperclip

    from vibe.cli.clipboard import _copy_osc52, _get_copy_fns

    mock_system.return_value = "Darwin"  # macOS

    copy_fns = _get_copy_fns(mock_app)

    # No xclip/wl-copy on macOS
    assert len(copy_fns) == 3
    assert copy_fns[0] == _copy_osc52
    assert copy_fns[1] == pyperclip.copy
    assert copy_fns[2] == mock_app.copy_to_clipboard
    mock_which.assert_not_called()


# =============================================================================
# INTEGRATION TESTS - Test real method calls with try-all pattern
# =============================================================================


@patch("vibe.cli.clipboard.shutil.which")
@patch("vibe.cli.clipboard.platform.system")
@patch("vibe.cli.clipboard._copy_osc52")
@patch("vibe.cli.clipboard.pyperclip.copy")
def test_integration_try_all_calls_all_methods_on_success(
    mock_pyperclip: MagicMock,
    mock_osc52: MagicMock,
    mock_system: MagicMock,
    mock_which: MagicMock,
    mock_app: MagicMock,
) -> None:
    """Integration: verify ALL methods are called even when first succeeds."""
    mock_system.return_value = "Darwin"  # No xclip/wl-copy
    widget = MockWidget(
        text_selection=SimpleNamespace(), get_selection_result=("test", None)
    )
    mock_app.query.return_value = [widget]

    copy_selection_to_clipboard(mock_app)

    # All 3 methods should be called (try-all pattern)
    mock_osc52.assert_called_once_with("test")
    mock_pyperclip.assert_called_once_with("test")
    mock_app.copy_to_clipboard.assert_called_once_with("test")
    mock_app.notify.assert_called_once()
    assert "copied to clipboard" in mock_app.notify.call_args[0][0]


@patch("vibe.cli.clipboard.shutil.which")
@patch("vibe.cli.clipboard.platform.system")
@patch("vibe.cli.clipboard._copy_osc52")
@patch("vibe.cli.clipboard.pyperclip.copy")
def test_integration_try_all_continues_after_osc52_failure(
    mock_pyperclip: MagicMock,
    mock_osc52: MagicMock,
    mock_system: MagicMock,
    mock_which: MagicMock,
    mock_app: MagicMock,
) -> None:
    """Integration: verify pyperclip is called even when OSC52 fails."""
    mock_system.return_value = "Darwin"
    mock_osc52.side_effect = Exception("OSC52 failed")
    widget = MockWidget(
        text_selection=SimpleNamespace(), get_selection_result=("test", None)
    )
    mock_app.query.return_value = [widget]

    copy_selection_to_clipboard(mock_app)

    mock_osc52.assert_called_once_with("test")
    mock_pyperclip.assert_called_once_with("test")
    mock_app.copy_to_clipboard.assert_called_once_with("test")
    # Should still succeed because pyperclip worked
    assert "copied to clipboard" in mock_app.notify.call_args[0][0]


@patch("vibe.cli.clipboard.shutil.which")
@patch("vibe.cli.clipboard.platform.system")
@patch("vibe.cli.clipboard._copy_osc52")
@patch("vibe.cli.clipboard.pyperclip.copy")
def test_integration_all_methods_fail_shows_error(
    mock_pyperclip: MagicMock,
    mock_osc52: MagicMock,
    mock_system: MagicMock,
    mock_which: MagicMock,
    mock_app: MagicMock,
) -> None:
    """Integration: verify error notification when all methods fail."""
    mock_system.return_value = "Darwin"
    mock_osc52.side_effect = Exception("OSC52 failed")
    mock_pyperclip.side_effect = Exception("pyperclip failed")
    mock_app.copy_to_clipboard.side_effect = Exception("app copy failed")
    widget = MockWidget(
        text_selection=SimpleNamespace(), get_selection_result=("test", None)
    )
    mock_app.query.return_value = [widget]

    copy_selection_to_clipboard(mock_app)

    # All methods attempted
    mock_osc52.assert_called_once()
    mock_pyperclip.assert_called_once()
    mock_app.copy_to_clipboard.assert_called_once()
    # Error notification
    mock_app.notify.assert_called_once_with(
        "Failed to copy - no clipboard method available", severity="warning", timeout=3
    )


@patch("vibe.cli.clipboard.subprocess.run")
@patch("vibe.cli.clipboard.shutil.which")
@patch("vibe.cli.clipboard.platform.system")
@patch("vibe.cli.clipboard._copy_osc52")
@patch("vibe.cli.clipboard.pyperclip.copy")
def test_integration_linux_with_xclip_calls_xclip_first(
    mock_pyperclip: MagicMock,
    mock_osc52: MagicMock,
    mock_system: MagicMock,
    mock_which: MagicMock,
    mock_subprocess: MagicMock,
    mock_app: MagicMock,
) -> None:
    """Integration: verify xclip is called first on Linux when available."""
    mock_system.return_value = "Linux"
    mock_which.side_effect = lambda cmd: "/usr/bin/xclip" if cmd == "xclip" else None
    widget = MockWidget(
        text_selection=SimpleNamespace(), get_selection_result=("test", None)
    )
    mock_app.query.return_value = [widget]

    copy_selection_to_clipboard(mock_app)

    # xclip should be called (via subprocess)
    mock_subprocess.assert_called()
    xclip_call = mock_subprocess.call_args_list[0]
    assert xclip_call[0][0] == ["xclip", "-selection", "clipboard"]
    # Other methods also called (try-all)
    mock_osc52.assert_called_once()
    mock_pyperclip.assert_called_once()
    mock_app.copy_to_clipboard.assert_called_once()
