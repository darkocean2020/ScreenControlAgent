"""Main control window for ScreenControlAgent."""

from typing import Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QMessageBox, QSizePolicy, QShortcut
)

from ..models.action import StepInfo
from ..utils.config import load_config
from ..perception.vlm_client import OpenAIVLMClient
from ..brain.openai_controller import OpenAILLMController, StepResult
from .floating_overlay import FloatingOverlay
from .styles import MAIN_WINDOW_STYLE


class LLMControllerThread(QThread):
    """Background thread for running the LLM controller."""

    finished = pyqtSignal(bool)  # Emits success status
    step_completed = pyqtSignal(object)  # Emits StepResult
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, controller: LLMController, task: str, max_steps: int = 0):
        super().__init__()
        self.controller = controller
        self.task = task
        self.max_steps = max_steps
        self._stopped = False

    def run(self):
        """Run the LLM controller task."""
        try:
            print(f"[LLMThread] Starting controller.run()")
            success = self.controller.run(self.task, max_steps=self.max_steps)
            print(f"[LLMThread] Controller finished, success={success}")
            self.finished.emit(success)
        except Exception as e:
            import traceback
            error_msg = str(e) if str(e) else "Unknown thread error"
            print(f"[LLMThread] Error: {error_msg}")
            traceback.print_exc()
            self.error_occurred.emit(error_msg)
            self.finished.emit(False)

    def stop(self):
        """Request the controller to stop."""
        self._stopped = True
        if self.controller and self.controller.state:
            self.controller.state.is_completed = True


