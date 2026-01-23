"""Error analysis and recovery strategies."""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any

from ..models.action import Action, ActionType
from ..models.task import ErrorType, ErrorEvent
from ..perception.vlm_client import VLMClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RecoveryStrategy:
    """A strategy for recovering from an error."""
    name: str
    description: str
    pre_actions: List[Action] = field(default_factory=list)
    retry_original: bool = True
    max_retries: int = 2

    def __str__(self) -> str:
        return f"RecoveryStrategy({self.name})"


class ErrorRecovery:
    """
    Error analysis and recovery system.

    Analyzes failures, classifies error types, and provides
    recovery strategies to handle common error scenarios.
    """

    # Built-in recovery strategies
    STRATEGIES: Dict[ErrorType, List[RecoveryStrategy]] = {
        ErrorType.CLICK_MISSED: [
            RecoveryStrategy(
                name="retry_click",
                description="Simply retry the click action",
                pre_actions=[
                    Action(ActionType.WAIT, duration=0.5)
                ],
                retry_original=True,
                max_retries=2
            ),
            RecoveryStrategy(
                name="click_nearby",
                description="Click slightly different position",
                pre_actions=[],
                retry_original=True,
                max_retries=1
            ),
        ],
        ErrorType.ELEMENT_NOT_FOUND: [
            RecoveryStrategy(
                name="wait_and_retry",
                description="Wait for element to appear",
                pre_actions=[
                    Action(ActionType.WAIT, duration=1.5)
                ],
                retry_original=True,
                max_retries=3
            ),
            RecoveryStrategy(
                name="scroll_down",
                description="Scroll down to find element",
                pre_actions=[
                    Action(ActionType.SCROLL, scroll_amount=-3)
                ],
                retry_original=True,
                max_retries=2
            ),
            RecoveryStrategy(
                name="scroll_up",
                description="Scroll up to find element",
                pre_actions=[
                    Action(ActionType.SCROLL, scroll_amount=3)
                ],
                retry_original=True,
                max_retries=2
            ),
        ],
        ErrorType.POPUP_BLOCKED: [
            RecoveryStrategy(
                name="dismiss_with_escape",
                description="Press Escape to dismiss popup",
                pre_actions=[
                    Action(ActionType.HOTKEY, keys=["escape"])
                ],
                retry_original=True,
                max_retries=2
            ),
            RecoveryStrategy(
                name="click_outside",
                description="Click outside popup to dismiss",
                pre_actions=[
                    Action(ActionType.CLICK, coordinates=(10, 10))
                ],
                retry_original=True,
                max_retries=1
            ),
        ],
        ErrorType.TYPING_FAILED: [
            RecoveryStrategy(
                name="click_and_retype",
                description="Click target field and retype",
                pre_actions=[],  # Will use original click coordinates
                retry_original=True,
                max_retries=2
            ),
            RecoveryStrategy(
                name="clear_and_retype",
                description="Clear field with Ctrl+A and retype",
                pre_actions=[
                    Action(ActionType.HOTKEY, keys=["ctrl", "a"])
                ],
                retry_original=True,
                max_retries=1
            ),
        ],
        ErrorType.TIMEOUT: [
            RecoveryStrategy(
                name="wait_longer",
                description="Wait longer for operation to complete",
                pre_actions=[
                    Action(ActionType.WAIT, duration=3.0)
                ],
                retry_original=True,
                max_retries=2
            ),
        ],
        ErrorType.ELEMENT_MOVED: [
            RecoveryStrategy(
                name="refresh_and_retry",
                description="Refresh element location and retry",
                pre_actions=[
                    Action(ActionType.WAIT, duration=0.5)
                ],
                retry_original=True,
                max_retries=2
            ),
        ],
        ErrorType.UNEXPECTED_STATE: [
            RecoveryStrategy(
                name="escape_and_retry",
                description="Press Escape and retry",
                pre_actions=[
                    Action(ActionType.HOTKEY, keys=["escape"]),
                    Action(ActionType.WAIT, duration=0.5)
                ],
                retry_original=True,
                max_retries=1
            ),
        ],
    }

    # Keywords for error classification
    ERROR_KEYWORDS = {
        ErrorType.CLICK_MISSED: [
            "didn't click", "missed", "wrong position", "not clicked",
            "click failed", "未点击", "点击失败"
        ],
        ErrorType.ELEMENT_NOT_FOUND: [
            "not found", "doesn't exist", "cannot find", "no element",
            "not visible", "找不到", "不存在", "未找到"
        ],
        ErrorType.POPUP_BLOCKED: [
            "popup", "dialog", "modal", "blocked", "overlay",
            "弹窗", "对话框", "遮挡"
        ],
        ErrorType.TYPING_FAILED: [
            "typing failed", "text not entered", "input failed",
            "输入失败", "未输入"
        ],
        ErrorType.TIMEOUT: [
            "timeout", "too slow", "not responding", "超时", "无响应"
        ],
        ErrorType.ELEMENT_MOVED: [
            "moved", "position changed", "relocated", "位置变化", "移动"
        ],
    }

    def __init__(
        self,
        vlm_client: Optional[VLMClient] = None,
        max_recovery_attempts: int = 3,
        enabled_strategies: Optional[List[str]] = None
    ):
        """
        Initialize error recovery system.

        Args:
            vlm_client: Optional VLM for advanced error analysis
            max_recovery_attempts: Max total recovery attempts per action
            enabled_strategies: List of enabled strategy names (None = all)
        """
        self.vlm_client = vlm_client
        self.max_recovery_attempts = max_recovery_attempts
        self.enabled_strategies = enabled_strategies
        self._attempt_counts: Dict[str, int] = {}

    def analyze_error(
        self,
        action: Action,
        verification_result: Dict[str, Any],
        screenshot=None
    ) -> ErrorType:
        """
        Analyze an error and classify its type.

        Args:
            action: The action that failed
            verification_result: Result from verifier
            screenshot: Current screenshot (optional, for VLM analysis)

        Returns:
            Classified error type
        """
        # Get the issues/observation from verification
        issues = verification_result.get("issues", "") or ""
        observation = verification_result.get("observation", "") or ""
        combined_text = f"{issues} {observation}".lower()

        # Keyword-based classification
        for error_type, keywords in self.ERROR_KEYWORDS.items():
            if any(kw.lower() in combined_text for kw in keywords):
                logger.debug(f"Error classified as {error_type.value} via keywords")
                return error_type

        # Action-type based heuristics
        if action.action_type in (ActionType.CLICK, ActionType.DOUBLE_CLICK, ActionType.RIGHT_CLICK):
            if "not" in combined_text and ("click" in combined_text or "open" in combined_text):
                return ErrorType.CLICK_MISSED

        if action.action_type == ActionType.TYPE:
            if "not" in combined_text and ("type" in combined_text or "enter" in combined_text or "input" in combined_text):
                return ErrorType.TYPING_FAILED

        # Default to unknown
        logger.debug(f"Error classified as UNKNOWN: {combined_text[:100]}")
        return ErrorType.UNKNOWN

    def get_recovery_strategy(
        self,
        error_type: ErrorType,
        action: Action,
        attempt: int = 0
    ) -> Optional[RecoveryStrategy]:
        """
        Get a recovery strategy for an error.

        Args:
            error_type: Type of error
            action: The failed action
            attempt: Current attempt number (0-indexed)

        Returns:
            RecoveryStrategy or None if no more strategies
        """
        strategies = self.STRATEGIES.get(error_type, [])

        if not strategies:
            # Try generic strategies for unknown errors
            strategies = [
                RecoveryStrategy(
                    name="wait_and_retry",
                    description="Wait and retry the action",
                    pre_actions=[Action(ActionType.WAIT, duration=1.0)],
                    retry_original=True,
                    max_retries=2
                )
            ]

        # Filter by enabled strategies
        if self.enabled_strategies:
            strategies = [
                s for s in strategies
                if s.name in self.enabled_strategies
            ]

        # Get strategy for this attempt
        if attempt >= len(strategies):
            # Cycle through strategies
            strategy_idx = attempt % len(strategies)
        else:
            strategy_idx = attempt

        strategy = strategies[strategy_idx]

        # Check if strategy has exceeded its max retries
        strategy_key = f"{error_type.value}:{strategy.name}"
        current_count = self._attempt_counts.get(strategy_key, 0)

        if current_count >= strategy.max_retries:
            # Try next strategy
            if strategy_idx + 1 < len(strategies):
                return strategies[strategy_idx + 1]
            return None

        # Increment attempt count
        self._attempt_counts[strategy_key] = current_count + 1

        logger.info(f"Selected recovery strategy: {strategy.name} for {error_type.value}")
        return strategy

    def can_recover(self, error_type: ErrorType, total_attempts: int) -> bool:
        """
        Check if recovery should be attempted.

        Args:
            error_type: Type of error
            total_attempts: Total recovery attempts so far

        Returns:
            True if recovery should be attempted
        """
        if total_attempts >= self.max_recovery_attempts:
            logger.warning(f"Max recovery attempts ({self.max_recovery_attempts}) reached")
            return False

        # Some error types are not recoverable
        non_recoverable = {ErrorType.PERMISSION_DENIED}
        if error_type in non_recoverable:
            return False

        return True

    def execute_recovery(
        self,
        strategy: RecoveryStrategy,
        executor,  # ActionExecutor
        original_action: Optional[Action] = None
    ) -> bool:
        """
        Execute a recovery strategy.

        Args:
            strategy: The recovery strategy to execute
            executor: ActionExecutor instance
            original_action: The original failed action (for retry)

        Returns:
            True if recovery actions succeeded
        """
        logger.info(f"Executing recovery strategy: {strategy.name}")

        # Execute pre-actions
        for pre_action in strategy.pre_actions:
            logger.debug(f"Recovery pre-action: {pre_action}")
            success = executor.execute(pre_action)
            if not success:
                logger.warning(f"Recovery pre-action failed: {pre_action}")
                # Continue anyway, might still work

        return True  # Pre-actions completed

    def reset_attempt_counts(self) -> None:
        """Reset attempt counts for a new action."""
        self._attempt_counts.clear()

    def create_error_event(
        self,
        error_type: ErrorType,
        action: Action,
        strategy_used: Optional[str] = None,
        recovery_successful: bool = False
    ) -> ErrorEvent:
        """
        Create an error event record.

        Args:
            error_type: Type of error
            action: The failed action
            strategy_used: Name of recovery strategy used
            recovery_successful: Whether recovery succeeded

        Returns:
            ErrorEvent instance
        """
        return ErrorEvent(
            error_type=error_type,
            action_description=str(action),
            recovery_attempted=strategy_used is not None,
            recovery_successful=recovery_successful,
            recovery_strategy=strategy_used
        )

    def get_error_summary(self, error_history: List[ErrorEvent]) -> Dict[str, Any]:
        """
        Get a summary of errors for analysis.

        Args:
            error_history: List of error events

        Returns:
            Summary dictionary
        """
        if not error_history:
            return {"total_errors": 0}

        type_counts = {}
        recovery_success = 0
        recovery_total = 0

        for event in error_history:
            type_name = event.error_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

            if event.recovery_attempted:
                recovery_total += 1
                if event.recovery_successful:
                    recovery_success += 1

        return {
            "total_errors": len(error_history),
            "error_types": type_counts,
            "recovery_attempts": recovery_total,
            "recovery_successes": recovery_success,
            "recovery_rate": recovery_success / recovery_total if recovery_total > 0 else 0
        }
