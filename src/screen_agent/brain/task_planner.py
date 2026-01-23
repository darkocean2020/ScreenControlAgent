"""Task planner for decomposing complex tasks into subtasks."""

import json
import re
from typing import Optional, List

from ..models.task import Subtask, TaskPlan, SubtaskStatus
from ..perception.vlm_client import VLMClient
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Prompt for task decomposition
TASK_DECOMPOSITION_PROMPT = """Analyze this task and determine if it needs to be broken into subtasks.

Task: {task}

Instructions:
1. If this is a simple, single-action task (like "click X" or "open Y"), set needs_decomposition to false
2. If this task has multiple distinct steps (indicated by words like "and", "then", "after", "并", "然后", "接着"), decompose it
3. Each subtask should be independently verifiable
4. Keep subtasks atomic - each should involve 1-3 actions maximum

Output JSON format:
{{
    "needs_decomposition": true/false,
    "reasoning": "Why this task does/doesn't need decomposition",
    "subtasks": [
        {{
            "id": "1",
            "description": "Clear description of what to do",
            "success_criteria": "How to verify this subtask is complete"
        }}
    ]
}}

If needs_decomposition is false, return empty subtasks array.
"""

SUBTASK_VERIFICATION_PROMPT = """Verify if this subtask has been completed.

Subtask: {subtask_description}
Success Criteria: {success_criteria}

Based on the current screenshot, determine if this subtask is complete.

Output JSON:
{{
    "completed": true/false,
    "confidence": 0.0-1.0,
    "observation": "What you see that indicates completion status"
}}
"""


