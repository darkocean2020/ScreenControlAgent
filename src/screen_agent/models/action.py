"""Data models for actions."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any


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
