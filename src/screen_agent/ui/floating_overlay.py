"""Floating overlay window that follows the mouse and displays agent reasoning."""

import ctypes
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCursor, QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

from ..models.action import StepInfo
from .styles import OVERLAY_STYLE


class FloatingOverlay(QWidget):
    """
    Floating information window that:
    - Follows the mouse position (offset to the right)
    - Is click-through (WS_EX_TRANSPARENT on Windows)
    - Displays agent's reasoning and observation
    - Has semi-transparent background
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Window flags for floating overlay
        self.setWindowFlags(
            Qt.FramelessWindowHint |      # No window frame
            Qt.WindowStaysOnTopHint |     # Always on top
            Qt.Tool |                      # Don't show in taskbar
            Qt.WindowTransparentForInput   # Transparent for input
        )

        # Enable transparency
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Set width range for auto-fit text
        self.setMinimumWidth(280)
        self.setMaximumWidth(450)
        self.setMinimumHeight(100)

        self._setup_ui()
        self._setup_timer()

        # Counter for periodic topmost refresh
        self._topmost_counter = 0

        # Apply click-through after window is created
        QTimer.singleShot(100, self._set_click_through)

    def _setup_ui(self):
        """Set up the UI layout."""
        # Main container with styling
        self.container = QWidget(self)
        self.container.setObjectName("overlayContainer")
        self.container.setStyleSheet(OVERLAY_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.container)

        # Inner layout
        inner_layout = QVBoxLayout(self.container)
        inner_layout.setContentsMargins(12, 10, 12, 10)
        inner_layout.setSpacing(2)

        # Action label (e.g., "Click at (500, 300)")
        self.action_label = QLabel("Waiting...")
        self.action_label.setObjectName("actionLabel")
        self.action_label.setWordWrap(True)
        inner_layout.addWidget(self.action_label)

        # Observation section (at top)
        observation_header = QLabel("Observation:")
        observation_header.setObjectName("sectionLabel")
        inner_layout.addWidget(observation_header)

        self.observation_label = QLabel("")
        self.observation_label.setObjectName("contentLabel")
        self.observation_label.setWordWrap(True)
        inner_layout.addWidget(self.observation_label)

        # Reasoning section (at bottom)
        reasoning_header = QLabel("Reasoning:")
        reasoning_header.setObjectName("sectionLabel")
        inner_layout.addWidget(reasoning_header)

        self.reasoning_label = QLabel("")
        self.reasoning_label.setObjectName("contentLabel")
        self.reasoning_label.setWordWrap(True)
        inner_layout.addWidget(self.reasoning_label)

        inner_layout.addStretch()

    def _setup_timer(self):
        """Set up the timer for following the mouse."""
        self.follow_timer = QTimer(self)
        self.follow_timer.timeout.connect(self._follow_mouse)
        # Timer will be started when overlay is shown

    def _set_click_through(self):
        """Set window to be click-through on Windows."""
        try:
            hwnd = int(self.winId())
            # Get current extended style
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            # Add WS_EX_LAYERED (0x80000) and WS_EX_TRANSPARENT (0x20)
            new_style = ex_style | 0x80000 | 0x20
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, new_style)
        except Exception as e:
            print(f"Warning: Could not set click-through: {e}")

        # Force window to be topmost using Windows API
        self._set_topmost()

    def _set_topmost(self):
        """Force window to stay on top of all other windows."""
        try:
            hwnd = int(self.winId())
            # HWND_TOPMOST = -1, SWP_NOMOVE = 0x0002, SWP_NOSIZE = 0x0001
            # SWP_NOACTIVATE = 0x0010
            ctypes.windll.user32.SetWindowPos(
                hwnd, -1,  # HWND_TOPMOST
                0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0010  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
            )
        except Exception as e:
            print(f"Warning: Could not set topmost: {e}")

    def _follow_mouse(self):
        """Update window position to follow the mouse."""
        # Periodically re-assert topmost to stay above other windows (every ~500ms)
        self._topmost_counter += 1
        if self._topmost_counter >= 10:
            self._topmost_counter = 0
            self._set_topmost()

        cursor_pos = QCursor.pos()

        # Get screen geometry to avoid going off-screen
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()

            # Calculate new position (right side of cursor, offset by 30px)
            new_x = cursor_pos.x() + 30
            new_y = cursor_pos.y() - 50

            # Ensure window stays on screen
            if new_x + self.width() > screen_rect.right():
                # Show on left side of cursor if too far right
                new_x = cursor_pos.x() - self.width() - 30

            if new_y < screen_rect.top():
                new_y = screen_rect.top() + 10

            if new_y + self.height() > screen_rect.bottom():
                new_y = screen_rect.bottom() - self.height() - 10

            self.move(new_x, new_y)

    def update_info(self, step_info: StepInfo):
        """
        Update the overlay with new step information.

        Args:
            step_info: StepInfo object containing action, reasoning, observation
        """
        # Update action label
        action_text = f"Step {step_info.step_number}: {step_info.action}"
        self.action_label.setText(action_text)

        # Update reasoning (allow more text)
        reasoning_text = step_info.reasoning or "(No reasoning provided)"
        if len(reasoning_text) > 400:
            reasoning_text = reasoning_text[:400] + "..."
        self.reasoning_label.setText(reasoning_text)

        # Update observation (allow more text)
        observation_text = step_info.observation or "(No observation yet)"
        if len(observation_text) > 400:
            observation_text = observation_text[:400] + "..."
        self.observation_label.setText(observation_text)

        # Adjust size based on content
        self.adjustSize()

        # Also adjust container
        self.container.adjustSize()

    def show(self):
        """Show the overlay and start following the mouse."""
        super().show()
        self.follow_timer.start(50)  # 20 FPS
        self._set_click_through()

    def hide(self):
        """Hide the overlay and stop following the mouse."""
        self.follow_timer.stop()
        super().hide()

    def set_waiting(self):
        """Set overlay to waiting state."""
        self.action_label.setText("Waiting for next action...")
        self.reasoning_label.setText("")
        self.observation_label.setText("")
