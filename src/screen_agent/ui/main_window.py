"""Main control window for ScreenControlAgent."""

from typing import Optional, Union

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMetaObject, Q_ARG
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QMessageBox, QComboBox
)

from ..models.action import StepInfo
from ..utils.config import load_config
from ..perception.vlm_client import (
    ClaudeVLMClient, OpenAIVLMClient,
    ClaudeLLMClient, OpenAILLMClient
)
from ..agent import ScreenControlAgent
from ..brain.llm_controller import LLMController, StepResult
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


class LLMControllerThread(QThread):
    """Background thread for running the LLM controller."""

    finished = pyqtSignal(bool)  # Emits success status
    step_completed = pyqtSignal(object)  # Emits StepResult
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, controller: LLMController, task: str, max_steps: int = 40):
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

        self.agent: Optional[ScreenControlAgent] = None
        self.controller: Optional[LLMController] = None
        self.agent_thread: Optional[Union[AgentThread, LLMControllerThread]] = None
        self.overlay = FloatingOverlay()
        self.current_mode = "llm_driven"  # Default to new mode

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the main window UI."""
        self.setWindowTitle("ScreenControlAgent")
        self.setFixedSize(500, 240)
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

        # Mode selector row
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(10)

        mode_label = QLabel("Mode:")
        mode_layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("LLM-Driven (New)", "llm_driven")
        self.mode_combo.addItem("VLM-Driven (Legacy)", "vlm_driven")
        self.mode_combo.setFixedWidth(180)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)

        mode_layout.addStretch()
        layout.addLayout(mode_layout)

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

    def _on_mode_changed(self, index):
        """Handle mode selection change."""
        self.current_mode = self.mode_combo.currentData()

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
            # Load config
            print(f"[UI] Starting task: {task}")
            config = load_config()
            print(f"[UI] Config loaded, mode: {self.current_mode}")

            if self.current_mode == "llm_driven":
                self._start_llm_driven(task, config)
            else:
                self._start_vlm_driven(task, config)

        except Exception as e:
            import traceback
            error_msg = str(e) if str(e) else "Unknown error"
            print(f"[UI] Error: {error_msg}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to start agent:\n{error_msg}")

    def _start_llm_driven(self, task: str, config):
        """Start in LLM-driven mode."""
        from ..perception.ui_automation import UIAutomationClient

        print(f"[UI] Starting LLM-Driven mode")

        # Get controller config
        controller_config = getattr(config, 'controller', None)

        # Determine LLM settings
        if controller_config and hasattr(controller_config, 'llm'):
            llm_model = controller_config.llm.get('model', 'claude-sonnet-4-20250514')
        else:
            llm_model = 'claude-sonnet-4-20250514'

        # Check API key
        if not config.anthropic_api_key:
            QMessageBox.critical(self, "Error", "Anthropic API key not found.")
            return

        # Create VLM client for look_at_screen tool
        if controller_config and hasattr(controller_config, 'vlm_tool'):
            vlm_provider = controller_config.vlm_tool.get('provider', 'openai')
            vlm_model = controller_config.vlm_tool.get('model', 'gpt-4o')
        else:
            vlm_provider = config.vlm.provider
            vlm_model = config.vlm.openai_model if vlm_provider == 'openai' else config.vlm.claude_model

        print(f"[UI] Creating VLM client for look_at_screen ({vlm_provider}: {vlm_model})...")
        if vlm_provider == "claude":
            vlm_client = ClaudeVLMClient(
                api_key=config.anthropic_api_key,
                model=vlm_model
            )
        else:
            if not config.openai_api_key:
                QMessageBox.critical(self, "Error", "OpenAI API key not found.")
                return
            vlm_client = OpenAIVLMClient(
                api_key=config.openai_api_key,
                model=vlm_model
            )

        # Create UIAutomation client
        uia_client = None
        if config.grounding.enabled:
            try:
                uia_client = UIAutomationClient(
                    max_depth=getattr(config.grounding, 'uia_max_depth', 15),
                    cache_duration=getattr(config.grounding, 'uia_cache_duration', 0.5)
                )
                print(f"[UI] UIAutomation client created")
            except Exception as e:
                print(f"[UI] Warning: Failed to initialize UIAutomation: {e}")

        # Create LLM controller
        print(f"[UI] Creating LLM controller with model: {llm_model}")
        self.controller = LLMController(
            api_key=config.anthropic_api_key,
            model=llm_model,
            vlm_client=vlm_client,
            uia_client=uia_client,
            max_tokens=4096,
            monitor_index=config.screen.monitor_index,
            action_delay=config.agent.action_delay,
            on_step_callback=self._on_llm_step
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
        self.status_label.setText("Status: Running (LLM-Driven)")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.task_input.setEnabled(False)
        self.mode_combo.setEnabled(False)

    def _start_vlm_driven(self, task: str, config):
        """Start in VLM-driven mode (legacy)."""
        print(f"[UI] Starting VLM-Driven mode")

        # Determine planning mode and create clients
        llm_client = None
        planning_mode = config.grounding.mode

        if config.separated_arch.enabled:
            # Separated architecture: VLM for perception, LLM for reasoning
            print(f"[UI] Using SEPARATED architecture")
            planning_mode = "separated"

            # Create VLM client for perception
            print(f"[UI] Creating VLM client for perception ({config.separated_arch.perception_model})...")
            if config.separated_arch.perception_provider == "claude":
                if not config.anthropic_api_key:
                    QMessageBox.critical(self, "Error", "Anthropic API key not found.")
                    return
                vlm_client = ClaudeVLMClient(
                    api_key=config.anthropic_api_key,
                    model=config.separated_arch.perception_model
                )
            else:
                if not config.openai_api_key:
                    QMessageBox.critical(self, "Error", "OpenAI API key not found.")
                    return
                vlm_client = OpenAIVLMClient(
                    api_key=config.openai_api_key,
                    model=config.separated_arch.perception_model
                )

            # Create LLM client for reasoning
            print(f"[UI] Creating LLM client for reasoning ({config.separated_arch.reasoning_model})...")
            if config.separated_arch.reasoning_provider == "claude":
                if not config.anthropic_api_key:
                    QMessageBox.critical(self, "Error", "Anthropic API key not found.")
                    return
                llm_client = ClaudeLLMClient(
                    api_key=config.anthropic_api_key,
                    model=config.separated_arch.reasoning_model
                )
            else:
                if not config.openai_api_key:
                    QMessageBox.critical(self, "Error", "OpenAI API key not found.")
                    return
                llm_client = OpenAILLMClient(
                    api_key=config.openai_api_key,
                    model=config.separated_arch.reasoning_model
                )
            print(f"[UI] LLM client created")
        else:
            # Traditional architecture: single VLM for everything
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
            llm_client=llm_client,
            max_steps=config.agent.max_steps,
            action_delay=config.agent.action_delay,
            verify_each_step=config.agent.verify_each_step,
            monitor_index=config.screen.monitor_index,
            planning_mode=planning_mode,
            grounding_confidence_threshold=config.grounding.confidence_threshold,
            enable_memory=config.memory.enabled,
            enable_task_planning=config.task_planning.enabled,
            enable_error_recovery=config.error_recovery.enabled,
            memory_storage_path=config.memory.long_term_storage,
            max_recovery_attempts=config.error_recovery.max_recovery_attempts
        )

        # Set callback for step updates
        self.agent.on_step_callback = self._on_agent_step

        # Minimize main window to prevent agent from clicking on it
        self.showMinimized()

        # Show overlay
        self.overlay.set_waiting()
        self.overlay.show()

        # Start agent thread
        self.agent_thread = AgentThread(self.agent, task)
        self.agent_thread.finished.connect(self._on_task_finished)
        self.agent_thread.error_occurred.connect(self._on_error)
        self.agent_thread.start()

        # Update UI state
        self.status_label.setText("Status: Running (VLM-Driven)")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.task_input.setEnabled(False)
        self.mode_combo.setEnabled(False)

    def _on_llm_step(self, step_result: StepResult):
        """Callback from LLM controller when a tool is executed."""
        print(f"[LLM Callback] Tool: {step_result.tool_name}")
        print(f"[LLM Callback] Result: {step_result.tool_result[:100] if step_result.tool_result else 'None'}...")
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
        self.mode_combo.setEnabled(True)

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
        self.showNormal()  # Restore main window

        if success:
            self.status_label.setText("Status: Completed")
        else:
            self.status_label.setText("Status: Failed")

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.task_input.setEnabled(True)
        self.mode_combo.setEnabled(True)
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
        self.mode_combo.setEnabled(True)
        QMessageBox.critical(self, "Agent Error", f"Error during execution:\n\n{error_msg}")

    def closeEvent(self, event):
        """Handle window close."""
        if self.agent_thread and self.agent_thread.isRunning():
            self.agent_thread.stop()
            self.agent_thread.wait(2000)

        self.overlay.close()
        event.accept()
