"""LLM-driven controller using Claude's tool_use feature.

This module implements the main controller where LLM is the brain
and VLM is a tool that LLM can call when needed.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Tuple

import anthropic

from ..models.action import Action, ActionType
from ..perception.screen_capture import ScreenCapture
from ..perception.vlm_client import VLMClient
from ..action.executor import ActionExecutor
from ..utils.logger import get_logger
from .tools import ALL_TOOLS
from .prompts import CONTROLLER_SYSTEM_PROMPT, LOOK_AT_SCREEN_PROMPT

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
        max_tokens: int = 4096,
        monitor_index: int = 1,
        action_delay: float = 0.5,
        on_step_callback: Optional[Callable[[StepResult], None]] = None
    ):
        """
        Initialize the LLM controller.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
            vlm_client: VLM client for look_at_screen tool
            uia_client: UIAutomation client for element detection
            max_tokens: Max tokens for LLM response
            monitor_index: Monitor index for screen capture
            action_delay: Delay between actions
            on_step_callback: Callback for each step
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.vlm_client = vlm_client
        self.uia_client = uia_client
        self.max_tokens = max_tokens
        self.action_delay = action_delay
        self.on_step_callback = on_step_callback

        # Initialize components
        self.screen_capture = ScreenCapture(monitor_index=monitor_index)
        self.executor = ActionExecutor()

        # State
        self.state: Optional[ControllerState] = None

        logger.info(f"LLMController initialized with model: {model}")

    def run(self, task: str, max_steps: int = 40) -> bool:
        """
        Execute a task using the LLM controller.

        Args:
            task: Natural language task description
            max_steps: Maximum number of steps (tool calls)

        Returns:
            True if task completed successfully, False otherwise
        """
        logger.info(f"Starting task: {task}")

        # Initialize state
        self.state = ControllerState(
            task=task,
            max_steps=max_steps,
            start_time=datetime.now()
        )

        # Initial user message
        self.state.messages = [{
            "role": "user",
            "content": f"任务: {task}\n\n请完成这个任务。首先使用 look_at_screen 工具查看当前屏幕状态，然后根据观察结果执行相应操作。"
        }]

        try:
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

        except KeyboardInterrupt:
            logger.info("Task interrupted by user")
            return False
        except Exception as e:
            logger.error(f"Task failed with error: {e}")
            self.state.is_failed = True
            self.state.error_message = str(e)
            raise

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
