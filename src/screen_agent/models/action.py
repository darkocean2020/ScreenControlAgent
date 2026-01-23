"""Data models for actions and agent state."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple, List
from PIL import Image


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
    current_task: str
    step_count: int = 0
    max_steps: int = 20
    screenshot: Optional[Image.Image] = None
    last_action: Optional[Action] = None
    action_history: List[Action] = field(default_factory=list)
    is_completed: bool = False
    error_message: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)

    def add_action(self, action: Action) -> None:
        """Add an action to history."""
        self.action_history.append(action)
        self.last_action = action

    def get_recent_history(self, n: int = 5) -> List[Action]:
        """Get the n most recent actions."""
        return self.action_history[-n:] if self.action_history else []
