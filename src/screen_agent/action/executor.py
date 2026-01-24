"""Action executor that dispatches actions to controllers."""

import time
from typing import Optional

from ..models.action import Action, ActionType
from ..utils.logger import get_logger
from .mouse import MouseController
from .keyboard import KeyboardController

logger = get_logger(__name__)


class ActionExecutor:
    """Executes Action objects using mouse and keyboard controllers."""

    def __init__(
        self,
        mouse_move_duration: float = 0.3,
        typing_interval: float = 0.05,
        fail_safe: bool = True,
        human_like: bool = True
    ):
        """
        Initialize the action executor.

        Args:
            mouse_move_duration: Duration for mouse movements
            typing_interval: Interval between keystrokes
            fail_safe: Enable pyautogui fail-safe
            human_like: Enable human-like mouse movements
        """
        self.mouse = MouseController(
            move_duration=mouse_move_duration,
            fail_safe=fail_safe,
            human_like=human_like
        )
        self.keyboard = KeyboardController(typing_interval=typing_interval)

    def execute(self, action: Action) -> bool:
        """
        Execute an action.

        Args:
            action: Action object to execute

        Returns:
            True if execution succeeded, False otherwise
        """
        try:
            logger.debug(f"Executing: {action}")

            if action.action_type == ActionType.CLICK:
                self._execute_click(action)

            elif action.action_type == ActionType.DOUBLE_CLICK:
                self._execute_double_click(action)

            elif action.action_type == ActionType.RIGHT_CLICK:
                self._execute_right_click(action)

            elif action.action_type == ActionType.TYPE:
                self._execute_type(action)

            elif action.action_type == ActionType.HOTKEY:
                self._execute_hotkey(action)

            elif action.action_type == ActionType.SCROLL:
                self._execute_scroll(action)

            elif action.action_type == ActionType.MOVE:
                self._execute_move(action)

            elif action.action_type == ActionType.WAIT:
                self._execute_wait(action)

            elif action.action_type == ActionType.DONE:
                logger.info("Task marked as done")

            return True

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False

    def _execute_click(self, action: Action) -> None:
        """Execute a click action."""
        if not action.coordinates:
            raise ValueError("Click action requires coordinates")
        x, y = action.coordinates
        self.mouse.click(x, y)

    def _execute_double_click(self, action: Action) -> None:
        """Execute a double-click action."""
        if not action.coordinates:
            raise ValueError("Double-click action requires coordinates")
        x, y = action.coordinates
        self.mouse.double_click(x, y)

    def _execute_right_click(self, action: Action) -> None:
        """Execute a right-click action."""
        if not action.coordinates:
            raise ValueError("Right-click action requires coordinates")
        x, y = action.coordinates
        self.mouse.right_click(x, y)

    def _execute_type(self, action: Action) -> None:
        """Execute a type action."""
        if not action.text:
            raise ValueError("Type action requires text")
        self.keyboard.type_smart(action.text)

    def _execute_hotkey(self, action: Action) -> None:
        """Execute a hotkey action."""
        if not action.keys:
            raise ValueError("Hotkey action requires keys")
        self.keyboard.hotkey(*action.keys)

    def _execute_scroll(self, action: Action) -> None:
        """Execute a scroll action."""
        amount = action.scroll_amount or 3
        x, y = action.coordinates if action.coordinates else (None, None)
        self.mouse.scroll(amount, x, y)

    def _execute_move(self, action: Action) -> None:
        """Execute a mouse move action."""
        if not action.coordinates:
            raise ValueError("Move action requires coordinates")
        x, y = action.coordinates
        self.mouse.move_to(x, y)

    def _execute_wait(self, action: Action) -> None:
        """Execute a wait action."""
        duration = action.duration or 1.0
        time.sleep(duration)
