"""Screen capture module using mss for high-performance screenshots."""

import base64
from io import BytesIO
from typing import Optional, Tuple

import mss
from PIL import Image


class ScreenCapture:
    """High-performance screen capture using mss."""

    def __init__(self, monitor_index: int = 1):
        """
        Initialize screen capture.

        Args:
            monitor_index: Monitor index (0=all monitors, 1=primary monitor)
        """
        self.monitor_index = monitor_index
        self._sct = mss.mss()

    def capture(self, region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """
        Capture a screenshot.

        Args:
            region: Optional region (left, top, width, height), None for full screen

        Returns:
            PIL Image object
        """
        if region:
            monitor = {
                "left": region[0],
                "top": region[1],
                "width": region[2],
                "height": region[3]
            }
        else:
            monitor = self._sct.monitors[self.monitor_index]

        screenshot = self._sct.grab(monitor)
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    def capture_to_base64(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        format: str = "PNG",
        quality: int = 85
    ) -> str:
        """
        Capture screenshot and encode as base64.

        Args:
            region: Optional region to capture
            format: Image format (PNG or JPEG)
            quality: JPEG quality (ignored for PNG)

        Returns:
            Base64-encoded image string
        """
        img = self.capture(region)
        buffer = BytesIO()

        if format.upper() == "JPEG":
            img.save(buffer, format="JPEG", quality=quality)
        else:
            img.save(buffer, format="PNG")

        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def get_screen_size(self) -> Tuple[int, int]:
        """
        Get the screen dimensions.

        Returns:
            Tuple of (width, height)
        """
        monitor = self._sct.monitors[self.monitor_index]
        return monitor["width"], monitor["height"]

    def __del__(self):
        """Cleanup mss instance."""
        if hasattr(self, "_sct"):
            self._sct.close()
