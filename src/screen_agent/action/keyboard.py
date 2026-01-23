"""Keyboard controller using pyautogui."""

from typing import List

import pyautogui
import pyperclip


class KeyboardController:
    """Keyboard control wrapper around pyautogui."""

    def __init__(self, typing_interval: float = 0.05):
        """
        Initialize keyboard controller.

        Args:
            typing_interval: Interval between keystrokes when typing
        """
        self.typing_interval = typing_interval

    def type_text(self, text: str, interval: float = None) -> None:
        """
        Type ASCII text.

        Args:
            text: Text to type (ASCII only)
            interval: Interval between keys (uses default if None)
        """
        pyautogui.write(text, interval=interval or self.typing_interval)

    def type_text_unicode(self, text: str) -> None:
        """
        Type Unicode text using clipboard.

        This method supports non-ASCII characters like Chinese, Japanese, etc.

        Args:
            text: Text to type (any Unicode)
        """
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")

    def type_smart(self, text: str) -> None:
        """
        Automatically choose the best typing method.

        Uses direct typing for ASCII, clipboard for Unicode.

        Args:
            text: Text to type
        """
        if self._is_ascii(text):
            self.type_text(text)
        else:
            self.type_text_unicode(text)

    def press_key(self, key: str) -> None:
        """
        Press a single key.

        Args:
            key: Key name (e.g., 'enter', 'tab', 'escape')
        """
        pyautogui.press(key)

    def hotkey(self, *keys: str) -> None:
        """
        Press a key combination.

        Args:
            keys: Key names to press together (e.g., 'ctrl', 'c')
        """
        pyautogui.hotkey(*keys)

    def key_down(self, key: str) -> None:
        """
        Hold down a key.

        Args:
            key: Key name to hold
        """
        pyautogui.keyDown(key)

    def key_up(self, key: str) -> None:
        """
        Release a held key.

        Args:
            key: Key name to release
        """
        pyautogui.keyUp(key)

    def _is_ascii(self, text: str) -> bool:
        """Check if text contains only ASCII characters."""
        return all(ord(c) < 128 for c in text)
