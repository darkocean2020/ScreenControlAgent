"""Mouse controller using pyautogui with human-like movements."""

import random
from typing import Optional, Tuple

import pyautogui


class MouseController:
    """Mouse control wrapper around pyautogui with human-like behavior."""

    def __init__(
        self,
        move_duration: float = 0.3,
        fail_safe: bool = True,
        human_like: bool = True
    ):
        """
        Initialize mouse controller.

        Args:
            move_duration: Default duration for mouse movements
            fail_safe: Enable pyautogui fail-safe (move to corner to abort)
            human_like: Enable human-like mouse movements
        """
        self.move_duration = move_duration
        self.human_like = human_like
        pyautogui.FAILSAFE = fail_safe
        pyautogui.PAUSE = 0.05  # Reduced pause for smoother movement

    def _get_human_duration(self, x: int, y: int) -> float:
        """
        Calculate human-like duration based on distance.

        Humans move faster for longer distances but not linearly.
        """
        if not self.human_like:
            return self.move_duration

        # Get current position
        current = pyautogui.position()
        distance = ((x - current.x) ** 2 + (y - current.y) ** 2) ** 0.5

        # Human-like duration: logarithmic scaling with some randomness
        # Short distances: ~0.2s, Long distances: ~0.5s
        base_duration = 0.15 + (distance / 2000) * 0.4
        # Add small random variation (humans aren't perfectly consistent)
        variation = random.uniform(-0.05, 0.08)
        duration = max(0.1, min(0.6, base_duration + variation))

        return duration

    def move_to(self, x: int, y: int, duration: Optional[float] = None) -> None:
        """
        Move mouse to specified position with human-like motion.

        Args:
            x: X coordinate
            y: Y coordinate
            duration: Movement duration (auto-calculated if None and human_like=True)
        """
        if duration is None:
            duration = self._get_human_duration(x, y)

        # Use easeOutQuad for natural deceleration (like a human stopping)
        pyautogui.moveTo(
            x, y,
            duration=duration,
            tween=pyautogui.easeOutQuad
        )

    def click(self, x: int, y: int, button: str = "left") -> None:
        """
        Move to position and click with human-like motion.

        Args:
            x: X coordinate
            y: Y coordinate
            button: Mouse button ('left', 'right', 'middle')
        """
        # First move to the position smoothly
        self.move_to(x, y)
        # Small pause before clicking (like a human)
        if self.human_like:
            pyautogui.sleep(random.uniform(0.02, 0.08))
        # Then click
        pyautogui.click(button=button)

    def double_click(self, x: int, y: int) -> None:
        """
        Move to position and double-click with human-like motion.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        # First move to the position smoothly
        self.move_to(x, y)
        # Small pause before clicking
        if self.human_like:
            pyautogui.sleep(random.uniform(0.02, 0.08))
        # Then double click
        pyautogui.doubleClick()

    def right_click(self, x: int, y: int) -> None:
        """
        Move to position and right-click with human-like motion.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        # First move to the position smoothly
        self.move_to(x, y)
        # Small pause before clicking
        if self.human_like:
            pyautogui.sleep(random.uniform(0.02, 0.08))
        # Then right click
        pyautogui.rightClick()

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """
        Scroll the mouse wheel.

        Args:
            clicks: Number of scroll clicks (positive=up, negative=down)
            x: Optional X position to scroll at
            y: Optional Y position to scroll at
        """
        import time

        if x is None or y is None:
            # Move to center of screen first to ensure we scroll the main content area
            screen_width, screen_height = pyautogui.size()
            center_x = screen_width // 2
            center_y = screen_height // 2
            self.move_to(center_x, center_y)
            time.sleep(0.15)
            target_x, target_y = None, None
        else:
            target_x, target_y = x, y

        # Amplify scroll amount 100x for visible effect
        clicks = clicks * 100

        # Scroll in multiple smaller steps so the OS/browser processes each one
        step = 3 if clicks > 0 else -3
        remaining = abs(clicks)
        while remaining > 0:
            batch = min(remaining, 3)
            actual = batch if clicks > 0 else -batch
            pyautogui.scroll(actual, x=target_x, y=target_y)
            remaining -= batch
            if remaining > 0:
                time.sleep(0.05)

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
