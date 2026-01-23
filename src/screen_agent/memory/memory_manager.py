"""Unified memory manager combining short-term and long-term memory."""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from .short_term import ShortTermMemory
from .long_term import LongTermMemory, TaskRecord
from ..models.action import Action
from ..utils.logger import get_logger

logger = get_logger(__name__)


class MemoryManager:
    """
    Unified interface for memory operations.

    Combines short-term (session) and long-term (persistent) memory
    to provide context for planning and learning from experience.
    """

    def __init__(
        self,
        storage_path: str = "data/memory.json",
        short_term_context_size: int = 10,
        element_cache_ttl: float = 300
    ):
        """
        Initialize memory manager.

        Args:
            storage_path: Path for long-term memory storage
            short_term_context_size: Max context entries in short-term
            element_cache_ttl: Element cache TTL in seconds
        """
        self.short_term = ShortTermMemory(
            context_size=short_term_context_size,
            element_cache_ttl=element_cache_ttl
        )
        self.long_term = LongTermMemory(storage_path=storage_path)

        self._session_task: Optional[str] = None
        self._session_start: Optional[datetime] = None
        self._session_actions: List[str] = []
        self._session_errors: List[str] = []

        logger.info("MemoryManager initialized")

    def start_session(self, task: str) -> None:
        """
        Start a new task session.

        Args:
            task: The task being executed
        """
        self._session_task = task
        self._session_start = datetime.now()
        self._session_actions.clear()
        self._session_errors.clear()
        self.short_term.clear()

        logger.debug(f"Started memory session for task: {task[:50]}...")

    def get_context_for_planning(self, task: str) -> Dict[str, Any]:
        """
        Get memory context to enhance planning.

        Args:
            task: Current task description

        Returns:
            Dictionary with memory context for prompts
        """
        # Find similar past tasks
        similar_tasks = self.long_term.find_similar_tasks(task)
        similar_summary = []
        for record in similar_tasks[:2]:
            summary = {
                "task": record.task,
                "success": record.success,
                "steps": record.steps,
                "key_actions": record.actions[:5] if record.actions else []
            }
            similar_summary.append(summary)

        # Get success patterns
        patterns = self.long_term.get_success_patterns(task)

        # Get recent context
        recent_context = self.short_term.get_recent_context()

        # Get element cache
        element_cache = self.short_term.element_cache.get_all()

        # Get failed actions to avoid
        failed_actions = self.short_term.get_failed_actions()

        return {
            "similar_tasks": similar_summary,
            "success_patterns": patterns,
            "recent_context": recent_context,
            "element_cache": element_cache,
            "failed_actions": failed_actions
        }

    def update_after_action(
        self,
        action: Action,
        success: bool,
        observation: str,
        element_name: Optional[str] = None,
        coordinates: Optional[Tuple[int, int]] = None
    ) -> None:
        """
        Update memory after an action is executed.

        Args:
            action: The action that was executed
            success: Whether it succeeded
            observation: What was observed after
            element_name: Target element name (if any)
            coordinates: Coordinates used (if any)
        """
        # Update short-term memory
        self.short_term.add_context(
            observation=observation,
            action=action,
            success=success,
            element_name=element_name,
            coordinates=coordinates
        )

        # Track for session
        self._session_actions.append(str(action))

        # Track failures
        if not success:
            self.short_term.mark_action_failed(action, observation)

        logger.debug(f"Memory updated: action={action}, success={success}")

    def record_error(self, error_type: str) -> None:
        """Record an error that occurred."""
        self._session_errors.append(error_type)

    def cache_element(self, name: str, coords: Tuple[int, int]) -> None:
        """Cache an element's location."""
        self.short_term.cache_element(name, coords)

    def get_cached_element(self, name: str) -> Optional[Tuple[int, int]]:
        """Get cached element location if available."""
        return self.short_term.get_cached_element(name)

    def save_session(self, success: bool, learned_patterns: List[str] = None) -> None:
        """
        Save the current session to long-term memory.

        Args:
            success: Whether the task completed successfully
            learned_patterns: Patterns learned during execution
        """
        if not self._session_task or not self._session_start:
            logger.warning("No active session to save")
            return

        duration = (datetime.now() - self._session_start).total_seconds()

        record = TaskRecord(
            task=self._session_task,
            success=success,
            steps=len(self._session_actions),
            actions=self._session_actions.copy(),
            duration_seconds=duration,
            learned_patterns=learned_patterns or [],
            error_types=list(set(self._session_errors))
        )

        self.long_term.save_task_record(record)

        logger.info(
            f"Session saved: task='{self._session_task[:30]}...', "
            f"success={success}, steps={record.steps}"
        )

        # Clear session state
        self._session_task = None
        self._session_start = None
        self._session_actions.clear()
        self._session_errors.clear()

    def get_element_from_cache_or_history(
        self,
        element_name: str
    ) -> Optional[Tuple[int, int]]:
        """
        Try to find element coordinates from cache or similar past tasks.

        Args:
            element_name: Name of the element

        Returns:
            Coordinates if found, None otherwise
        """
        # First check short-term cache
        coords = self.short_term.get_cached_element(element_name)
        if coords:
            logger.debug(f"Element '{element_name}' found in cache: {coords}")
            return coords

        # Could extend to search long-term memory in the future
        return None

    def should_use_cached_element(self, element_name: str) -> bool:
        """Check if we should use a cached element location."""
        coords = self.short_term.get_cached_element(element_name)
        return coords is not None

    def format_context_for_prompt(self, context: Dict[str, Any]) -> str:
        """
        Format memory context as a string for inclusion in prompts.

        Args:
            context: Context dictionary from get_context_for_planning

        Returns:
            Formatted string for prompt
        """
        lines = []

        # Similar tasks
        if context.get("similar_tasks"):
            lines.append("SIMILAR PAST TASKS:")
            for st in context["similar_tasks"]:
                status = "SUCCESS" if st["success"] else "FAILED"
                lines.append(f"  - [{status}] {st['task']} ({st['steps']} steps)")

        # Success patterns
        if context.get("success_patterns"):
            lines.append("\nSUCCESS PATTERNS:")
            for pattern in context["success_patterns"]:
                lines.append(f"  - {pattern}")

        # Failed actions to avoid
        if context.get("failed_actions"):
            lines.append("\nACTIONS TO AVOID (previously failed):")
            for fa in context["failed_actions"]:
                lines.append(f"  - {fa['action']}: {fa['reason']}")

        # Element cache
        if context.get("element_cache"):
            lines.append("\nKNOWN ELEMENT LOCATIONS:")
            for name, coords in list(context["element_cache"].items())[:10]:
                lines.append(f"  - {name}: {coords}")

        return "\n".join(lines) if lines else "No memory context available."

    def get_statistics(self) -> Dict[str, Any]:
        """Get combined memory statistics."""
        short_stats = self.short_term.get_summary()
        long_stats = self.long_term.get_statistics()

        return {
            "short_term": short_stats,
            "long_term": long_stats
        }

    def clear_all(self) -> None:
        """Clear both short-term and long-term memory."""
        self.short_term.clear()
        self.long_term.clear()
        self._session_task = None
        self._session_start = None
        self._session_actions.clear()
        self._session_errors.clear()
        logger.info("All memory cleared")
