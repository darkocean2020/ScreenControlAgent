"""Main control window for ScreenControlAgent."""

from typing import Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMetaObject, Q_ARG
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QMessageBox
)

from ..models.action import StepInfo
from ..utils.config import load_config
from ..perception.vlm_client import ClaudeVLMClient, OpenAIVLMClient
from ..agent import ScreenControlAgent
from .floating_overlay import FloatingOverlay
from .styles import MAIN_WINDOW_STYLE


class AgentThread(QThread):
    """Background thread for running the agent."""

    finished = pyqtSignal(bool)  # Emits success status
    step_completed = pyqtSignal(object)  # Emits StepInfo
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, agent: ScreenControlAgent, task: str):
        super().__init__()
        self.agent = agent
        self.task = task
        self._stopped = False

    def run(self):
        """Run the agent task."""
        try:
            print(f"[Thread] Starting agent.run()")
            success = self.agent.run(self.task)
            print(f"[Thread] Agent finished, success={success}")
            self.finished.emit(success)
        except Exception as e:
            import traceback
            error_msg = str(e) if str(e) else "Unknown thread error"
            print(f"[Thread] Error: {error_msg}")
            traceback.print_exc()
            self.error_occurred.emit(error_msg)
            self.finished.emit(False)

    def stop(self):
        """Request the agent to stop."""
        self._stopped = True
        if self.agent and self.agent.state:
            self.agent.state.is_completed = True


class MainWindow(QMainWindow):
    """Main control window with task input and start/stop buttons."""

    # Signal for thread-safe UI updates
    update_overlay_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()

        self.agent: Optional[ScreenControlAgent] = None
        self.agent_thread: Optional[AgentThread] = None
        self.overlay = FloatingOverlay()

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the main window UI."""
        self.setWindowTitle("ScreenControlAgent")
        self.setFixedSize(500, 200)
        self.setStyleSheet(MAIN_WINDOW_STYLE)

        # Central widget
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        # Main layout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel("ScreenControlAgent")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Task input row
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("Enter task, e.g.: Open Notepad and type Hello World")
        self.task_input.returnPressed.connect(self._on_start)
        input_layout.addWidget(self.task_input, stretch=1)

        layout.addLayout(input_layout)

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
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.progress_label = QLabel("")
        status_layout.addWidget(self.progress_label)

        layout.addLayout(status_layout)

        layout.addStretch()

    def _connect_signals(self):
        """Connect button signals."""
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.update_overlay_signal.connect(self._update_overlay)

    def _on_start(self):
        """Handle start button click."""
        task = self.task_input.text().strip()
        if not task:
            QMessageBox.warning(self, "Warning", "Please enter a task description.")
            return

        try:
            # Load config and create agent
            print(f"[UI] Starting task: {task}")
            config = load_config()
            print(f"[UI] Config loaded, provider: {config.vlm.provider}")

            # Create VLM client
            print(f"[UI] Creating VLM client...")
            if config.vlm.provider == "claude":
                if not config.anthropic_api_key:
                    QMessageBox.critical(self, "Error", "Anthropic API key not found in environment.")
                    return
                print(f"[UI] Using Claude model: {config.vlm.claude_model}")
                vlm_client = ClaudeVLMClient(
                    api_key=config.anthropic_api_key,
                    model=config.vlm.claude_model
                )
            else:
                if not config.openai_api_key:
                    QMessageBox.critical(self, "Error", "OpenAI API key not found in environment.")
                    return
                print(f"[UI] Using OpenAI model: {config.vlm.openai_model}")
                vlm_client = OpenAIVLMClient(
                    api_key=config.openai_api_key,
                    model=config.vlm.openai_model
                )
            print(f"[UI] VLM client created")

            # Create agent
            self.agent = ScreenControlAgent(
                vlm_client=vlm_client,
                max_steps=config.agent.max_steps,
                action_delay=config.agent.action_delay,
                verify_each_step=config.agent.verify_each_step,
                monitor_index=config.screen.monitor_index,
                planning_mode=config.grounding.mode,
                grounding_confidence_threshold=config.grounding.confidence_threshold,
                enable_memory=config.memory.enabled,
                enable_task_planning=config.task_planning.enabled,
                enable_error_recovery=config.error_recovery.enabled,
                memory_storage_path=config.memory.long_term_storage,
                max_recovery_attempts=config.error_recovery.max_recovery_attempts
            )

            # Set callback for step updates
            self.agent.on_step_callback = self._on_agent_step

            # Show overlay
            self.overlay.set_waiting()
            self.overlay.show()

            # Start agent thread
            self.agent_thread = AgentThread(self.agent, task)
            self.agent_thread.finished.connect(self._on_task_finished)
            self.agent_thread.error_occurred.connect(self._on_error)
            self.agent_thread.start()

            # Update UI state
            self.status_label.setText("Status: Running")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.task_input.setEnabled(False)

        except Exception as e:
            import traceback
            error_msg = str(e) if str(e) else "Unknown error"
            print(f"[UI] Error: {error_msg}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to start agent:\n{error_msg}")

    def _on_stop(self):
        """Handle stop button click."""
        if self.agent_thread:
            self.agent_thread.stop()

        self.overlay.hide()
        self.status_label.setText("Status: Stopped")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.task_input.setEnabled(True)

    def _on_agent_step(self, step_info: StepInfo):
        """
        Callback from agent when a step completes.
        Called from agent thread, so we emit a signal for thread-safe UI update.
        """
        print(f"[Callback] Step {step_info.step_number}: {step_info.action}")
        print(f"[Callback] Reasoning: {step_info.reasoning[:50] if step_info.reasoning else 'None'}...")
        print(f"[Callback] Observation: {step_info.observation[:50] if step_info.observation else 'None'}...")
        self.update_overlay_signal.emit(step_info)

    def _update_overlay(self, step_info: StepInfo):
        """Update overlay in the main thread."""
        print(f"[UI Update] Updating overlay for step {step_info.step_number}")
        self.overlay.update_info(step_info)
        self.progress_label.setText(f"Step {step_info.step_number}")

    def _on_task_finished(self, success: bool):
        """Handle task completion."""
        self.overlay.hide()

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
