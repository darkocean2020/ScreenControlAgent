"""Screen capture module using mss for high-performance screenshots."""

import base64
import threading
from io import BytesIO
from typing import Optional, Tuple

import mss
from PIL import Image


class ScreenCapture:
    """High-performance screen capture using mss.

    Note: mss uses thread-local storage, so we create a new instance
    per thread to support multi-threaded usage.
    """

    def __init__(self, monitor_index: int = 1):
        """
        Initialize screen capture.

        Args:
            monitor_index: Monitor index (0=all monitors, 1=primary monitor)
        """
        self.monitor_index = monitor_index
        self._local = threading.local()

    def _get_sct(self):
        """Get thread-local mss instance."""
        if not hasattr(self._local, 'sct'):
            self._local.sct = mss.mss()
        return self._local.sct

    def capture(self, region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """
        Capture a screenshot.

        Args:
            region: Optional region (left, top, width, height), None for full screen

        Returns:
            PIL Image object
        """
        sct = self._get_sct()

        if region:
            monitor = {
                "left": region[0],
                "top": region[1],
                "width": region[2],
                "height": region[3]
            }
        else:
            monitor = sct.monitors[self.monitor_index]

        screenshot = sct.grab(monitor)
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
        sct = self._get_sct()
        monitor = sct.monitors[self.monitor_index]
        return monitor["width"], monitor["height"]