class MainWindow(QMainWindow):
    """Main control window with task input and start/stop buttons."""

    # Signal for thread-safe UI updates
    update_overlay_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()

        self.controller: Optional[LLMController] = None
        self.agent_thread: Optional[LLMControllerThread] = None
        self.overlay = FloatingOverlay()
        self.subtitle_label: Optional[QLabel] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the main window UI."""
        self.setWindowTitle("ScreenControlAgent")
        self.setMinimumSize(500, 250)
        self.resize(600, 300)
        self.setStyleSheet(MAIN_WINDOW_STYLE)

        # Central widget
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        # Main layout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("ScreenControlAgent")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Subtitle (dynamic based on config)
        self.subtitle_label = QLabel("LLM-Driven Mode")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.subtitle_label)

        # Update subtitle based on config
        self._update_subtitle()

        # Task input (multi-line, resizable)
        task_label = QLabel("Task:")
        layout.addWidget(task_label)

        self.task_input = QTextEdit()
        self.task_input.setPlaceholderText("Enter task, e.g.: Open Notepad and type Hello World")
        self.task_input.setMinimumHeight(60)
        self.task_input.setMaximumHeight(150)
        self.task_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.task_input, stretch=1)

        # Buttons row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setFixedWidth(100)
        button_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedWidth(100)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Status row
        status_layout = QHBoxLayout()

        self.status_label = QLabel("Status: Idle")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label, stretch=1)

        self.progress_label = QLabel("")
        status_layout.addWidget(self.progress_label)

        layout.addLayout(status_layout)

    def _connect_signals(self):
        """Connect button signals."""
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.update_overlay_signal.connect(self._update_overlay)

        # Ctrl+Enter to start task
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._on_start)

    def _update_subtitle(self):
        """Update subtitle based on current configuration."""
        try:
            config = load_config()
            controller_config = getattr(config, 'controller', None)

            if controller_config and hasattr(controller_config, 'llm'):
                model = controller_config.llm.get('model', 'gpt-4.5-preview')
                self.subtitle_label.setText(f"OpenAI Mode ({model})")
            else:
                self.subtitle_label.setText("OpenAI Mode (gpt-4.5-preview)")
        except Exception:
            self.subtitle_label.setText("OpenAI Mode")

    def _on_start(self):
        """Handle start button click."""
        task = self.task_input.toPlainText().strip()
        if not task:
            QMessageBox.warning(self, "Warning", "Please enter a task description.")
            return

        try:
            # Load config
            print(f"[UI] Starting task: {task}")
            config = load_config()
            print(f"[UI] Config loaded")

            self._start_controller(task, config)

        except Exception as e:
            import traceback
            error_msg = str(e) if str(e) else "Unknown error"
            print(f"[UI] Error: {error_msg}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to start agent:\n{error_msg}")

    def _start_controller(self, task: str, config):
        """Start the OpenAI LLM controller."""
        from ..perception.ui_automation import UIAutomationClient

        print(f"[UI] Starting OpenAI LLM mode")

        # Check OpenAI API key
        if not config.openai_api_key:
            QMessageBox.critical(self, "Error", "OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
            return

        # Get LLM model from config
        controller_config = getattr(config, 'controller', None)
        llm_model = "gpt-5.2"
        if controller_config and hasattr(controller_config, 'llm'):
            llm_model = controller_config.llm.get('model', 'gpt-4.5-preview')

        print(f"[UI] LLM Model: {llm_model}")

        # Create VLM client for look_at_screen tool
        vlm_model = config.vlm.openai_model
        print(f"[UI] VLM Model: {vlm_model}")

        vlm_client = OpenAIVLMClient(
            api_key=config.openai_api_key,
            model=vlm_model
        )

        # Create UIAutomation client
        uia_client = None
        try:
            uia_client = UIAutomationClient(
                max_depth=getattr(config.grounding, 'uia_max_depth', 15),
                cache_duration=getattr(config.grounding, 'uia_cache_duration', 0.5)
            )
            print(f"[UI] UIAutomation client created")
        except Exception as e:
            print(f"[UI] Warning: Failed to initialize UIAutomation: {e}")

        # Create OpenAI LLM controller
        print(f"[UI] Creating OpenAI controller with model: {llm_model}")
        self.controller = OpenAILLMController(
            api_key=config.openai_api_key,
            model=llm_model,
            vlm_client=vlm_client,
            uia_client=uia_client,
            max_tokens=4096,
            monitor_index=config.screen.monitor_index,
            action_delay=config.agent.action_delay,
            on_step_callback=self._on_step
        )

        # Minimize main window to prevent clicking on it
        self.showMinimized()

        # Show overlay
        self.overlay.set_waiting()
        self.overlay.show()

        # Start controller thread
        self.agent_thread = LLMControllerThread(
            self.controller, task, max_steps=config.agent.max_steps
        )
        self.agent_thread.finished.connect(self._on_task_finished)
        self.agent_thread.error_occurred.connect(self._on_error)
        self.agent_thread.start()

        # Update UI state
        self.status_label.setText("Status: Running")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.task_input.setEnabled(False)

    def _on_step(self, step_result: StepResult):
        """Callback from LLM controller when a tool is executed."""
        try:
            print(f"[Callback] Tool: {step_result.tool_name}")
            result_preview = step_result.tool_result[:100] if step_result.tool_result else 'None'
            print(f"[Callback] Result: {result_preview}...")
        except UnicodeEncodeError:
            # Handle encoding issues on Windows consoles
            print(f"[Callback] Tool: {step_result.tool_name}")
            print("[Callback] Result: (contains non-printable characters)...")

        # Convert to StepInfo-like object for overlay
        step_info = StepInfo(
            step_number=len(self.controller.get_tool_history()) if self.controller else 0,
            action=None,
            reasoning=f"Tool: {step_result.tool_name}",
            observation=step_result.tool_result[:200] if step_result.tool_result else "",
            verification=None,
            mouse_position=(0, 0)
        )
        self.update_overlay_signal.emit(step_info)

    def _on_stop(self):
        """Handle stop button click."""
        if self.agent_thread:
            self.agent_thread.stop()

        self.overlay.hide()
        self.showNormal()  # Restore main window
        self.status_label.setText("Status: Stopped")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.task_input.setEnabled(True)

    def _update_overlay(self, step_info: StepInfo):
        """Update overlay in the main thread."""
        print(f"[UI Update] Updating overlay for step {step_info.step_number}")
        self.overlay.update_info(step_info)
        self.progress_label.setText(f"Step {step_info.step_number}")

    def _on_task_finished(self, success: bool):
        """Handle task completion."""
        self.overlay.hide()
        self.showNormal()  # Restore main window

        if success:
            self.status_label.setText("Status: Completed")
        else:
            self.status_label.setText("Status: Failed")

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.task_input.setEnabled(True)
        self.progress_label.setText("")

    def _on_error(self, error_msg: str):
        """Handle error from agent thread."""
        print(f"[UI] Received error signal: {error_msg}")
        self.overlay.hide()
        self.showNormal()  # Restore main window
        self.status_label.setText("Status: Error")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.task_input.setEnabled(True)
        QMessageBox.critical(self, "Agent Error", f"Error during execution:\n\n{error_msg}")

    def closeEvent(self, event):
        """Handle window close."""
        if self.agent_thread and self.agent_thread.isRunning():
            self.agent_thread.stop()
            self.agent_thread.wait(2000)

        self.overlay.close()
        event.accept()
