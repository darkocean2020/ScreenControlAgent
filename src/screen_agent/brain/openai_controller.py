"""OpenAI LLM-driven controller using GPT function calling.

This module implements the main controller using OpenAI's GPT models
with function calling (tools) feature.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Tuple

import openai
from PIL import Image

from ..models.action import Action, ActionType
from ..models.task import Subtask, TaskPlan, SubtaskStatus
from ..perception.screen_capture import ScreenCapture
from ..perception.vlm_client import VLMClient
from ..perception.som_annotator import SoMAnnotator
from ..perception.element_detector import HybridElementDetector
from ..models.som_element import SoMElement
from ..models.ui_element import BoundingRect
from ..action.executor import ActionExecutor
from ..memory.memory_manager import MemoryManager
from ..utils.logger import get_logger
from .tools import ALL_TOOLS
from .prompts import CONTROLLER_SYSTEM_PROMPT, LOOK_AT_SCREEN_PROMPT, SOM_SCREEN_PROMPT
from .task_planner import TaskPlanner
from .reflection import ReflectionWorkflow, ReflectionResult

# RAG and Skills imports (optional, graceful fallback)
try:
    from ..rag import KnowledgeStore, KnowledgeRetriever
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

try:
    from ..skills import SkillRegistry, SkillExecutor, register_builtin_skills
    SKILLS_AVAILABLE = True
except ImportError:
    SKILLS_AVAILABLE = False

logger = get_logger(__name__)


def safe_str(msg: str) -> str:
    """Convert string to ASCII-safe version for logging/printing on Windows."""
    return msg.encode('ascii', errors='replace').decode('ascii')


def safe_print(msg: str) -> None:
    """Print message with fallback for encoding errors (e.g., emoji on Windows GBK)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(safe_str(msg))


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


def convert_tools_to_openai_format(anthropic_tools: List[Dict]) -> List[Dict]:
    """Convert Anthropic tool definitions to OpenAI function format."""
    openai_tools = []
    for tool in anthropic_tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        }
        openai_tools.append(openai_tool)
    return openai_tools


