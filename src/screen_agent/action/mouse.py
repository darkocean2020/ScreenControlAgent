"""Mouse controller using pyautogui."""

from typing import Optional, Tuple

import pyautogui


class MouseController:
    """Mouse control wrapper around pyautogui."""

    def __init__(self, move_duration: float = 0.3, fail_safe: bool = True):
        """
        Initialize mouse controller.

        Args:
            move_duration: Default duration for mouse movements
            fail_safe: Enable pyautogui fail-safe (move to corner to abort)
        """
        self.move_duration = move_duration
        pyautogui.FAILSAFE = fail_safe
        pyautogui.PAUSE = 0.1

    def move_to(self, x: int, y: int, duration: Optional[float] = None) -> None:
        """
        Move mouse to specified position.

        Args:
            x: X coordinate
            y: Y coordinate
            duration: Movement duration (uses default if None)
        """
        pyautogui.moveTo(x, y, duration=duration or self.move_duration)

    def click(self, x: int, y: int, button: str = "left") -> None:
        """
        Click at specified position.

        Args:
            x: X coordinate
            y: Y coordinate
            button: Mouse button ('left', 'right', 'middle')
        """
        pyautogui.click(x, y, button=button)

    def double_click(self, x: int, y: int) -> None:
        """
        Double-click at specified position.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        pyautogui.doubleClick(x, y)

    def right_click(self, x: int, y: int) -> None:
        """
        Right-click at specified position.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        pyautogui.rightClick(x, y)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """
        Scroll the mouse wheel.

        Args:
            clicks: Number of scroll clicks (positive=up, negative=down)
            x: Optional X position to scroll at
            y: Optional Y position to scroll at
        """
        pyautogui.scroll(clicks, x=x, y=y)

    def drag_to(self, x: int, y: int, duration: float = 0.5, button: str = "left") -> None:
        """
        Drag to specified position.

        Args:
            x: Target X coordinate
            y: Target Y coordinate
            duration: Drag duration
            button: Mouse button to hold
        """
        pyautogui.dragTo(x, y, duration=duration, button=button)

    def get_position(self) -> Tuple[int, int]:
        """
        Get current mouse position.

        Returns:
            Tuple of (x, y) coordinates
        """
        pos = pyautogui.position()
        return (pos.x, pos.y)
