"""Main agent controller implementing the plan-execute-verify loop."""

import time
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Any, List

from .models.action import Action, ActionType, AgentState
from .models.task import ErrorType, ErrorEvent
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
    DECOMPOSING = "decomposing"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"


class ScreenControlAgent:
    """
    Main agent class that orchestrates screen control tasks.

    Implements an enhanced plan-execute-verify loop with:
    - Task decomposition for complex tasks (Phase 3)
    - Memory system for context and learning (Phase 3)
    - Error recovery mechanisms (Phase 3)
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
        uia_client: Any = None,
        # Phase 3 options
        enable_memory: bool = True,
        enable_task_planning: bool = True,
        enable_error_recovery: bool = True,
        memory_storage_path: str = "data/memory.json",
        max_recovery_attempts: int = 3
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
            enable_memory: Enable memory system (Phase 3)
            enable_task_planning: Enable task decomposition (Phase 3)
            enable_error_recovery: Enable error recovery (Phase 3)
            memory_storage_path: Path for long-term memory storage
            max_recovery_attempts: Max recovery attempts per step
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

        # Core components
        self.screen_capture = ScreenCapture(monitor_index=monitor_index)
        self.planner = Planner(
            vlm_client,
            mode=self.planning_mode,
            uia_client=uia_client,
            grounding_confidence_threshold=grounding_confidence_threshold
        )
        self.verifier = Verifier(vlm_client)
        self.executor = ActionExecutor()

        # Phase 3: Memory system
        self.memory = None
        if enable_memory:
            try:
                from .memory import MemoryManager
                self.memory = MemoryManager(storage_path=memory_storage_path)
                logger.info("Memory system enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize memory system: {e}")

        # Phase 3: Task planner
        self.task_planner = None
        if enable_task_planning:
            try:
                from .brain.task_planner import TaskPlanner
                self.task_planner = TaskPlanner(vlm_client)
                logger.info("Task planning enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize task planner: {e}")

        # Phase 3: Error recovery
        self.error_recovery = None
        self.max_recovery_attempts = max_recovery_attempts
        if enable_error_recovery:
            try:
                from .brain.error_recovery import ErrorRecovery
                self.error_recovery = ErrorRecovery(
                    vlm_client=vlm_client,
                    max_recovery_attempts=max_recovery_attempts
                )
                logger.info("Error recovery enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize error recovery: {e}")

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
        start_time = datetime.now()

        self.state = AgentState(
            current_task=task,
            max_steps=self.max_steps
        )

        # Phase 3: Start memory session
        if self.memory:
            self.memory.start_session(task)
            self.state.memory_context = self.memory.get_context_for_planning(task)

        # Phase 3: Task decomposition
        if self.task_planner and self.task_planner.should_decompose(task):
            self.status = AgentStatus.DECOMPOSING
            logger.info("Decomposing complex task...")

            screenshot = self.screen_capture.capture()
            self.state.task_plan = self.task_planner.decompose(task, screenshot)

            if self.state.task_plan and self.state.task_plan.subtasks:
                logger.info(f"Task decomposed into {len(self.state.task_plan.subtasks)} subtasks")
                self.state.task_plan.start()
                self.state.current_subtask = self.state.task_plan.current_subtask

        try:
            while self.state.step_count < self.state.max_steps:
                if self.state.is_completed:
                    self.status = AgentStatus.COMPLETED
                    logger.info("Task completed successfully!")
                    self._save_session(success=True, start_time=start_time)
                    return True

                # Check subtask completion
                if self.state.task_plan and self.state.current_subtask:
                    if self._check_subtask_completion():
                        if not self.state.advance_subtask():
                            # All subtasks done
                            self.state.is_completed = True
                            continue

                # Execute step with error recovery
                success = self._execute_step_with_recovery()

                if not success:
                    logger.warning(f"Step {self.state.step_count + 1} failed")

                self.state.step_count += 1
                self.state.reset_recovery_state()
                time.sleep(self.action_delay)

            logger.warning(f"Reached max steps ({self.max_steps}) without completing task")
            self.status = AgentStatus.FAILED
            self._save_session(success=False, start_time=start_time)
            return False

        except KeyboardInterrupt:
            logger.info("Task interrupted by user")
            self.status = AgentStatus.FAILED
            self._save_session(success=False, start_time=start_time)
            return False

        except Exception as e:
            logger.error(f"Task failed with error: {e}")
            self.status = AgentStatus.FAILED
            self.state.error_message = str(e)
            self._save_session(success=False, start_time=start_time)
            raise

    def _execute_step_with_recovery(self) -> bool:
        """
        Execute a step with error recovery support.

        Returns:
            True if step succeeded (possibly after recovery), False otherwise
        """
        success = self._execute_step()

        # If failed and recovery is enabled, attempt recovery
        if not success and self.error_recovery and self.state.last_verification:
            while self.state.recovery_attempts < self.max_recovery_attempts:
                self.status = AgentStatus.RECOVERING

                # Analyze the error
                error_type = self.error_recovery.analyze_error(
                    action=self.state.last_action,
                    verification_result=self.state.last_verification
                )

                logger.info(f"Error type: {error_type.value}")

                # Check if we can recover
                if not self.error_recovery.can_recover(error_type, self.state.recovery_attempts):
                    break

                # Get recovery strategy
                strategy = self.error_recovery.get_recovery_strategy(
                    error_type=error_type,
                    action=self.state.last_action,
                    attempt=self.state.recovery_attempts
                )

                if not strategy:
                    break

                logger.info(f"Attempting recovery: {strategy.name}")

                # Execute recovery pre-actions
                self.error_recovery.execute_recovery(
                    strategy=strategy,
                    executor=self.executor,
                    original_action=self.state.last_action
                )

                self.state.recovery_attempts += 1

                # Record error event
                if self.memory:
                    self.memory.record_error(error_type.value)

                error_event = self.error_recovery.create_error_event(
                    error_type=error_type,
                    action=self.state.last_action,
                    strategy_used=strategy.name
                )
                self.state.record_error(error_event)

                # Retry the original action if strategy says so
                if strategy.retry_original:
                    # Re-capture and re-plan
                    success = self._execute_step()
                    if success:
                        error_event.recovery_successful = True
                        logger.info(f"Recovery successful with {strategy.name}")
                        break

        return success

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

        # Show subtask context if available
        if self.state.current_subtask:
            subtask_desc = self.state.current_subtask.description[:30]
            logger.info(f"[Step {step_num}] [{subtask_desc}...] {action}")
        else:
            logger.info(f"[Step {step_num}] {action}")

        # Check if task is done
        if action.action_type == ActionType.DONE:
            self.state.is_completed = True
            return True

        # 3. Execute action
        self.status = AgentStatus.EXECUTING
        logger.debug("Executing action...")

        exec_success = self.executor.execute(action)
        if not exec_success:
            logger.error("Action execution failed")
            return False

        # Record action in history
        self.state.add_action(action)

        # Update memory with element location
        if self.memory and action.target_element_name and action.coordinates:
            self.memory.cache_element(action.target_element_name, action.coordinates)

        # 4. Verify (optional)
        verification_result = None
        if self.verify_each_step:
            self.status = AgentStatus.VERIFYING
            logger.debug("Verifying action...")

            # Wait for UI to update
            time.sleep(0.3)
            new_screenshot = self.screen_capture.capture()

            result = self.verifier.verify_action(
                screenshot=new_screenshot,
                task=self._get_current_task_description(),
                action_description=str(action)
            )

            verification_result = {
                "action_successful": result.action_successful,
                "task_completed": result.task_completed,
                "observation": result.observation,
                "issues": result.issues
            }

            self.state.last_verification = verification_result

            logger.debug(f"Verification: {result.observation[:100]}...")

            if result.task_completed:
                self.state.is_completed = True
                logger.info("Verifier detected task completion")

            if result.issues:
                logger.warning(f"Issues detected: {result.issues}")

                # Update memory with failure
                if self.memory:
                    self.memory.update_after_action(
                        action=action,
                        success=False,
                        observation=result.observation,
                        element_name=action.target_element_name,
                        coordinates=action.coordinates
                    )

                return not bool(result.issues)  # Return False if issues

            # Update memory with success
            if self.memory:
                self.memory.update_after_action(
                    action=action,
                    success=True,
                    observation=result.observation,
                    element_name=action.target_element_name,
                    coordinates=action.coordinates
                )

        # Trigger callback if set
        if self.on_step_callback:
            self.on_step_callback(self.state, action)

        return True

    def _get_current_task_description(self) -> str:
        """Get the current task or subtask description."""
        if self.state.current_subtask:
            return f"{self.state.current_task} (Current: {self.state.current_subtask.description})"
        return self.state.current_task

    def _check_subtask_completion(self) -> bool:
        """
        Check if the current subtask is complete.

        Returns:
            True if subtask is complete
        """
        if not self.task_planner or not self.state.current_subtask:
            return False

        # Use verifier to check subtask completion
        screenshot = self.screen_capture.capture()

        completed, confidence, observation = self.task_planner.verify_subtask_complete(
            subtask=self.state.current_subtask,
            screenshot=screenshot
        )

        if completed and confidence > 0.7:
            logger.info(f"Subtask completed: {self.state.current_subtask.description[:50]}...")
            self.state.current_subtask.complete()
            return True

        return False

    def _save_session(self, success: bool, start_time: datetime) -> None:
        """Save the session to memory."""
        if not self.memory:
            return

        # Extract learned patterns from successful execution
        learned_patterns = []
        if success and self.state.action_history:
            # Pattern: action sequence that worked
            action_types = [a.action_type.value for a in self.state.action_history[:5]]
            if len(action_types) >= 2:
                learned_patterns.append(f"Sequence: {' -> '.join(action_types)}")

        self.memory.save_session(
            success=success,
            learned_patterns=learned_patterns
        )

    def get_memory_stats(self) -> dict:
        """Get memory statistics."""
        if self.memory:
            return self.memory.get_statistics()
        return {"enabled": False}

    def get_error_summary(self) -> dict:
        """Get error summary from current session."""
        if self.error_recovery and self.state:
            return self.error_recovery.get_error_summary(self.state.error_history)
        return {"enabled": False}
