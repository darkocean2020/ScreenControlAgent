"""Keyboard controller using pyautogui."""

import random
import time
from typing import List

import pyautogui
import pyperclip


class KeyboardController:
    """Keyboard control wrapper around pyautogui."""

    def __init__(self, typing_interval: float = 0.05, human_like: bool = True):
        """
        Initialize keyboard controller.

        Args:
            typing_interval: Base interval between keystrokes when typing
            human_like: Enable human-like typing with random delays
        """
        self.typing_interval = typing_interval
        self.human_like = human_like

    def _get_typing_delay(self) -> float:
        """Get a human-like random typing delay."""
        if self.human_like:
            # Random delay between 0.03 and 0.12 seconds, with occasional pauses
            base_delay = random.uniform(0.03, 0.10)
            # 10% chance of a longer pause (like thinking)
            if random.random() < 0.10:
                base_delay += random.uniform(0.1, 0.3)
            return base_delay
        return self.typing_interval

    def type_text(self, text: str, interval: float = None) -> None:
        """
        Type ASCII text with human-like delays.

        Args:
            text: Text to type (ASCII only)
            interval: Interval between keys (uses default if None)
        """
        if self.human_like:
            for char in text:
                pyautogui.write(char, interval=0)
                time.sleep(self._get_typing_delay())
        else:
            pyautogui.write(text, interval=interval or self.typing_interval)

    def type_text_unicode(self, text: str) -> None:
        """
        Type Unicode text character by character with human-like delays.

        This method supports non-ASCII characters like Chinese, Japanese, etc.
        Each character is typed individually to simulate human typing.

        Args:
            text: Text to type (any Unicode)
        """
        for char in text:
            pyperclip.copy(char)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(self._get_typing_delay())

    def type_smart(self, text: str) -> None:
        """
        Automatically choose the best typing method with human-like effect.

        Uses direct typing for ASCII, clipboard for Unicode.
        Both methods simulate human typing speed.

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
