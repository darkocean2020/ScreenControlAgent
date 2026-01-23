"""Task planning models for multi-step task execution."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class SubtaskStatus(Enum):
    """Status of a subtask."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Subtask:
    """Represents a single subtask in a task plan."""
    id: str
    description: str
    success_criteria: str
    estimated_steps: int = 3
    status: SubtaskStatus = SubtaskStatus.PENDING
    actual_steps: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def start(self) -> None:
        """Mark subtask as in progress."""
        self.status = SubtaskStatus.IN_PROGRESS
        self.started_at = datetime.now()

    def complete(self) -> None:
        """Mark subtask as completed."""
        self.status = SubtaskStatus.COMPLETED
        self.completed_at = datetime.now()

    def fail(self, error: str) -> None:
        """Mark subtask as failed."""
        self.status = SubtaskStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "success_criteria": self.success_criteria,
            "status": self.status.value,
            "actual_steps": self.actual_steps
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Subtask":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            success_criteria=data.get("success_criteria", ""),
            estimated_steps=data.get("estimated_steps", 3),
            status=SubtaskStatus(data.get("status", "pending"))
        )


@dataclass
class TaskPlan:
    """Represents a complete task execution plan."""
    original_task: str
    subtasks: List[Subtask] = field(default_factory=list)
    current_index: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def current_subtask(self) -> Optional[Subtask]:
        """Get the current subtask."""
        if 0 <= self.current_index < len(self.subtasks):
            return self.subtasks[self.current_index]
        return None

    @property
    def progress(self) -> str:
        """Get progress string."""
        completed = sum(1 for s in self.subtasks if s.status == SubtaskStatus.COMPLETED)
        return f"{completed}/{len(self.subtasks)}"

    def advance(self) -> bool:
        """
        Move to the next subtask.

        Returns:
            True if advanced successfully, False if no more subtasks
        """
        if self.current_subtask:
            if self.current_subtask.status == SubtaskStatus.IN_PROGRESS:
                self.current_subtask.complete()

        self.current_index += 1
        if self.current_index < len(self.subtasks):
            self.subtasks[self.current_index].start()
            return True
        return False

    def is_complete(self) -> bool:
        """Check if all subtasks are completed."""
        return all(
            s.status in (SubtaskStatus.COMPLETED, SubtaskStatus.SKIPPED)
            for s in self.subtasks
        )

    def has_failures(self) -> bool:
        """Check if any subtask failed."""
        return any(s.status == SubtaskStatus.FAILED for s in self.subtasks)

    def start(self) -> None:
        """Start executing the plan."""
        if self.subtasks:
            self.subtasks[0].start()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "original_task": self.original_task,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "current_index": self.current_index,
            "progress": self.progress
        }


class ErrorType(Enum):
    """Classification of errors during execution."""
    CLICK_MISSED = "click_missed"
    ELEMENT_NOT_FOUND = "element_not_found"
    ELEMENT_MOVED = "element_moved"
    POPUP_BLOCKED = "popup_blocked"
    TYPING_FAILED = "typing_failed"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    UNEXPECTED_STATE = "unexpected_state"
    UNKNOWN = "unknown"


@dataclass
class ErrorEvent:
    """Records an error that occurred during execution."""
    error_type: ErrorType
    action_description: str
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    recovery_attempted: bool = False
    recovery_successful: bool = False
    recovery_strategy: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "error_type": self.error_type.value,
            "action": self.action_description,
            "timestamp": self.timestamp.isoformat(),
            "recovery_attempted": self.recovery_attempted,
            "recovery_successful": self.recovery_successful,
            "recovery_strategy": self.recovery_strategy
        }
