"""Main agent controller implementing the plan-execute-verify loop."""

import time
from enum import Enum
from typing import Optional, Callable, Any

from .models.action import Action, ActionType, AgentState
from .brain.planner import Planner, PlanningMode
from .brain.verifier import Verifier
from .perception.screen_capture import ScreenCapture
from .perception.vlm_client import VLMClient
from .action.executor import ActionExecutor
from .utils.logger import get_logger

logger = get_logger(__name__)


class AgentStatus(Enum):
    """Agent execution status."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class ScreenControlAgent:
    """
    Main agent class that orchestrates screen control tasks.

    Implements a plan-execute-verify loop:
    1. Capture screenshot
    2. Plan next action using VLM
    3. Execute the action
    4. Verify the result
    5. Repeat until task is done or max steps reached
    """

    def __init__(
        self,
        vlm_client: VLMClient,
        max_steps: int = 20,
        action_delay: float = 0.5,
        verify_each_step: bool = True,
        monitor_index: int = 1,
        planning_mode: str = "hybrid",
        grounding_confidence_threshold: float = 0.4,
        uia_client: Any = None
    ):
        """
        Initialize the agent.

        Args:
            vlm_client: VLM client for analyzing screenshots
            max_steps: Maximum number of steps before giving up
            action_delay: Delay between actions in seconds
            verify_each_step: Whether to verify after each action
            monitor_index: Monitor to capture (1 = primary)
            planning_mode: Planning mode ("visual_only", "grounded", or "hybrid")
            grounding_confidence_threshold: Minimum confidence for grounded coords
            uia_client: Optional UIAutomation client instance
        """
        self.vlm_client = vlm_client
        self.max_steps = max_steps
        self.action_delay = action_delay
        self.verify_each_step = verify_each_step

        # Parse planning mode
        mode_map = {
            "visual_only": PlanningMode.VISUAL_ONLY,
            "grounded": PlanningMode.GROUNDED,
            "hybrid": PlanningMode.HYBRID
        }
        self.planning_mode = mode_map.get(planning_mode.lower(), PlanningMode.HYBRID)
        logger.info(f"Planning mode: {self.planning_mode.value}")

        self.screen_capture = ScreenCapture(monitor_index=monitor_index)
        self.planner = Planner(
            vlm_client,
            mode=self.planning_mode,
            uia_client=uia_client,
            grounding_confidence_threshold=grounding_confidence_threshold
        )
        self.verifier = Verifier(vlm_client)
        self.executor = ActionExecutor()

        self.status = AgentStatus.IDLE
        self.state: Optional[AgentState] = None

        self.on_step_callback: Optional[Callable[[AgentState, Action], None]] = None

    def run(self, task: str) -> bool:
        """
        Execute a task.

        Args:
            task: Natural language task description

        Returns:
            True if task completed successfully, False otherwise
        """
        logger.info(f"Starting task: {task}")

        self.state = AgentState(
            current_task=task,
            max_steps=self.max_steps
        )

        try:
            while self.state.step_count < self.state.max_steps:
                if self.state.is_completed:
                    self.status = AgentStatus.COMPLETED
                    logger.info("Task completed successfully!")
                    return True

                success = self._execute_step()

                if not success:
                    logger.warning(f"Step {self.state.step_count + 1} execution failed")

                self.state.step_count += 1
                time.sleep(self.action_delay)

            logger.warning(f"Reached max steps ({self.max_steps}) without completing task")
            self.status = AgentStatus.FAILED
            return False

        except KeyboardInterrupt:
            logger.info("Task interrupted by user")
            self.status = AgentStatus.FAILED
            return False

        except Exception as e:
            logger.error(f"Task failed with error: {e}")
            self.status = AgentStatus.FAILED
            self.state.error_message = str(e)
            raise

    def _execute_step(self) -> bool:
        """
        Execute a single step: capture -> plan -> execute -> verify.

        Returns:
            True if step succeeded, False otherwise
        """
        # 1. Capture screenshot
        logger.debug("Capturing screenshot...")
        self.state.screenshot = self.screen_capture.capture()

        # 2. Plan next action
        self.status = AgentStatus.PLANNING
        logger.debug("Planning next action...")

        try:
            action, raw_response = self.planner.plan_next_action(self.state)
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return False

        step_num = self.state.step_count + 1
        logger.info(f"[Step {step_num}] {action}")

        # Check if task is done
        if action.action_type == ActionType.DONE:
            self.state.is_completed = True
            return True

        # 3. Execute action
        self.status = AgentStatus.EXECUTING
        logger.debug("Executing action...")

        success = self.executor.execute(action)
        if not success:
            logger.error("Action execution failed")
            return False

        # Record action in history
        self.state.add_action(action)

        # 4. Verify (optional)
        if self.verify_each_step:
            self.status = AgentStatus.VERIFYING
            logger.debug("Verifying action...")

            # Wait for UI to update
            time.sleep(0.3)
            new_screenshot = self.screen_capture.capture()

            result = self.verifier.verify_action(
                screenshot=new_screenshot,
                task=self.state.current_task,
                action_description=str(action)
            )

            logger.debug(f"Verification: {result.observation[:100]}...")

            if result.task_completed:
                self.state.is_completed = True
                logger.info("Verifier detected task completion")

            if result.issues:
                logger.warning(f"Issues detected: {result.issues}")

        # Trigger callback if set
        if self.on_step_callback:
            self.on_step_callback(self.state, action)

        return True
