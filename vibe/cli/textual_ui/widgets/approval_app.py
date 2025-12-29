from __future__ import annotations

import logging
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from vibe.cli.textual_ui.renderers import get_renderer
from vibe.core.config import VibeConfig

logger = logging.getLogger(__name__)


class ApprovalApp(Container):
    can_focus = True
    can_focus_children = False

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
        Binding("1", "select_1", "Yes", show=False),
        Binding("y", "select_1", "Yes", show=False),
        # Binding("2", "select_2", "Always Tool Session", show=False),  # DISABLED: use shift+tab to auto-approve
        Binding("3", "select_3", "No", show=False),
        Binding("n", "select_3", "No", show=False),
    ]

    class ApprovalGranted(Message):
        def __init__(self, tool_name: str, tool_args: dict) -> None:
            super().__init__()
            self.tool_name = tool_name
            self.tool_args = tool_args

    class ApprovalGrantedAlwaysTool(Message):
        def __init__(
            self, tool_name: str, tool_args: dict, save_permanently: bool
        ) -> None:
            super().__init__()
            self.tool_name = tool_name
            self.tool_args = tool_args
            self.save_permanently = save_permanently

    class ApprovalRejected(Message):
        def __init__(self, tool_name: str, tool_args: dict) -> None:
            super().__init__()
            self.tool_name = tool_name
            self.tool_args = tool_args

    def __init__(
        self, tool_name: str, tool_args: dict, workdir: str, config: VibeConfig
    ) -> None:
        super().__init__(id="approval-app")
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.workdir = workdir
        self.config = config
        self.selected_option = 0
        self.content_container: Vertical | None = None
        self.title_widget: Static | None = None
        self.tool_info_container: Vertical | None = None
        self.option_widgets: list[Static] = []
        self.help_widget: Static | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-content"):
            self.title_widget = Static(
                f"⚠ {self.tool_name} command", classes="approval-title"
            )
            yield self.title_widget

            with VerticalScroll(classes="approval-tool-info-scroll"):
                self.tool_info_container = Vertical(
                    classes="approval-tool-info-container"
                )
                yield self.tool_info_container

            yield Static("")

            for _ in range(3):
                widget = Static("", classes="approval-option")
                self.option_widgets.append(widget)
                yield widget

            yield Static("")

            self.help_widget = Static(
                "↑↓ navigate  Enter select  ESC reject", classes="approval-help"
            )
            yield self.help_widget

    async def on_mount(self) -> None:
        logger.debug("APPROVAL: on_mount called, id=%s", self.id)
        await self._update_tool_info()
        self._update_options()
        self.focus()
        logger.debug("APPROVAL: focus() called, has_focus=%s", self.has_focus)

    async def _update_tool_info(self) -> None:
        if not self.tool_info_container:
            return

        renderer = get_renderer(self.tool_name)
        widget_class, data = renderer.get_approval_widget(self.tool_args)

        await self.tool_info_container.remove_children()
        approval_widget = widget_class(data)
        await self.tool_info_container.mount(approval_widget)

    def _update_options(self) -> None:
        options = [
            ("Yes", "yes"),
            (f"Yes and always allow {self.tool_name} this session", "yes"),
            ("No and tell the agent what to do instead", "no"),
        ]

        for idx, ((text, color_type), widget) in enumerate(
            zip(options, self.option_widgets, strict=True)
        ):
            is_selected = idx == self.selected_option

            cursor = "› " if is_selected else "  "
            option_text = f"{cursor}{idx + 1}. {text}"

            widget.update(option_text)

            widget.remove_class("approval-cursor-selected")
            widget.remove_class("approval-option-selected")
            widget.remove_class("approval-option-yes")
            widget.remove_class("approval-option-no")
            widget.remove_class("approval-option-disabled")

            # Option 1 (index 1) is disabled - gray it out
            if idx == 1:
                widget.add_class("approval-option-disabled")
                continue

            if is_selected:
                widget.add_class("approval-cursor-selected")
                if color_type == "yes":
                    widget.add_class("approval-option-yes")
                else:
                    widget.add_class("approval-option-no")
            else:
                widget.add_class("approval-option-selected")
                if color_type == "yes":
                    widget.add_class("approval-option-yes")
                else:
                    widget.add_class("approval-option-no")

    def action_move_up(self) -> None:
        logger.debug("APPROVAL: action_move_up triggered")
        # Skip option 1 (disabled)
        self.selected_option = 0 if self.selected_option == 2 else 2
        self._update_options()

    def action_move_down(self) -> None:
        logger.debug("APPROVAL: action_move_down triggered")
        # Skip option 1 (disabled)
        self.selected_option = 2 if self.selected_option == 0 else 0
        self._update_options()

    def action_select(self) -> None:
        logger.debug("APPROVAL: action_select triggered (Enter)")
        self._handle_selection(self.selected_option)

    def action_select_1(self) -> None:
        logger.debug("APPROVAL: action_select_1 triggered (1 or y)")
        self.selected_option = 0
        self._handle_selection(0)

    def action_select_2(self) -> None:
        logger.debug("APPROVAL: action_select_2 triggered (disabled)")
        self.selected_option = 1
        self._handle_selection(1)

    def action_select_3(self) -> None:
        logger.debug("APPROVAL: action_select_3 triggered (3 or n)")
        self.selected_option = 2
        self._handle_selection(2)

    def action_reject(self) -> None:
        logger.debug("APPROVAL: action_reject triggered (ESC)")
        self.selected_option = 2
        self._handle_selection(2)

    def _handle_selection(self, option: int) -> None:
        logger.debug("APPROVAL: _handle_selection called, option=%d", option)
        if option == 1:  # Option 2 disabled - use shift+tab for auto-approve
            logger.debug("APPROVAL: option 1 is disabled, returning")
            return
        match option:
            case 0:
                self.post_message(
                    self.ApprovalGranted(
                        tool_name=self.tool_name, tool_args=self.tool_args
                    )
                )
            case 1:
                self.post_message(
                    self.ApprovalGrantedAlwaysTool(
                        tool_name=self.tool_name,
                        tool_args=self.tool_args,
                        save_permanently=False,
                    )
                )
            case 2:
                self.post_message(
                    self.ApprovalRejected(
                        tool_name=self.tool_name, tool_args=self.tool_args
                    )
                )

    def on_blur(self, event: events.Blur) -> None:
        logger.debug("APPROVAL: on_blur triggered, refocusing...")
        self.call_after_refresh(self.focus)

    def on_key(self, event: events.Key) -> None:
        logger.debug(
            "APPROVAL: on_key received: key=%s, character=%s",
            event.key,
            event.character,
        )

    def on_mouse_down(self, event: events.MouseDown) -> None:
        logger.debug("APPROVAL: on_mouse_down received: x=%d, y=%d", event.x, event.y)

    def on_click(self, event: events.Click) -> None:
        logger.debug("APPROVAL: on_click received: x=%d, y=%d", event.x, event.y)