class TaskPlanner:
    """
    Decomposes complex tasks into manageable subtasks.

    Uses VLM to analyze tasks and create execution plans with
    clear success criteria for each subtask.
    """

    # Keywords that indicate a task might need decomposition
    COMPLEXITY_KEYWORDS = [
        # Chinese
        "并", "然后", "接着", "之后", "再", "首先", "最后", "同时",
        # English
        "and", "then", "after", "next", "first", "finally", "also",
        "before", "while", "followed by"
    ]

    def __init__(
        self,
        vlm_client: VLMClient,
        auto_decompose: bool = True,
        max_subtasks: int = 10
    ):
        """
        Initialize task planner.

        Args:
            vlm_client: VLM client for analysis
            auto_decompose: Whether to automatically decompose complex tasks
            max_subtasks: Maximum number of subtasks allowed
        """
        self.vlm_client = vlm_client
        self.auto_decompose = auto_decompose
        self.max_subtasks = max_subtasks

    def should_decompose(self, task: str) -> bool:
        """
        Determine if a task needs decomposition.

        Args:
            task: Task description

        Returns:
            True if task appears complex enough to decompose
        """
        if not self.auto_decompose:
            return False

        task_lower = task.lower()

        # Check for complexity keywords
        has_keywords = any(kw in task_lower for kw in self.COMPLEXITY_KEYWORDS)

        # Check task length (longer tasks more likely to be complex)
        is_long = len(task) > 50

        # Check for multiple verbs (Chinese or English)
        verb_patterns = [
            r'打开.*(?:输入|写|填)',
            r'点击.*(?:然后|再)',
            r'open.*(?:type|write|enter)',
            r'click.*(?:then|and)',
        ]
        has_multiple_actions = any(
            re.search(pattern, task_lower) for pattern in verb_patterns
        )

        return has_keywords or has_multiple_actions or (is_long and has_keywords)

    def decompose(self, task: str, screenshot=None) -> TaskPlan:
        """
        Decompose a task into subtasks using VLM.

        Args:
            task: Task description to decompose
            screenshot: Optional current screenshot for context

        Returns:
            TaskPlan with subtasks
        """
        logger.info(f"Decomposing task: {task[:50]}...")

        prompt = TASK_DECOMPOSITION_PROMPT.format(task=task)

        try:
            if screenshot:
                response = self.vlm_client.analyze_screen(
                    screenshot=screenshot,
                    prompt=prompt,
                    system_prompt="You are a task planning assistant that breaks down complex tasks."
                )
            else:
                # Use chat if no screenshot
                response = self.vlm_client.chat(prompt)

            # Parse response
            plan = self._parse_decomposition_response(response, task)

            if plan.subtasks:
                logger.info(f"Task decomposed into {len(plan.subtasks)} subtasks")
                for i, st in enumerate(plan.subtasks):
                    logger.debug(f"  {i+1}. {st.description}")
            else:
                logger.info("Task does not need decomposition")

            return plan

        except Exception as e:
            logger.error(f"Task decomposition failed: {e}")
            # Return a simple plan with the original task
            return self._create_simple_plan(task)

    def _parse_decomposition_response(self, response: str, original_task: str) -> TaskPlan:
        """Parse VLM response into a TaskPlan."""
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            logger.warning("No JSON found in decomposition response")
            return self._create_simple_plan(original_task)

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse decomposition JSON: {e}")
            return self._create_simple_plan(original_task)

        if not data.get("needs_decomposition", False):
            return self._create_simple_plan(original_task)

        subtasks = []
        for st_data in data.get("subtasks", [])[:self.max_subtasks]:
            subtask = Subtask(
                id=str(st_data.get("id", len(subtasks) + 1)),
                description=st_data.get("description", ""),
                success_criteria=st_data.get("success_criteria", "Task appears complete"),
                estimated_steps=st_data.get("estimated_steps", 3)
            )
            if subtask.description:
                subtasks.append(subtask)

        if not subtasks:
            return self._create_simple_plan(original_task)

        return TaskPlan(
            original_task=original_task,
            subtasks=subtasks
        )

    def _create_simple_plan(self, task: str) -> TaskPlan:
        """Create a simple single-subtask plan."""
        return TaskPlan(
            original_task=task,
            subtasks=[
                Subtask(
                    id="1",
                    description=task,
                    success_criteria="Task is completed as described"
                )
            ]
        )

    def verify_subtask_complete(
        self,
        subtask: Subtask,
        screenshot
    ) -> tuple[bool, float, str]:
        """
        Verify if a subtask has been completed.

        Args:
            subtask: The subtask to verify
            screenshot: Current screenshot

        Returns:
            Tuple of (completed, confidence, observation)
        """
        prompt = SUBTASK_VERIFICATION_PROMPT.format(
            subtask_description=subtask.description,
            success_criteria=subtask.success_criteria
        )

        try:
            response = self.vlm_client.analyze_screen(
                screenshot=screenshot,
                prompt=prompt,
                system_prompt="You are a verification assistant checking task completion."
            )

            # Parse response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                return (
                    data.get("completed", False),
                    data.get("confidence", 0.5),
                    data.get("observation", "")
                )

        except Exception as e:
            logger.error(f"Subtask verification failed: {e}")

        return False, 0.0, "Verification failed"

    def get_subtask_context(self, plan: TaskPlan) -> str:
        """
        Get context string for current subtask to include in planning prompts.

        Args:
            plan: Current task plan

        Returns:
            Context string for prompts
        """
        if not plan or not plan.current_subtask:
            return ""

        current = plan.current_subtask
        progress = plan.progress

        lines = [
            f"CURRENT SUBTASK ({progress}):",
            f"  Description: {current.description}",
            f"  Success Criteria: {current.success_criteria}",
        ]

        # Add completed subtasks for context
        completed = [s for s in plan.subtasks if s.status == SubtaskStatus.COMPLETED]
        if completed:
            lines.append("\nCOMPLETED SUBTASKS:")
            for s in completed[-3:]:  # Last 3 completed
                lines.append(f"  - {s.description}")

        # Add upcoming subtasks
        upcoming_idx = plan.current_index + 1
        if upcoming_idx < len(plan.subtasks):
            lines.append("\nUPCOMING:")
            for s in plan.subtasks[upcoming_idx:upcoming_idx + 2]:
                lines.append(f"  - {s.description}")

        return "\n".join(lines)
