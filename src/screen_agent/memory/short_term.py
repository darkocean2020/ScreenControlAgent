"""Short-term memory for session context and element caching."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from collections import OrderedDict

from ..models.action import Action


@dataclass
class ContextEntry:
    """A single entry in the context window."""
    observation: str
    action_description: str
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)
    element_name: Optional[str] = None
    coordinates: Optional[Tuple[int, int]] = None


@dataclass
class FailedAction:
    """Record of a failed action."""
    action: Action
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0


class ElementCache:
    """LRU cache for element locations."""

    def __init__(self, max_size: int = 100, ttl_seconds: float = 300):
        """
        Initialize element cache.

        Args:
            max_size: Maximum number of cached elements
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self._cache: OrderedDict[str, Tuple[Tuple[int, int], datetime]] = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

    def get(self, name: str) -> Optional[Tuple[int, int]]:
        """
        Get cached coordinates for an element.

        Args:
            name: Element name (case-insensitive)

        Returns:
            Cached coordinates or None if not found/expired
        """
        key = name.lower().strip()
        if key not in self._cache:
            return None

        coords, timestamp = self._cache[key]

        # Check TTL
        age = (datetime.now() - timestamp).total_seconds()
        if age > self.ttl_seconds:
            del self._cache[key]
            return None

        # Move to end (LRU update)
        self._cache.move_to_end(key)
        return coords

    def set(self, name: str, coords: Tuple[int, int]) -> None:
        """
        Cache element coordinates.

        Args:
            name: Element name
            coords: (x, y) coordinates
        """
        key = name.lower().strip()

        # Remove if exists (will be re-added at end)
        if key in self._cache:
            del self._cache[key]

        # Evict oldest if at capacity
        while len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)

        self._cache[key] = (coords, datetime.now())

    def invalidate(self, name: str) -> None:
        """Remove an element from cache."""
        key = name.lower().strip()
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all cached elements."""
        self._cache.clear()

    def get_all(self) -> Dict[str, Tuple[int, int]]:
        """Get all cached elements (for context)."""
        now = datetime.now()
        valid = {}
        for name, (coords, timestamp) in self._cache.items():
            if (now - timestamp).total_seconds() <= self.ttl_seconds:
                valid[name] = coords
        return valid

    def __len__(self) -> int:
        return len(self._cache)


class ShortTermMemory:
    """
    Short-term memory for the current session.

    Stores:
    - Element location cache (avoids repeated grounding)
    - Recent context window (observations and actions)
    - Failed actions (to avoid repeating mistakes)
    """

    def __init__(
        self,
        context_size: int = 10,
        element_cache_size: int = 100,
        element_cache_ttl: float = 300
    ):
        """
        Initialize short-term memory.

        Args:
            context_size: Number of recent contexts to keep
            element_cache_size: Max elements in location cache
            element_cache_ttl: Cache TTL in seconds
        """
        self.context_size = context_size
        self.context_window: List[ContextEntry] = []
        self.element_cache = ElementCache(element_cache_size, element_cache_ttl)
        self.failed_actions: List[FailedAction] = []
        self.session_start = datetime.now()

    def add_context(
        self,
        observation: str,
        action: Action,
        success: bool,
        element_name: Optional[str] = None,
        coordinates: Optional[Tuple[int, int]] = None
    ) -> None:
        """
        Add a context entry from an action execution.

        Args:
            observation: What was observed on screen
            action: The action that was taken
            success: Whether the action succeeded
            element_name: Name of target element (if any)
            coordinates: Coordinates used (if any)
        """
        entry = ContextEntry(
            observation=observation,
            action_description=str(action),
            success=success,
            element_name=element_name,
            coordinates=coordinates
        )

        self.context_window.append(entry)

        # Trim to max size
        if len(self.context_window) > self.context_size:
            self.context_window = self.context_window[-self.context_size:]

        # Cache successful element locations
        if success and element_name and coordinates:
            self.element_cache.set(element_name, coordinates)

    def get_recent_context(self, n: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent context entries.

        Args:
            n: Number of entries to return

        Returns:
            List of context dictionaries
        """
        entries = self.context_window[-n:] if self.context_window else []
        return [
            {
                "observation": e.observation,
                "action": e.action_description,
                "success": e.success,
                "element": e.element_name
            }
            for e in entries
        ]

    def cache_element(self, name: str, coords: Tuple[int, int]) -> None:
        """Cache an element's location."""
        self.element_cache.set(name, coords)

    def get_cached_element(self, name: str) -> Optional[Tuple[int, int]]:
        """Get cached element location."""
        return self.element_cache.get(name)

    def mark_action_failed(self, action: Action, reason: str) -> None:
        """
        Record a failed action.

        Args:
            action: The action that failed
            reason: Why it failed
        """
        # Check if this action already failed recently
        for fa in self.failed_actions:
            if str(fa.action) == str(action):
                fa.retry_count += 1
                fa.reason = reason
                fa.timestamp = datetime.now()
                return

        self.failed_actions.append(FailedAction(
            action=action,
            reason=reason
        ))

        # Keep only recent failures
        if len(self.failed_actions) > 20:
            self.failed_actions = self.failed_actions[-20:]

    def get_failed_actions(self) -> List[Dict[str, Any]]:
        """Get list of failed actions to avoid."""
        return [
            {
                "action": str(fa.action),
                "reason": fa.reason,
                "retry_count": fa.retry_count
            }
            for fa in self.failed_actions
            if fa.retry_count < 3  # Only include if not retried too many times
        ]

    def should_avoid_action(self, action: Action) -> bool:
        """Check if an action should be avoided due to previous failures."""
        action_str = str(action)
        for fa in self.failed_actions:
            if str(fa.action) == action_str and fa.retry_count >= 2:
                return True
        return False

    def clear(self) -> None:
        """Clear all short-term memory."""
        self.context_window.clear()
        self.element_cache.clear()
        self.failed_actions.clear()
        self.session_start = datetime.now()

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of current memory state."""
        return {
            "session_duration": (datetime.now() - self.session_start).total_seconds(),
            "context_entries": len(self.context_window),
            "cached_elements": len(self.element_cache),
            "failed_actions": len(self.failed_actions),
            "recent_success_rate": self._calculate_success_rate()
        }

    def _calculate_success_rate(self) -> float:
        """Calculate recent action success rate."""
        if not self.context_window:
            return 1.0
        successes = sum(1 for e in self.context_window if e.success)
        return successes / len(self.context_window)
