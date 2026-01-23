"""Data models for actions and agent state."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any, TYPE_CHECKING, Callable
from PIL import Image

if TYPE_CHECKING:
    from .task import TaskPlan, Subtask, ErrorEvent


@dataclass
class StepInfo:
    """每一步的详细信息，用于 UI 显示"""
    step_number: int
    action: 'Action'
    reasoning: str = ""           # VLM 的推理过程
    observation: str = ""         # VLM 的观察结果
    verification: Optional[Dict[str, Any]] = None  # 验证结果
    mouse_position: Tuple[int, int] = (0, 0)  # 当前鼠标位置


class ActionType(Enum):
    """Action type enumeration."""
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    MOVE = "move"
    WAIT = "wait"
    DONE = "done"


@dataclass
class Action:
    """Represents a single action to be executed."""
    action_type: ActionType
    coordinates: Optional[Tuple[int, int]] = None
    text: Optional[str] = None
    keys: Optional[List[str]] = None
    scroll_amount: Optional[int] = None
    duration: Optional[float] = None
    description: Optional[str] = None
    # Grounding information (Phase 2)
    target_element_name: Optional[str] = None
    grounding_confidence: Optional[float] = None

    def __str__(self) -> str:
        if self.action_type == ActionType.CLICK:
            return f"Click at {self.coordinates}"
        elif self.action_type == ActionType.DOUBLE_CLICK:
            return f"Double-click at {self.coordinates}"
        elif self.action_type == ActionType.RIGHT_CLICK:
            return f"Right-click at {self.coordinates}"
        elif self.action_type == ActionType.TYPE:
            text_preview = self.text[:20] + "..." if self.text and len(self.text) > 20 else self.text
            return f"Type: '{text_preview}'"
        elif self.action_type == ActionType.HOTKEY:
            return f"Hotkey: {'+'.join(self.keys or [])}"
        elif self.action_type == ActionType.SCROLL:
            direction = "up" if (self.scroll_amount or 0) > 0 else "down"
            return f"Scroll {direction} ({abs(self.scroll_amount or 0)})"
        elif self.action_type == ActionType.WAIT:
            return f"Wait {self.duration}s"
        elif self.action_type == ActionType.DONE:
            return "Task completed"
        return f"{self.action_type.value}: {self.description or ''}"


@dataclass
class AgentState:
    """Represents the current state of the agent."""
    # Core state (Phase 1)
    current_task: str
    step_count: int = 0
    max_steps: int = 20
    screenshot: Optional[Image.Image] = None
    last_action: Optional[Action] = None
    action_history: List[Action] = field(default_factory=list)
    is_completed: bool = False
    error_message: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)

    # Phase 3: Task planning
    task_plan: Optional[Any] = None  # TaskPlan
    current_subtask: Optional[Any] = None  # Subtask
    subtask_step_count: int = 0  # Steps in current subtask

    # Phase 3: Error tracking
    error_history: List[Any] = field(default_factory=list)  # List[ErrorEvent]
    recovery_attempts: int = 0
    last_error_type: Optional[str] = None

    # Phase 3: Memory context
    memory_context: Dict[str, Any] = field(default_factory=dict)

    # Phase 3: Verification tracking
    last_verification: Optional[Dict[str, Any]] = None

    def add_action(self, action: Action) -> None:
        """Add an action to history."""
        self.action_history.append(action)
        self.last_action = action
        self.subtask_step_count += 1

    def get_recent_history(self, n: int = 5) -> List[Action]:
        """Get the n most recent actions."""
        return self.action_history[-n:] if self.action_history else []

    def record_error(self, error_event: Any) -> None:
        """Record an error event."""
        self.error_history.append(error_event)
        self.last_error_type = error_event.error_type.value if hasattr(error_event, 'error_type') else str(error_event)

    def reset_recovery_state(self) -> None:
        """Reset recovery-related state for a new action."""
        self.recovery_attempts = 0
        self.last_error_type = None

    def advance_subtask(self) -> bool:
        """
        Advance to the next subtask.

        Returns:
            True if advanced, False if no more subtasks
        """
        if self.task_plan and hasattr(self.task_plan, 'advance'):
            self.subtask_step_count = 0
            result = self.task_plan.advance()
            if result and hasattr(self.task_plan, 'current_subtask'):
                self.current_subtask = self.task_plan.current_subtask
            return result
        return False

    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a summary of current progress."""
        summary = {
            "task": self.current_task,
            "step": self.step_count,
            "max_steps": self.max_steps,
            "completed": self.is_completed,
            "errors": len(self.error_history),
            "recovery_attempts": self.recovery_attempts
        }

        if self.task_plan and hasattr(self.task_plan, 'progress'):
            summary["subtask_progress"] = self.task_plan.progress

        return summary
