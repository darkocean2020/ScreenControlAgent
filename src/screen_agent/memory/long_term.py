"""Long-term memory for persistent task history and learned patterns."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TaskRecord:
    """Record of a completed task execution."""
    task: str
    success: bool
    steps: int
    actions: List[str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_seconds: float = 0.0
    learned_patterns: List[str] = field(default_factory=list)
    error_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        """Create from dictionary."""
        return cls(
            task=data.get("task", ""),
            success=data.get("success", False),
            steps=data.get("steps", 0),
            actions=data.get("actions", []),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            duration_seconds=data.get("duration_seconds", 0.0),
            learned_patterns=data.get("learned_patterns", []),
            error_types=data.get("error_types", [])
        )


class LongTermMemory:
    """
    Long-term memory with persistent storage.

    Stores:
    - Task execution history
    - Learned patterns for common tasks
    - Common failure modes
    """

    def __init__(self, storage_path: str = "data/memory.json", max_records: int = 500):
        """
        Initialize long-term memory.

        Args:
            storage_path: Path to JSON storage file
            max_records: Maximum number of records to keep
        """
        self.storage_path = Path(storage_path)
        self.max_records = max_records
        self._records: List[TaskRecord] = []
        self._patterns: Dict[str, List[str]] = {}  # task_type -> patterns
        self._failures: Dict[str, List[str]] = {}  # action_type -> failures

        self._load()

    def _load(self) -> None:
        """Load memory from storage."""
        if not self.storage_path.exists():
            logger.debug(f"No existing memory file at {self.storage_path}")
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._records = [
                TaskRecord.from_dict(r) for r in data.get("records", [])
            ]
            self._patterns = data.get("patterns", {})
            self._failures = data.get("failures", {})

            logger.info(f"Loaded {len(self._records)} task records from memory")

        except Exception as e:
            logger.error(f"Failed to load memory: {e}")

    def _save(self) -> None:
        """Save memory to storage."""
        try:
            # Ensure directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "records": [r.to_dict() for r in self._records],
                "patterns": self._patterns,
                "failures": self._failures,
                "last_updated": datetime.now().isoformat()
            }

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Saved {len(self._records)} records to memory")

        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def save_task_record(self, record: TaskRecord) -> None:
        """
        Save a task execution record.

        Args:
            record: The task record to save
        """
        self._records.append(record)

        # Extract and store patterns from successful tasks
        if record.success and record.learned_patterns:
            task_type = self._classify_task(record.task)
            if task_type not in self._patterns:
                self._patterns[task_type] = []
            for pattern in record.learned_patterns:
                if pattern not in self._patterns[task_type]:
                    self._patterns[task_type].append(pattern)

        # Store failure information
        if not record.success and record.error_types:
            for action in record.actions:
                action_type = action.split()[0] if action else "unknown"
                if action_type not in self._failures:
                    self._failures[action_type] = []
                for error in record.error_types:
                    if error not in self._failures[action_type]:
                        self._failures[action_type].append(error)

        # Trim old records
        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records:]

        self._save()

    def find_similar_tasks(self, task: str, limit: int = 3) -> List[TaskRecord]:
        """
        Find similar past tasks.

        Args:
            task: Current task description
            limit: Maximum number of results

        Returns:
            List of similar task records, most similar first
        """
        if not self._records:
            return []

        # Calculate similarity scores
        scored = []
        task_lower = task.lower()

        for record in self._records:
            # Use sequence matcher for similarity
            similarity = SequenceMatcher(
                None, task_lower, record.task.lower()
            ).ratio()

            # Boost successful tasks
            if record.success:
                similarity *= 1.2

            scored.append((record, similarity))

        # Sort by similarity and return top matches
        scored.sort(key=lambda x: x[1], reverse=True)

        # Only return if similarity is above threshold
        return [
            record for record, score in scored[:limit]
            if score > 0.3
        ]

    def get_success_patterns(self, task: str) -> List[str]:
        """
        Get learned success patterns for a task type.

        Args:
            task: Task description

        Returns:
            List of patterns that worked for similar tasks
        """
        task_type = self._classify_task(task)
        patterns = self._patterns.get(task_type, [])

        # Also check similar task types
        for t_type, t_patterns in self._patterns.items():
            if t_type != task_type and self._task_types_similar(task_type, t_type):
                patterns.extend(t_patterns)

        return list(set(patterns))[:5]  # Dedupe and limit

    def get_common_failures(self, action_type: str) -> List[str]:
        """
        Get common failure modes for an action type.

        Args:
            action_type: Type of action (click, type, etc.)

        Returns:
            List of common failure descriptions
        """
        return self._failures.get(action_type.lower(), [])[:5]

    def _classify_task(self, task: str) -> str:
        """Classify a task into a category."""
        task_lower = task.lower()

        # Simple keyword-based classification
        if any(kw in task_lower for kw in ["打开", "open", "launch", "启动"]):
            return "open_app"
        elif any(kw in task_lower for kw in ["输入", "type", "write", "填写"]):
            return "text_input"
        elif any(kw in task_lower for kw in ["点击", "click", "按"]):
            return "click_action"
        elif any(kw in task_lower for kw in ["搜索", "search", "find", "查找"]):
            return "search"
        elif any(kw in task_lower for kw in ["关闭", "close", "退出"]):
            return "close_app"
        elif any(kw in task_lower for kw in ["保存", "save"]):
            return "save"
        else:
            return "general"

    def _task_types_similar(self, type1: str, type2: str) -> bool:
        """Check if two task types are similar."""
        related = {
            ("open_app", "search"),
            ("text_input", "search"),
            ("click_action", "close_app"),
        }
        return (type1, type2) in related or (type2, type1) in related

    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics."""
        if not self._records:
            return {
                "total_tasks": 0,
                "success_rate": 0.0,
                "avg_steps": 0.0
            }

        successes = sum(1 for r in self._records if r.success)
        total_steps = sum(r.steps for r in self._records)

        return {
            "total_tasks": len(self._records),
            "success_rate": successes / len(self._records),
            "avg_steps": total_steps / len(self._records),
            "pattern_count": sum(len(p) for p in self._patterns.values()),
            "failure_types": sum(len(f) for f in self._failures.values())
        }

    def clear(self) -> None:
        """Clear all long-term memory."""
        self._records.clear()
        self._patterns.clear()
        self._failures.clear()
        self._save()
