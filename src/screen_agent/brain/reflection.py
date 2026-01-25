"""Reflection workflow for subtask-level verification and retry.

This module implements a reflection workflow that operates at the subtask level,
not at every tool call. After executing a subtask, it verifies completion,
analyzes failures, and generates alternative approaches for retry.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

from PIL import Image

from ..models.task import Subtask, SubtaskStatus
from ..perception.vlm_client import VLMClient
from ..memory.memory_manager import MemoryManager
from ..utils.logger import get_logger
from .prompts import REFLECTION_VERIFY_PROMPT, REFLECTION_ANALYZE_PROMPT

logger = get_logger(__name__)


@dataclass
class ReflectionResult:
    """Result of reflection analysis."""
    subtask_completed: bool
    confidence: float
    observation: str
    failure_reason: Optional[str] = None
    suggested_approach: Optional[str] = None
    should_retry: bool = False
    similar_cases: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "subtask_completed": self.subtask_completed,
            "confidence": self.confidence,
            "observation": self.observation,
            "failure_reason": self.failure_reason,
            "suggested_approach": self.suggested_approach,
            "should_retry": self.should_retry
        }


@dataclass
class ReflectionAttempt:
    """Record of a single reflection attempt."""
    attempt_number: int
    result: ReflectionResult
    actions_taken: List[str]
    timestamp: datetime = field(default_factory=datetime.now)


class ReflectionWorkflow:
    """
    Subtask-level reflection workflow.

    Provides verification after subtask execution, failure analysis,
    and alternative approach generation for retry attempts.
    """

    def __init__(
        self,
        vlm_client: VLMClient,
        memory_manager: Optional[MemoryManager] = None,
        max_retries: int = 2,
        confidence_threshold: float = 0.7
    ):
        """
        Initialize reflection workflow.

        Args:
            vlm_client: VLM client for screen analysis
            memory_manager: Optional memory manager for case retrieval
            max_retries: Maximum retry attempts per subtask
            confidence_threshold: Minimum confidence to consider subtask complete
        """
        self.vlm_client = vlm_client
        self.memory_manager = memory_manager
        self.max_retries = max_retries
        self.confidence_threshold = confidence_threshold

        # Track attempts per subtask
        self._attempts: Dict[str, List[ReflectionAttempt]] = {}

        logger.info(f"ReflectionWorkflow initialized (max_retries={max_retries})")

    def verify_subtask(
        self,
        subtask: Subtask,
        screenshot: Image.Image,
        actions_taken: List[str]
    ) -> ReflectionResult:
        """
        Verify if a subtask has been completed.

        Args:
            subtask: The subtask to verify
            screenshot: Current screenshot
            actions_taken: List of action descriptions taken

        Returns:
            ReflectionResult with verification outcome
        """
        logger.info(f"Verifying subtask: {subtask.description[:50]}...")

        # Get similar cases from memory
        similar_cases = []
        if self.memory_manager:
            context = self.memory_manager.get_context_for_planning(subtask.description)
            similar_cases = context.get("similar_tasks", [])

        # Build prompt
        prompt = REFLECTION_VERIFY_PROMPT.format(
            subtask_description=subtask.description,
            success_criteria=subtask.success_criteria,
            actions_taken="\n".join(f"  - {a}" for a in actions_taken[-10:]),
            similar_cases=self._format_similar_cases(similar_cases)
        )

        try:
            response = self.vlm_client.analyze_screen(
                screenshot=screenshot,
                prompt=prompt,
                system_prompt="你是一个任务验证助手，客观判断子任务是否完成。"
            )

            result = self._parse_verify_response(response, similar_cases)
            logger.info(
                f"Verification result: completed={result.subtask_completed}, "
                f"confidence={result.confidence:.2f}"
            )

            # Record attempt
            self._record_attempt(subtask.id, result, actions_taken)

            return result

        except Exception as e:
            logger.error(f"Subtask verification failed: {e}")
            return ReflectionResult(
                subtask_completed=False,
                confidence=0.0,
                observation=f"Verification error: {str(e)}",
                should_retry=True
            )

    def reflect_on_failure(
        self,
        subtask: Subtask,
        screenshot: Image.Image,
        actions_taken: List[str],
        previous_result: ReflectionResult
    ) -> ReflectionResult:
        """
        Reflect on a failed subtask and generate alternative approach.

        Args:
            subtask: The failed subtask
            screenshot: Current screenshot
            actions_taken: Actions that were taken
            previous_result: The previous verification result

        Returns:
            ReflectionResult with analysis and suggested approach
        """
        logger.info(f"Reflecting on failure: {subtask.description[:50]}...")

        # Get attempt history
        attempts = self._attempts.get(subtask.id, [])
        attempt_count = len(attempts)

        # Get similar successful cases
        similar_cases = []
        if self.memory_manager:
            context = self.memory_manager.get_context_for_planning(subtask.description)
            # Filter for successful cases only
            similar_cases = [
                c for c in context.get("similar_tasks", [])
                if c.get("success", False)
            ]

        # Build reflection prompt
        prompt = REFLECTION_ANALYZE_PROMPT.format(
            subtask_description=subtask.description,
            success_criteria=subtask.success_criteria,
            actions_taken="\n".join(f"  - {a}" for a in actions_taken[-10:]),
            attempt_count=attempt_count,
            previous_observation=previous_result.observation,
            previous_failure=previous_result.failure_reason or "Unknown",
            similar_cases=self._format_similar_cases(similar_cases)
        )

        try:
            response = self.vlm_client.analyze_screen(
                screenshot=screenshot,
                prompt=prompt,
                system_prompt="你是一个任务分析专家，分析失败原因并提供替代方案。"
            )

            result = self._parse_analyze_response(response, attempt_count)
            logger.info(
                f"Reflection result: should_retry={result.should_retry}, "
                f"suggested_approach={result.suggested_approach[:50] if result.suggested_approach else 'None'}..."
            )

            return result

        except Exception as e:
            logger.error(f"Reflection analysis failed: {e}")
            return ReflectionResult(
                subtask_completed=False,
                confidence=0.0,
                observation=f"Reflection error: {str(e)}",
                failure_reason="Reflection analysis failed",
                should_retry=attempt_count < self.max_retries
            )

    def record_outcome(
        self,
        subtask: Subtask,
        success: bool,
        total_attempts: int,
        learned_pattern: Optional[str] = None
    ) -> None:
        """
        Record the final outcome of a subtask to memory.

        Args:
            subtask: The subtask that was executed
            success: Whether it ultimately succeeded
            total_attempts: Total number of attempts made
            learned_pattern: Optional pattern learned from this execution
        """
        if not self.memory_manager:
            return

        logger.info(
            f"Recording outcome: subtask='{subtask.description[:30]}...', "
            f"success={success}, attempts={total_attempts}"
        )

        # Get the attempts for this subtask
        attempts = self._attempts.get(subtask.id, [])

        # Build learned patterns
        patterns = []
        if learned_pattern:
            patterns.append(learned_pattern)

        # If successful after multiple attempts, record what worked
        if success and total_attempts > 1 and attempts:
            last_attempt = attempts[-1]
            if last_attempt.result.suggested_approach:
                patterns.append(
                    f"Alternative approach: {last_attempt.result.suggested_approach}"
                )

        # Record failure patterns
        if not success and attempts:
            failure_reasons = [
                a.result.failure_reason
                for a in attempts
                if a.result.failure_reason
            ]
            if failure_reasons:
                self.memory_manager.record_error(failure_reasons[-1])

        # Clear attempts for this subtask
        if subtask.id in self._attempts:
            del self._attempts[subtask.id]

    def get_attempt_count(self, subtask_id: str) -> int:
        """Get the number of attempts for a subtask."""
        return len(self._attempts.get(subtask_id, []))

    def should_continue_retry(self, subtask_id: str) -> bool:
        """Check if we should continue retrying a subtask."""
        return self.get_attempt_count(subtask_id) < self.max_retries

    def reset(self) -> None:
        """Reset all attempt tracking."""
        self._attempts.clear()

    def _record_attempt(
        self,
        subtask_id: str,
        result: ReflectionResult,
        actions_taken: List[str]
    ) -> None:
        """Record an attempt for a subtask."""
        if subtask_id not in self._attempts:
            self._attempts[subtask_id] = []

        attempt = ReflectionAttempt(
            attempt_number=len(self._attempts[subtask_id]) + 1,
            result=result,
            actions_taken=actions_taken.copy()
        )
        self._attempts[subtask_id].append(attempt)

    def _format_similar_cases(self, cases: List[Dict[str, Any]]) -> str:
        """Format similar cases for prompt injection."""
        if not cases:
            return "无相似案例"

        lines = []
        for i, case in enumerate(cases[:3], 1):
            status = "成功" if case.get("success") else "失败"
            task = case.get("task", "Unknown task")
            steps = case.get("steps", 0)
            actions = case.get("key_actions", [])[:3]

            lines.append(f"{i}. [{status}] {task} ({steps}步)")
            if actions:
                for action in actions:
                    lines.append(f"   - {action}")

        return "\n".join(lines)

    def _parse_verify_response(
        self,
        response: str,
        similar_cases: List[Dict[str, Any]]
    ) -> ReflectionResult:
        """Parse verification response from VLM."""
        # Try to extract JSON
        json_match = re.search(r'\{[\s\S]*\}', response)

        if json_match:
            try:
                data = json.loads(json_match.group())
                return ReflectionResult(
                    subtask_completed=data.get("subtask_completed", False),
                    confidence=float(data.get("confidence", 0.5)),
                    observation=data.get("observation", response[:500]),
                    failure_reason=data.get("failure_reason"),
                    should_retry=not data.get("subtask_completed", False),
                    similar_cases=similar_cases
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: heuristic parsing
        response_lower = response.lower()
        completed = any(kw in response_lower for kw in [
            "completed", "完成", "成功", "done", "finished"
        ])
        failed = any(kw in response_lower for kw in [
            "failed", "失败", "未完成", "not complete", "incomplete"
        ])

        return ReflectionResult(
            subtask_completed=completed and not failed,
            confidence=0.6 if completed else 0.4,
            observation=response[:500],
            should_retry=not completed,
            similar_cases=similar_cases
        )

    def _parse_analyze_response(
        self,
        response: str,
        attempt_count: int
    ) -> ReflectionResult:
        """Parse reflection analysis response from VLM."""
        # Try to extract JSON
        json_match = re.search(r'\{[\s\S]*\}', response)

        if json_match:
            try:
                data = json.loads(json_match.group())
                should_retry = data.get("should_retry", attempt_count < self.max_retries)

                return ReflectionResult(
                    subtask_completed=False,
                    confidence=float(data.get("confidence", 0.5)),
                    observation=data.get("observation", response[:500]),
                    failure_reason=data.get("failure_reason", "Unknown"),
                    suggested_approach=data.get("suggested_approach"),
                    should_retry=should_retry
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback
        return ReflectionResult(
            subtask_completed=False,
            confidence=0.3,
            observation=response[:500],
            failure_reason="Could not parse reflection response",
            should_retry=attempt_count < self.max_retries
        )