class OpenAILLMController:
    """
    OpenAI LLM-driven controller that uses GPT's function calling.

    The LLM acts as the brain, deciding when to:
    - Look at the screen (via VLM tool)
    - Execute actions (click, type, etc.)
    - Complete the task
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
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
        Initialize the OpenAI LLM controller.

        Args:
            api_key: OpenAI API key
            model: OpenAI model to use (e.g., "gpt-4o", "gpt-4.5-preview")
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
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.vlm_client = vlm_client
        self.uia_client = uia_client
        self.memory_manager = memory_manager
        self.max_tokens = max_tokens
        self.action_delay = action_delay
        self.enable_reflection = enable_reflection
        self.on_step_callback = on_step_callback
        self.on_subtask_callback = on_subtask_callback

        # Convert tools to OpenAI format
        self.tools = convert_tools_to_openai_format(ALL_TOOLS)

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

        # RAG system (optional)
        self.knowledge_retriever = None
        if RAG_AVAILABLE:
            try:
                knowledge_store = KnowledgeStore()
                self.knowledge_retriever = KnowledgeRetriever(knowledge_store)
                logger.info("RAG system initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize RAG: {e}")

        # Skills system (optional)
        self.skill_executor = None
        if SKILLS_AVAILABLE:
            try:
                register_builtin_skills()
                self.skill_executor = SkillExecutor(
                    action_executor=self.executor
                )
                logger.info("Skills system initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Skills: {e}")

        # SoM (Set-of-Mark) annotator and current mark map
        self.som_annotator = SoMAnnotator()
        self._current_som_map: Dict[int, SoMElement] = {}

        # CDP client for Chrome web elements (graceful if unavailable)
        self.cdp_client = None
        try:
            from ..perception.cdp_client import CDPClient
            self.cdp_client = CDPClient()
            if self.cdp_client.is_available():
                logger.info("CDP client initialized - Chrome debug port available")
            else:
                logger.info("CDP client initialized - Chrome debug port not detected (will retry on use)")
        except ImportError:
            logger.info("CDP client not available (websocket-client not installed)")

        # Hybrid element detector (UIAutomation + CDP)
        self.element_detector = HybridElementDetector(
            uia_client=self.uia_client,
            cdp_client=self.cdp_client,
        )

        # State
        self.state: Optional[ControllerState] = None

        logger.info(
            f"OpenAILLMController initialized with model: {model}, "
            f"reflection={'enabled' if self.reflection else 'disabled'}, "
            f"RAG={'enabled' if self.knowledge_retriever else 'disabled'}, "
            f"Skills={'enabled' if self.skill_executor else 'disabled'}"
        )

    def run(self, task: str, max_steps: int = 0) -> bool:
        """
        Execute a task using the OpenAI LLM controller.

        Args:
            task: Natural language task description
            max_steps: Maximum number of steps (0 = unlimited)

        Returns:
            True if task completed successfully, False otherwise
        """
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
        """Execute task with subtask decomposition."""
        plan.start()

        for subtask in plan.subtasks:
            logger.info(f"Starting subtask {subtask.id}: {subtask.description[:50]}...")
            self.state.current_subtask = subtask
            self.state.subtask_actions.clear()
            subtask.start()

            success = self._execute_subtask_with_reflection(subtask, max_steps)

            if success:
                subtask.complete()
                logger.info(f"Subtask {subtask.id} completed")
            else:
                subtask.fail("Subtask execution failed after retries")
                logger.warning(f"Subtask {subtask.id} failed")

            if self.on_subtask_callback:
                self.on_subtask_callback(subtask, success)

            if not success and subtask.status == SubtaskStatus.FAILED:
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
        """Execute a single subtask with reflection and retry."""
        max_retries = self.reflection.max_retries if self.reflection else 0

        for attempt in range(max_retries + 1):
            logger.info(f"Subtask attempt {attempt + 1}/{max_retries + 1}")

            actions_before = len(self.state.subtask_actions)
            self._execute_subtask_actions(subtask, max_steps)
            actions_after = len(self.state.subtask_actions)

            if actions_after == actions_before and attempt > 0:
                logger.warning("No new actions taken in retry")
                self._reset_subtask_context(subtask)
                continue

            if self.reflection:
                screenshot = self.screen_capture.capture()
                result = self.reflection.verify_subtask(
                    subtask,
                    screenshot,
                    self.state.subtask_actions
                )

                if result.subtask_completed:
                    self.reflection.record_outcome(subtask, True, attempt + 1)
                    return True

                if result.should_retry and attempt < max_retries:
                    logger.info(f"Subtask not complete, reflecting for retry...")
                    reflection_result = self.reflection.reflect_on_failure(
                        subtask,
                        screenshot,
                        self.state.subtask_actions,
                        result
                    )

                    if reflection_result.suggested_approach:
                        self._inject_reflection_hint(reflection_result)

                    self.state.subtask_actions.clear()
                    continue
                else:
                    self.reflection.record_outcome(subtask, False, attempt + 1)
                    return False
            else:
                return self.state.is_completed

        return False

    def _reset_subtask_context(self, subtask: Subtask) -> None:
        """Reset conversation context for a fresh subtask retry."""
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
        """Execute actions for a subtask."""
        subtask_prompt = (
            f"当前子任务: {subtask.description}\n"
            f"成功标准: {subtask.success_criteria}\n\n"
            f"请完成这个子任务。首先使用 look_at_screen 工具查看当前屏幕状态。\n"
            f"注意: 完成这个子任务后，不要调用 task_complete，系统会自动验证并进入下一个子任务。"
        )

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

        subtask_done = False
        subtask_steps = 0
        max_subtask_steps = min(20, max_steps - self.state.step_count)

        while subtask_steps < max_subtask_steps:
            if subtask_done:
                self.state.is_completed = False
                break

            response = self._call_llm()
            if response is None:
                break

            should_continue = self._process_response(response)
            subtask_steps += 1
            self.state.step_count += 1

            if self.state.is_completed:
                subtask_done = True
                continue

            if not should_continue:
                break

            time.sleep(self.action_delay)

    def _inject_reflection_hint(self, result: ReflectionResult) -> None:
        """Inject reflection hint into the conversation."""
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
        """Run task directly without subtask decomposition."""
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

            response = self._call_llm()

            if response is None:
                logger.error("LLM call failed")
                return False

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
        """Extract learned patterns from the execution."""
        patterns = []

        if not self.state or not self.state.tool_call_history:
            return patterns

        actions = []
        for call in self.state.tool_call_history[-10:]:
            tool = call.get("tool", "")
            if tool not in ["look_at_screen", "look_at_screen_som", "task_complete"]:
                actions.append(tool)

        if len(actions) >= 2:
            pattern = "Sequence: " + " -> ".join(actions[:5])
            patterns.append(pattern)

        return patterns

    def _call_llm(self):
        """Call the OpenAI LLM with current messages and tools."""
        try:
            safe_print(f"[OpenAI] Calling {self.model}...")

            # Build system prompt with RAG context
            system_prompt = CONTROLLER_SYSTEM_PROMPT

            if self.knowledge_retriever and self.state:
                try:
                    # Retrieve relevant knowledge for the task
                    rag_context = self.knowledge_retriever.retrieve_for_task(
                        self.state.task,
                        top_k=2
                    )
                    if rag_context:
                        system_prompt = f"{CONTROLLER_SYSTEM_PROMPT}\n\n{rag_context}"
                except Exception as e:
                    logger.warning(f"RAG retrieval failed: {e}")

            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *self.state.messages
                ],
                tools=self.tools,
                tool_choice="auto"
            )
            return response
        except Exception as e:
            logger.error(f"OpenAI LLM call failed: {e}")
            safe_print(f"[OpenAI] ERROR: {e}")
            return None

    def _process_response(self, response) -> bool:
        """Process OpenAI LLM response and execute tool calls."""
        choice = response.choices[0]
        message = choice.message

        # Check if LLM wants to use tools
        if message.tool_calls:
            # Process each tool call
            tool_results = []

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    import json
                    tool_input = json.loads(tool_call.function.arguments)
                except:
                    tool_input = {}

                logger.info(f"Executing tool: {tool_name} with input: {safe_str(str(tool_input))}")
                safe_print(f"[OpenAI] Tool: {tool_name}, Input: {tool_input}")

                # Execute tool
                result, success, is_complete = self._execute_tool(tool_name, tool_input)

                tool_results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
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

                # Track subtask actions
                if self.state.current_subtask and tool_name not in ["look_at_screen", "look_at_screen_som"]:
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

                if is_complete:
                    self.state.is_completed = True
                    return False

            # Add assistant message with tool calls
            self.state.messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            })

            # Add tool results
            for tr in tool_results:
                self.state.messages.append(tr)

            return True

        else:
            # No tool calls, LLM finished
            if message.content:
                logger.info(f"LLM response: {message.content[:200]}...")
            return False

    def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Tuple[str, bool, bool]:
        """Execute a tool and return the result."""
        # Tools that change screen state → invalidate SoM map afterwards
        _ACTION_TOOLS = {
            "click", "double_click", "right_click", "type_text",
            "hotkey", "scroll", "click_element", "click_mark", "use_skill",
        }

        try:
            if tool_name == "look_at_screen":
                result = self._tool_look_at_screen(tool_input)
                return result, True, False

            elif tool_name == "look_at_screen_som":
                result = self._tool_look_at_screen_som(tool_input)
                return result, True, False

            elif tool_name == "click_mark":
                result = self._tool_click_mark(tool_input)
            elif tool_name == "click":
                result = self._tool_click(tool_input)
            elif tool_name == "double_click":
                result = self._tool_double_click(tool_input)
            elif tool_name == "right_click":
                result = self._tool_right_click(tool_input)
            elif tool_name == "type_text":
                result = self._tool_type_text(tool_input)
            elif tool_name == "hotkey":
                result = self._tool_hotkey(tool_input)
            elif tool_name == "scroll":
                result = self._tool_scroll(tool_input)
            elif tool_name == "find_element":
                result = self._tool_find_element(tool_input)
            elif tool_name == "click_element":
                result = self._tool_click_element(tool_input)
            elif tool_name == "use_skill":
                result = self._tool_use_skill(tool_input)
            elif tool_name == "task_complete":
                result = self._tool_task_complete(tool_input)
                return result, True, True
            else:
                return f"Unknown tool: {tool_name}", False, False

            # Invalidate SoM map after any action that changes screen state
            if tool_name in _ACTION_TOOLS and self._current_som_map:
                self._current_som_map.clear()

            return result, True, False

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return f"Error executing {tool_name}: {str(e)}", False, False

    def _tool_look_at_screen(self, input: Dict[str, Any]) -> str:
        """Execute look_at_screen tool using the main LLM as VLM."""
        import base64
        from io import BytesIO
        import pyautogui

        screenshot = self.screen_capture.capture()

        # Resize screenshot to logical screen resolution so VLM coordinate
        # estimates match pyautogui's logical coordinate space.
        # On high-DPI displays, mss captures at physical pixels (e.g. 2560x1440)
        # while pyautogui operates at logical pixels (e.g. 1707x960 at 150% scale).
        logical_size = pyautogui.size()
        if screenshot.size != (logical_size.width, logical_size.height):
            logger.info(
                f"Resizing screenshot from {screenshot.size} to "
                f"({logical_size.width}, {logical_size.height}) for DPI alignment"
            )
            screenshot = screenshot.resize(
                (logical_size.width, logical_size.height),
                Image.LANCZOS
            )
        screen_size = screenshot.size

        element_context = ""
        if self.uia_client and self.uia_client.is_available():
            try:
                ui_tree = self.uia_client.get_element_tree()
                element_context = ui_tree.to_text_representation(max_elements=50)
            except Exception as e:
                logger.warning(f"Failed to get UI element tree: {e}")

        focus_hint = input.get("focus_hint", "")

        prompt = LOOK_AT_SCREEN_PROMPT.format(
            screen_width=screen_size[0],
            screen_height=screen_size[1],
            focus_hint=f"\n重点关注: {focus_hint}" if focus_hint else "",
            element_context=element_context if element_context else "无法获取 UI 元素列表"
        )

        # Use the main LLM (GPT-5.2) as VLM to analyze the screenshot
        try:
            # Convert screenshot to base64
            buffer = BytesIO()
            screenshot.save(buffer, format="PNG")
            image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            # Call LLM with image
            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=1024,
                messages=[
                    {"role": "system", "content": "你是一个视觉观察助手，客观准确地描述屏幕内容。"},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"VLM analysis failed: {e}")
            return f"VLM 分析失败: {str(e)}\n\nUI 元素列表:\n{element_context}"

    def _tool_look_at_screen_som(self, input: Dict[str, Any]) -> str:
        """Execute look_at_screen_som tool: annotate screenshot with numbered marks."""
        import base64
        from io import BytesIO
        import pyautogui

        screenshot = self.screen_capture.capture()

        # DPI alignment: resize to logical resolution
        logical_size = pyautogui.size()
        if screenshot.size != (logical_size.width, logical_size.height):
            logger.info(
                f"SoM: Resizing screenshot from {screenshot.size} to "
                f"({logical_size.width}, {logical_size.height}) for DPI alignment"
            )
            screenshot = screenshot.resize(
                (logical_size.width, logical_size.height),
                Image.LANCZOS
            )

        # Collect interactive elements from all sources (UIAutomation + CDP)
        som_elements = self.element_detector.detect()
        logger.info(f"SoM: Detected {len(som_elements)} interactive elements")

        if not som_elements:
            return "SoM: 未检测到可交互元素。请使用 look_at_screen 工具查看屏幕。"

        # Annotate screenshot
        annotated_img, mark_map = self.som_annotator.annotate(screenshot, som_elements)
        self._current_som_map = mark_map

        logger.info(f"SoM: Annotated {len(mark_map)} marks on screenshot")

        # Build mark details text
        mark_lines = []
        for mid in sorted(mark_map.keys()):
            elem = mark_map[mid]
            cx, cy = elem.center
            mark_lines.append(f"[{mid}] {elem.element_type}: \"{elem.name}\" at ({cx}, {cy})")
        mark_details = "\n".join(mark_lines)

        focus_hint = input.get("focus_hint", "")

        prompt = SOM_SCREEN_PROMPT.format(
            screen_width=annotated_img.size[0],
            screen_height=annotated_img.size[1],
            focus_hint=f"\n重点关注: {focus_hint}" if focus_hint else "",
            mark_details=mark_details
        )

        # Send annotated screenshot to VLM
        try:
            buffer = BytesIO()
            annotated_img.save(buffer, format="PNG")
            image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=1024,
                messages=[
                    {"role": "system", "content": "你是一个视觉观察助手，客观准确地描述标注了编号标记的屏幕内容。"},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
            )
            vlm_result = response.choices[0].message.content

            # Append available marks summary
            vlm_result += f"\n\n可用标记: {len(mark_map)} 个元素已标注。使用 click_mark(mark_id) 精确点击。"
            return vlm_result

        except Exception as e:
            logger.error(f"SoM VLM analysis failed: {e}")
            return f"SoM VLM 分析失败: {str(e)}\n\n标记列表:\n{mark_details}"

    def _tool_click_mark(self, input: Dict[str, Any]) -> str:
        """Execute click_mark tool: click a SoM-annotated element by mark ID."""
        mark_id = input["mark_id"]
        click_type = input.get("click_type", "single")

        if not self._current_som_map:
            return "没有可用的 SoM 标记。请先调用 look_at_screen_som 获取标记。"

        if mark_id not in self._current_som_map:
            available = sorted(self._current_som_map.keys())
            return (
                f"标记 [{mark_id}] 不存在。"
                f"可用标记: {available[:20]}{'...' if len(available) > 20 else ''}"
            )

        elem = self._current_som_map[mark_id]
        x, y = elem.center

        # Determine action type
        if click_type == "double":
            action_type = ActionType.DOUBLE_CLICK
            action_desc = "双击"
        elif click_type == "right":
            action_type = ActionType.RIGHT_CLICK
            action_desc = "右键点击"
        else:
            action_type = ActionType.CLICK
            action_desc = "点击"

        action = Action(
            action_type=action_type,
            coordinates=(x, y),
            description=f"SoM {action_desc} [{mark_id}] '{elem.name}'"
        )

        success = self.executor.execute(action)

        if success:
            return f"成功{action_desc}标记 [{mark_id}] '{elem.name}' ({elem.element_type}) 于坐标 ({x}, {y})"
        else:
            return f"{action_desc}标记 [{mark_id}] 失败"

    def _uia_correct_coordinates(
        self, x: int, y: int, element_name: str
    ) -> Tuple[int, int, bool]:
        """Try to correct coordinates using UIAutomation.

        When element_name is provided and UIAutomation is available, looks up
        the element by name and picks the match closest to the VLM-estimated
        (x, y). This combines VLM semantic understanding with UIAutomation
        pixel-perfect positioning.

        Returns:
            (final_x, final_y, uia_used) tuple
        """
        if not element_name or not self.uia_client or not self.uia_client.is_available():
            return x, y, False

        try:
            ui_tree = self.uia_client.get_element_tree()
            elements = ui_tree.find_by_name(element_name, partial=True)

            if not elements:
                return x, y, False

            # Pick the element closest to the VLM-estimated coordinates
            best_element = None
            best_distance = float('inf')
            for elem in elements:
                if elem.bounding_rect and elem.is_enabled:
                    cx, cy = elem.center
                    dist = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
                    if dist < best_distance:
                        best_distance = dist
                        best_element = elem

            if best_element and best_element.center:
                final_x, final_y = best_element.center
                if best_distance > 5:
                    logger.info(
                        f"UIAutomation corrected coordinates for '{element_name}': "
                        f"({x}, {y}) -> ({final_x}, {final_y}), "
                        f"distance={best_distance:.0f}px"
                    )
                return final_x, final_y, True

        except Exception as e:
            logger.warning(f"UIAutomation lookup failed for '{element_name}': {e}")

        return x, y, False

    def _tool_click(self, input: Dict[str, Any]) -> str:
        """Execute click tool with automatic UIAutomation coordinate correction."""
        x = input["x"]
        y = input["y"]
        element_name = input.get("element_name", "")

        final_x, final_y, uia_used = self._uia_correct_coordinates(x, y, element_name)

        action = Action(
            action_type=ActionType.CLICK,
            coordinates=(final_x, final_y),
            description=f"Click on {element_name}" if element_name else f"Click at ({final_x}, {final_y})"
        )

        success = self.executor.execute(action)

        if success:
            msg = f"成功点击坐标 ({final_x}, {final_y})"
            if element_name:
                msg += f" - {element_name}"
            if uia_used:
                msg += " (UIAutomation 精确定位)"
            return msg
        else:
            return f"点击失败: ({final_x}, {final_y})"

    def _tool_double_click(self, input: Dict[str, Any]) -> str:
        """Execute double_click tool with automatic UIAutomation coordinate correction."""
        x = input["x"]
        y = input["y"]
        element_name = input.get("element_name", "")

        final_x, final_y, uia_used = self._uia_correct_coordinates(x, y, element_name)

        action = Action(
            action_type=ActionType.DOUBLE_CLICK,
            coordinates=(final_x, final_y),
            description=f"Double-click on {element_name}" if element_name else f"Double-click at ({final_x}, {final_y})"
        )

        success = self.executor.execute(action)

        if success:
            msg = f"成功双击坐标 ({final_x}, {final_y})"
            if element_name:
                msg += f" - {element_name}"
            if uia_used:
                msg += " (UIAutomation 精确定位)"
            return msg
        else:
            return f"双击失败: ({final_x}, {final_y})"

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

    def _tool_find_element(self, input: Dict[str, Any]) -> str:
        """Execute find_element tool using UIAutomation."""
        name = input["name"]
        element_type = input.get("element_type", "Any")

        if not self.uia_client or not self.uia_client.is_available():
            return f"UIAutomation 不可用，无法查找元素 '{name}'。请使用 look_at_screen 工具估计坐标。"

        try:
            ui_tree = self.uia_client.get_element_tree()
            elements = ui_tree.find_by_name(name, partial=True)

            if not elements:
                return f"未找到名称包含 '{name}' 的元素。请尝试使用不同的名称，或使用 look_at_screen 工具查看屏幕。"

            # Filter by element type if specified
            if element_type and element_type != "Any":
                filtered = [e for e in elements if element_type.lower() in str(e.control_type).lower()]
                if filtered:
                    elements = filtered

            # Return the first matching element's info
            result_lines = [f"找到 {len(elements)} 个匹配元素:"]
            for i, elem in enumerate(elements[:5]):  # Limit to 5 elements
                center = elem.center
                result_lines.append(
                    f"  {i+1}. '{elem.name}' ({str(elem.control_type)}) - 坐标: ({center[0]}, {center[1]})"
                )

            if len(elements) > 5:
                result_lines.append(f"  ... 还有 {len(elements) - 5} 个元素")

            # Recommend the first element
            best = elements[0]
            center = best.center
            result_lines.append(f"\n推荐点击: '{best.name}' ({str(best.control_type)}) at ({center[0]}, {center[1]})")

            return "\n".join(result_lines)

        except Exception as e:
            logger.error(f"find_element failed: {e}")
            return f"查找元素失败: {str(e)}"

    def _tool_click_element(self, input: Dict[str, Any]) -> str:
        """Execute click_element tool - find element by name and click it."""
        name = input["name"]
        element_type = input.get("element_type", "Any")
        click_type = input.get("click_type", "single")

        if not self.uia_client or not self.uia_client.is_available():
            return f"UIAutomation 不可用，无法点击元素 '{name}'。请使用 find_element 或 look_at_screen 获取坐标后使用 click 工具。"

        try:
            ui_tree = self.uia_client.get_element_tree()
            elements = ui_tree.find_by_name(name, partial=True)

            if not elements:
                return f"未找到名称包含 '{name}' 的元素。请尝试使用不同的名称，或使用 look_at_screen 工具查看屏幕后使用 click 工具。"

            # Filter by element type if specified
            if element_type and element_type != "Any":
                filtered = [e for e in elements if element_type.lower() in str(e.control_type).lower()]
                if filtered:
                    elements = filtered

            # Click the first matching element
            target = elements[0]
            center = target.center
            x, y = center[0], center[1]

            # Determine action type
            if click_type == "double":
                action_type = ActionType.DOUBLE_CLICK
                action_desc = "双击"
            elif click_type == "right":
                action_type = ActionType.RIGHT_CLICK
                action_desc = "右键点击"
            else:
                action_type = ActionType.CLICK
                action_desc = "点击"

            action = Action(
                action_type=action_type,
                coordinates=(x, y),
                description=f"{action_desc} '{target.name}'"
            )

            success = self.executor.execute(action)

            if success:
                return f"成功{action_desc}元素 '{target.name}' ({str(target.control_type)}) 于坐标 ({x}, {y})"
            else:
                return f"{action_desc}元素 '{target.name}' 失败"

        except Exception as e:
            logger.error(f"click_element failed: {e}")
            return f"点击元素失败: {str(e)}"

    def _tool_use_skill(self, input: Dict[str, Any]) -> str:
        """Execute use_skill tool to invoke a pre-defined skill."""
        skill_name = input.get("skill_name", "")
        params = input.get("params", {})

        if not self.skill_executor:
            return f"技能系统不可用。请使用基础工具完成操作。"

        try:
            logger.info(f"Executing skill: {skill_name} with params: {params}")
            result = self.skill_executor.execute(skill_name, params)

            if result.success:
                return f"技能 '{skill_name}' 执行成功: {result.message}\n执行了 {result.steps_executed} 个步骤"
            else:
                return f"技能 '{skill_name}' 执行失败: {result.message}\n错误: {result.error or 'Unknown'}"

        except Exception as e:
            logger.error(f"Skill execution failed: {e}")
            return f"技能执行出错: {str(e)}"

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
        """Format a tool call as a human-readable action description."""
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

        elif tool_name == "find_element":
            name = tool_input.get("name", "")
            return f"Find element: '{name}'"

        elif tool_name == "click_element":
            name = tool_input.get("name", "")
            click_type = tool_input.get("click_type", "single")
            return f"Click element: '{name}' ({click_type})"

        elif tool_name == "click_mark":
            mark_id = tool_input.get("mark_id", "?")
            click_type = tool_input.get("click_type", "single")
            return f"Click mark [{mark_id}] ({click_type})"

        elif tool_name == "use_skill":
            skill = tool_input.get("skill_name", "")
            params = tool_input.get("params", {})
            return f"Use skill: {skill}({params})"

        elif tool_name == "task_complete":
            return f"Task complete"

        else:
            return f"{tool_name}: {tool_input}"

    def get_task_plan(self) -> Optional[TaskPlan]:
        """Get the current task plan if available."""
        if self.state:
            return self.state.task_plan
        return None
