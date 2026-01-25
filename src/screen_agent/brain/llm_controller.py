"""LLM-driven controller using Claude's tool_use feature.

This module implements the main controller where LLM is the brain
and VLM is a tool that LLM can call when needed.

Supports subtask-level reflection workflow for verification and retry.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Tuple

import anthropic

from ..models.action import Action, ActionType
from ..models.task import Subtask, TaskPlan, SubtaskStatus
from ..perception.screen_capture import ScreenCapture
from ..perception.vlm_client import VLMClient
from ..action.executor import ActionExecutor
from ..memory.memory_manager import MemoryManager
from ..utils.logger import get_logger
from .tools import ALL_TOOLS
from .prompts import CONTROLLER_SYSTEM_PROMPT, LOOK_AT_SCREEN_PROMPT
from .task_planner import TaskPlanner
from .reflection import ReflectionWorkflow, ReflectionResult

logger = get_logger(__name__)


@dataclass
class ControllerState:
    """State of the LLM controller."""
    task: str = ""
    step_count: int = 0
    max_steps: int = 40
    is_completed: bool = False
    is_failed: bool = False
    error_message: str = ""
    start_time: Optional[datetime] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_call_history: List[Dict[str, Any]] = field(default_factory=list)
    # Subtask tracking
    task_plan: Optional[TaskPlan] = None
    current_subtask: Optional[Subtask] = None
    subtask_actions: List[str] = field(default_factory=list)


@dataclass
class StepResult:
    """Result of a single step."""
    tool_name: str
    tool_input: Dict[str, Any]
    tool_result: str
    success: bool
    is_task_complete: bool = False


class LLMController:
    """
    LLM-driven controller that uses Claude's tool_use feature.

    The LLM acts as the brain, deciding when to:
    - Look at the screen (via VLM tool)
    - Execute actions (click, type, etc.)
    - Complete the task
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        vlm_client: Optional[VLMClient] = None,
        uia_client: Optional[Any] = None,
        memory_manager: Optional[MemoryManager] = None,
        max_tokens: int = 4096,
        monitor_index: int = 1,
        action_delay: float = 0.5,
        enable_reflection: bool = True,
        reflection_max_retries: int = 2,
        on_step_callback: Optional[Callable[[StepResult], None]] = None,
        on_subtask_callback: Optional[Callable[[Subtask, bool], None]] = None
    ):
        """
        Initialize the LLM controller.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
            vlm_client: VLM client for look_at_screen tool
            uia_client: UIAutomation client for element detection
            memory_manager: Memory manager for context retrieval
            max_tokens: Max tokens for LLM response
            monitor_index: Monitor index for screen capture
            action_delay: Delay between actions
            enable_reflection: Whether to enable subtask-level reflection
            reflection_max_retries: Max retries per subtask in reflection
            on_step_callback: Callback for each step
            on_subtask_callback: Callback for subtask completion (subtask, success)
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.vlm_client = vlm_client
        self.uia_client = uia_client
        self.memory_manager = memory_manager
        self.max_tokens = max_tokens
        self.action_delay = action_delay
        self.enable_reflection = enable_reflection
        self.on_step_callback = on_step_callback
        self.on_subtask_callback = on_subtask_callback

        # Initialize components
        self.screen_capture = ScreenCapture(monitor_index=monitor_index)
        self.executor = ActionExecutor()

        # Task planner (optional, requires VLM)
        self.task_planner: Optional[TaskPlanner] = None
        if vlm_client:
            self.task_planner = TaskPlanner(vlm_client)

        # Reflection workflow (optional, requires VLM)
        self.reflection: Optional[ReflectionWorkflow] = None
        if enable_reflection and vlm_client:
            self.reflection = ReflectionWorkflow(
                vlm_client=vlm_client,
                memory_manager=memory_manager,
                max_retries=reflection_max_retries
            )

        # State
        self.state: Optional[ControllerState] = None

        logger.info(
            f"LLMController initialized with model: {model}, "
            f"reflection={'enabled' if self.reflection else 'disabled'}"
        )

    def run(self, task: str, max_steps: int = 0) -> bool:
        """
        Execute a task using the LLM controller.

        Supports subtask decomposition and reflection workflow when enabled.

        Args:
            task: Natural language task description
            max_steps: Maximum number of steps (0 = unlimited)

        Returns:
            True if task completed successfully, False otherwise
        """
        # 0 means unlimited
        if max_steps <= 0:
            max_steps = 999999
        logger.info(f"Starting task: {task}")

        # Initialize state
        self.state = ControllerState(
            task=task,
            max_steps=max_steps,
            start_time=datetime.now()
        )

        # Start memory session if available
        if self.memory_manager:
            self.memory_manager.start_session(task)

        try:
            # Check if task needs decomposition
            if self.task_planner and self.task_planner.should_decompose(task):
                screenshot = self.screen_capture.capture()
                plan = self.task_planner.decompose(task, screenshot)
                self.state.task_plan = plan

                if len(plan.subtasks) > 1:
                    logger.info(f"Task decomposed into {len(plan.subtasks)} subtasks")
                    return self._run_with_subtasks(plan, max_steps)

            # No decomposition, run directly
            return self._run_direct(task, max_steps)

        except KeyboardInterrupt:
            logger.info("Task interrupted by user")
            return False
        except Exception as e:
            logger.error(f"Task failed with error: {e}")
            self.state.is_failed = True
            self.state.error_message = str(e)
            raise
        finally:
            # Save memory session
            if self.memory_manager:
                learned_patterns = self._extract_learned_patterns()
                self.memory_manager.save_session(
                    self.state.is_completed,
                    learned_patterns
                )

    def _run_with_subtasks(self, plan: TaskPlan, max_steps: int) -> bool:
        """
        Execute task with subtask decomposition and reflection.

        Args:
            plan: The task plan with subtasks
            max_steps: Maximum total steps

        Returns:
            True if all subtasks completed successfully
        """
        plan.start()

        for subtask in plan.subtasks:
            logger.info(f"Starting subtask {subtask.id}: {subtask.description[:50]}...")
            self.state.current_subtask = subtask
            self.state.subtask_actions.clear()
            subtask.start()

            # Execute subtask with reflection
            success = self._execute_subtask_with_reflection(subtask, max_steps)

            if success:
                subtask.complete()
                logger.info(f"Subtask {subtask.id} completed")
            else:
                subtask.fail("Subtask execution failed after retries")
                logger.warning(f"Subtask {subtask.id} failed")

            # Callback
            if self.on_subtask_callback:
                self.on_subtask_callback(subtask, success)

            # Check if we should continue
            if not success and subtask.status == SubtaskStatus.FAILED:
                # Could implement skip logic here
                logger.error(f"Stopping due to subtask failure: {subtask.id}")
                self.state.is_failed = True
                return False

            if self.state.step_count >= max_steps:
                logger.warning("Reached max steps during subtask execution")
                return False

        self.state.is_completed = True
        logger.info("All subtasks completed successfully")
        return True

    def _execute_subtask_with_reflection(
        self,
        subtask: Subtask,
        max_steps: int
    ) -> bool:
        """
        Execute a single subtask with reflection and retry.

        Args:
            subtask: The subtask to execute
            max_steps: Global max steps limit

        Returns:
            True if subtask completed successfully
        """
        max_retries = self.reflection.max_retries if self.reflection else 0

        for attempt in range(max_retries + 1):
            logger.info(f"Subtask attempt {attempt + 1}/{max_retries + 1}")

            # Execute the subtask (must have actions taken)
            actions_before = len(self.state.subtask_actions)
            self._execute_subtask_actions(subtask, max_steps)
            actions_after = len(self.state.subtask_actions)

            # Check if any actions were actually taken
            if actions_after == actions_before and attempt > 0:
                logger.warning("No new actions taken in retry, continuing to next attempt")
                # Force a new execution by resetting conversation context
                self._reset_subtask_context(subtask)
                continue

            # Verify with reflection
            if self.reflection:
                screenshot = self.screen_capture.capture()
                result = self.reflection.verify_subtask(
                    subtask,
                    screenshot,
                    self.state.subtask_actions
                )

                if result.subtask_completed:
                    self.reflection.record_outcome(
                        subtask, True, attempt + 1
                    )
                    return True

                # If not completed and should retry
                if result.should_retry and attempt < max_retries:
                    logger.info(f"Subtask not complete, reflecting for retry...")

                    # Reflect on failure to get alternative approach
                    reflection_result = self.reflection.reflect_on_failure(
                        subtask,
                        screenshot,
                        self.state.subtask_actions,
                        result
                    )

                    if reflection_result.suggested_approach:
                        # Inject alternative approach hint
                        self._inject_reflection_hint(reflection_result)

                    # Clear actions for retry but keep reflection hint in messages
                    self.state.subtask_actions.clear()
                    continue
                else:
                    # No more retries
                    self.reflection.record_outcome(
                        subtask, False, attempt + 1
                    )
                    return False
            else:
                # No reflection, assume success if task_complete was called
                return self.state.is_completed

        return False

    def _reset_subtask_context(self, subtask: Subtask) -> None:
        """
        Reset conversation context for a fresh subtask retry.

        Args:
            subtask: The subtask being retried
        """
        # Keep only the last few messages for context, then add fresh prompt
        if len(self.state.messages) > 4:
            self.state.messages = self.state.messages[-2:]

        retry_prompt = (
            f"请重新尝试完成子任务: {subtask.description}\n"
            f"成功标准: {subtask.success_criteria}\n\n"
            f"首先使用 look_at_screen 查看当前屏幕状态，然后执行必要的操作。"
        )

        self.state.messages.append({
            "role": "user",
            "content": retry_prompt
        })

    def _execute_subtask_actions(self, subtask: Subtask, max_steps: int) -> None:
        """
        Execute actions for a subtask until completion or step limit.

        Args:
            subtask: The current subtask
            max_steps: Global max steps
        """
        # Build initial message for this subtask
        subtask_prompt = (
            f"当前子任务: {subtask.description}\n"
            f"成功标准: {subtask.success_criteria}\n\n"
            f"请完成这个子任务。首先使用 look_at_screen 工具查看当前屏幕状态。\n"
            f"注意: 完成这个子任务后，不要调用 task_complete，系统会自动验证并进入下一个子任务。"
        )

        # If we have previous context, include it
        if len(self.state.messages) > 0:
            self.state.messages.append({
                "role": "user",
                "content": subtask_prompt
            })
        else:
            self.state.messages = [{
                "role": "user",
                "content": f"总任务: {self.state.task}\n\n{subtask_prompt}"
            }]

        # Track if this subtask called task_complete (should be treated as subtask done)
        subtask_done = False

        # Execute until subtask seems complete or limits reached
        subtask_steps = 0
        max_subtask_steps = min(20, max_steps - self.state.step_count)

        while subtask_steps < max_subtask_steps:
            # In subtask mode, is_completed means subtask is done, not whole task
            if subtask_done:
                # Reset for next subtask
                self.state.is_completed = False
                break

            response = self._call_llm()
            if response is None:
                break

            should_continue = self._process_response(response)
            subtask_steps += 1
            self.state.step_count += 1

            # Check if task_complete was called (means subtask is done)
            if self.state.is_completed:
                subtask_done = True
                continue

            if not should_continue:
                break

            time.sleep(self.action_delay)

    def _inject_reflection_hint(self, result: ReflectionResult) -> None:
        """
        Inject reflection hint into the conversation for retry.

        Args:
            result: The reflection result with suggested approach
        """
        hint_message = (
            f"[反思] 上次尝试未成功完成子任务。\n"
            f"失败原因: {result.failure_reason}\n"
            f"建议方案: {result.suggested_approach}\n\n"
            f"请根据上述建议，尝试用不同的方法完成子任务。"
        )

        self.state.messages.append({
            "role": "user",
            "content": hint_message
        })

        logger.info(f"Injected reflection hint: {result.suggested_approach[:100]}...")

    def _run_direct(self, task: str, max_steps: int) -> bool:
        """
        Run task directly without subtask decomposition.

        Args:
            task: Task description
            max_steps: Maximum steps

        Returns:
            True if completed successfully
        """
        # Initial user message
        self.state.messages = [{
            "role": "user",
            "content": f"任务: {task}\n\n请完成这个任务。首先使用 look_at_screen 工具查看当前屏幕状态，然后根据观察结果执行相应操作。"
        }]

        while self.state.step_count < max_steps:
            if self.state.is_completed:
                logger.info("Task completed successfully!")
                return True

            if self.state.is_failed:
                logger.error(f"Task failed: {self.state.error_message}")
                return False

            # Call LLM
            response = self._call_llm()

            if response is None:
                logger.error("LLM call failed")
                return False

            # Process response
            should_continue = self._process_response(response)

            if not should_continue:
                break

            self.state.step_count += 1
            time.sleep(self.action_delay)

        if not self.state.is_completed:
            logger.warning(f"Reached max steps ({max_steps}) without completing task")
            return False

        return True

    def _extract_learned_patterns(self) -> List[str]:
        """Extract learned patterns from the execution for memory."""
        patterns = []

        if not self.state or not self.state.tool_call_history:
            return patterns

        # Extract action sequence pattern
        actions = []
        for call in self.state.tool_call_history[-10:]:
            tool = call.get("tool", "")
            if tool not in ["look_at_screen", "task_complete"]:
                actions.append(tool)

        if len(actions) >= 2:
            pattern = "Sequence: " + " -> ".join(actions[:5])
            patterns.append(pattern)

        return patterns

    def _call_llm(self) -> Optional[anthropic.types.Message]:
        """Call the LLM with current messages and tools."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=CONTROLLER_SYSTEM_PROMPT,
                tools=ALL_TOOLS,
                messages=self.state.messages
            )
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _process_response(self, response: anthropic.types.Message) -> bool:
        """
        Process LLM response and execute tool calls.

        Returns:
            True to continue, False to stop
        """
        # Check stop reason
        if response.stop_reason == "end_turn":
            # LLM decided to end without tool use
            # Check if there's text content indicating completion
            for block in response.content:
                if hasattr(block, 'text'):
                    logger.info(f"LLM response: {block.text[:200]}...")
            return False

        if response.stop_reason != "tool_use":
            logger.warning(f"Unexpected stop reason: {response.stop_reason}")
            return False

        # Process tool calls
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

                # Execute tool
                result, success, is_complete = self._execute_tool(tool_name, tool_input)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result
                })

                # Record in history
                self.state.tool_call_history.append({
                    "step": self.state.step_count,
                    "tool": tool_name,
                    "input": tool_input,
                    "result": result[:500] if len(result) > 500 else result,
                    "success": success
                })

                # Track subtask actions for reflection
                if self.state.current_subtask and tool_name not in ["look_at_screen"]:
                    action_desc = self._format_action_description(tool_name, tool_input)
                    self.state.subtask_actions.append(action_desc)

                # Callback
                if self.on_step_callback:
                    step_result = StepResult(
                        tool_name=tool_name,
                        tool_input=tool_input,
                        tool_result=result,
                        success=success,
                        is_task_complete=is_complete
                    )
                    self.on_step_callback(step_result)

                # Check if task is complete
                if is_complete:
                    self.state.is_completed = True
                    return False

            elif hasattr(block, 'text') and block.text:
                logger.debug(f"LLM thinking: {block.text[:200]}...")

        # Add assistant response and tool results to messages
        self.state.messages.append({
            "role": "assistant",
            "content": response.content
        })

        self.state.messages.append({
            "role": "user",
            "content": tool_results
        })

        return True

    def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Tuple[str, bool, bool]:
        """
        Execute a tool and return the result.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool

        Returns:
            Tuple of (result_string, success_bool, is_task_complete_bool)
        """
        try:
            if tool_name == "look_at_screen":
                return self._tool_look_at_screen(tool_input), True, False

            elif tool_name == "click":
                return self._tool_click(tool_input), True, False

            elif tool_name == "double_click":
                return self._tool_double_click(tool_input), True, False

            elif tool_name == "right_click":
                return self._tool_right_click(tool_input), True, False

            elif tool_name == "type_text":
                return self._tool_type_text(tool_input), True, False

            elif tool_name == "hotkey":
                return self._tool_hotkey(tool_input), True, False

            elif tool_name == "scroll":
                return self._tool_scroll(tool_input), True, False

            elif tool_name == "task_complete":
                return self._tool_task_complete(tool_input), True, True

            else:
                return f"Unknown tool: {tool_name}", False, False

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return f"Error executing {tool_name}: {str(e)}", False, False

    def _tool_look_at_screen(self, input: Dict[str, Any]) -> str:
        """Execute look_at_screen tool - uses VLM to analyze screen."""
        # Capture screenshot
        screenshot = self.screen_capture.capture()
        screen_size = screenshot.size

        # Get UI element tree if available
        element_context = ""
        if self.uia_client and self.uia_client.is_available():
            try:
                ui_tree = self.uia_client.get_element_tree()
                element_context = ui_tree.to_text_representation(max_elements=50)
            except Exception as e:
                logger.warning(f"Failed to get UI element tree: {e}")

        # Build prompt for VLM
        focus_hint = input.get("focus_hint", "")

        prompt = LOOK_AT_SCREEN_PROMPT.format(
            screen_width=screen_size[0],
            screen_height=screen_size[1],
            focus_hint=f"\n重点关注: {focus_hint}" if focus_hint else "",
            element_context=element_context if element_context else "无法获取 UI 元素列表"
        )

        # Call VLM if available
        if self.vlm_client:
            try:
                result = self.vlm_client.analyze_screen(
                    screenshot=screenshot,
                    prompt=prompt,
                    system_prompt="你是一个视觉观察助手，客观准确地描述屏幕内容。"
                )
                return result
            except Exception as e:
                logger.error(f"VLM analysis failed: {e}")
                return f"VLM 分析失败: {str(e)}\n\nUI 元素列表:\n{element_context}"
        else:
            # No VLM available, return element context only
            return f"屏幕分辨率: {screen_size[0]}x{screen_size[1]}\n\nUI 元素列表:\n{element_context}"

    def _tool_click(self, input: Dict[str, Any]) -> str:
        """Execute click tool."""
        x = input["x"]
        y = input["y"]
        element_name = input.get("element_name", "")

        action = Action(
            action_type=ActionType.CLICK,
            coordinates=(x, y),
            description=f"Click on {element_name}" if element_name else f"Click at ({x}, {y})"
        )

        success = self.executor.execute(action)

        if success:
            return f"成功点击坐标 ({x}, {y})" + (f" - {element_name}" if element_name else "")
        else:
            return f"点击失败: ({x}, {y})"

    def _tool_double_click(self, input: Dict[str, Any]) -> str:
        """Execute double_click tool."""
        x = input["x"]
        y = input["y"]
        element_name = input.get("element_name", "")

        action = Action(
            action_type=ActionType.DOUBLE_CLICK,
            coordinates=(x, y),
            description=f"Double-click on {element_name}" if element_name else f"Double-click at ({x}, {y})"
        )

        success = self.executor.execute(action)

        if success:
            return f"成功双击坐标 ({x}, {y})" + (f" - {element_name}" if element_name else "")
        else:
            return f"双击失败: ({x}, {y})"

    def _tool_right_click(self, input: Dict[str, Any]) -> str:
        """Execute right_click tool."""
        x = input["x"]
        y = input["y"]

        action = Action(
            action_type=ActionType.RIGHT_CLICK,
            coordinates=(x, y)
        )

        success = self.executor.execute(action)

        if success:
            return f"成功右键点击坐标 ({x}, {y})"
        else:
            return f"右键点击失败: ({x}, {y})"

    def _tool_type_text(self, input: Dict[str, Any]) -> str:
        """Execute type_text tool."""
        text = input["text"]

        action = Action(
            action_type=ActionType.TYPE,
            text=text
        )

        success = self.executor.execute(action)

        if success:
            preview = text[:50] + "..." if len(text) > 50 else text
            return f"成功输入文本: '{preview}'"
        else:
            return f"文本输入失败"

    def _tool_hotkey(self, input: Dict[str, Any]) -> str:
        """Execute hotkey tool."""
        keys = input["keys"]

        action = Action(
            action_type=ActionType.HOTKEY,
            keys=keys
        )

        success = self.executor.execute(action)

        key_str = "+".join(keys)
        if success:
            return f"成功按下快捷键: {key_str}"
        else:
            return f"快捷键执行失败: {key_str}"

    def _tool_scroll(self, input: Dict[str, Any]) -> str:
        """Execute scroll tool."""
        amount = input["amount"]
        x = input.get("x")
        y = input.get("y")

        action = Action(
            action_type=ActionType.SCROLL,
            scroll_amount=amount,
            coordinates=(x, y) if x is not None and y is not None else None
        )

        success = self.executor.execute(action)

        direction = "向上" if amount > 0 else "向下"
        if success:
            return f"成功{direction}滚动 {abs(amount)} 格"
        else:
            return f"滚动失败"

    def _tool_task_complete(self, input: Dict[str, Any]) -> str:
        """Execute task_complete tool."""
        summary = input["summary"]

        logger.info(f"Task completed: {summary}")
        return f"任务已完成: {summary}"

    def get_state(self) -> Optional[ControllerState]:
        """Get the current controller state."""
        return self.state

    def get_tool_history(self) -> List[Dict[str, Any]]:
        """Get the tool call history."""
        if self.state:
            return self.state.tool_call_history
        return []

    def _format_action_description(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> str:
        """
        Format a tool call as a human-readable action description.

        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters

        Returns:
            Human-readable action description
        """
        if tool_name == "click":
            x, y = tool_input.get("x", 0), tool_input.get("y", 0)
            element = tool_input.get("element_name", "")
            if element:
                return f"Click on '{element}' at ({x}, {y})"
            return f"Click at ({x}, {y})"

        elif tool_name == "double_click":
            x, y = tool_input.get("x", 0), tool_input.get("y", 0)
            return f"Double-click at ({x}, {y})"

        elif tool_name == "right_click":
            x, y = tool_input.get("x", 0), tool_input.get("y", 0)
            return f"Right-click at ({x}, {y})"

        elif tool_name == "type_text":
            text = tool_input.get("text", "")
            preview = text[:30] + "..." if len(text) > 30 else text
            return f"Type: '{preview}'"

        elif tool_name == "hotkey":
            keys = tool_input.get("keys", [])
            return f"Hotkey: {'+'.join(keys)}"

        elif tool_name == "scroll":
            amount = tool_input.get("amount", 0)
            direction = "up" if amount > 0 else "down"
            return f"Scroll {direction} by {abs(amount)}"

        elif tool_name == "task_complete":
            return f"Task complete"

        else:
            return f"{tool_name}: {tool_input}"

    def get_task_plan(self) -> Optional[TaskPlan]:
        """Get the current task plan if available."""
        if self.state:
            return self.state.task_plan
        return None
