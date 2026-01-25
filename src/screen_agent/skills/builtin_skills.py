"""Built-in skills for common operations.

These skills encapsulate common tasks that the agent frequently needs
to perform, providing reliable implementations.
"""

import time
from typing import Dict, Any, List, Optional

from .skill_base import Skill, SkillParameter, SkillResult, SkillStatus, SkillStep, SimpleSkill
from .skill_registry import SkillRegistry
from ..models.action import Action, ActionType
from ..utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Open Application Skill
# =============================================================================

class OpenApplicationSkill(Skill):
    """Skill to open an application using Windows search."""

    @property
    def name(self) -> str:
        return "open_app"

    @property
    def description(self) -> str:
        return "通过 Windows 搜索打开指定应用程序"

    @property
    def parameters(self) -> List[SkillParameter]:
        return [
            SkillParameter(
                name="app_name",
                description="要打开的应用程序名称，如'记事本'、'Chrome'、'Word'",
                param_type="string",
                required=True
            )
        ]

    @property
    def tags(self) -> List[str]:
        return ["windows", "app", "open", "launch"]

    def execute(self, params: Dict[str, Any], executor) -> SkillResult:
        app_name = params["app_name"]

        try:
            # Step 1: Press Win key to open Start menu
            action = Action(action_type=ActionType.HOTKEY, keys=["win"])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法打开开始菜单",
                    steps_executed=0
                )
            time.sleep(0.5)

            # Step 2: Type app name
            action = Action(action_type=ActionType.TYPE, text=app_name)
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法输入应用名称",
                    steps_executed=1
                )
            time.sleep(0.8)

            # Step 3: Press Enter to launch
            action = Action(action_type=ActionType.HOTKEY, keys=["enter"])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法启动应用",
                    steps_executed=2
                )
            time.sleep(1.0)

            return SkillResult(
                status=SkillStatus.SUCCESS,
                message=f"已启动应用: {app_name}",
                steps_executed=3,
                data={"app_name": app_name}
            )

        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"打开应用失败: {str(e)}",
                error=str(e)
            )


# =============================================================================
# Save File Skill
# =============================================================================

class SaveFileSkill(Skill):
    """Skill to save current file with a name."""

    @property
    def name(self) -> str:
        return "save_file"

    @property
    def description(self) -> str:
        return "保存当前文件（触发另存为对话框并输入文件名）"

    @property
    def parameters(self) -> List[SkillParameter]:
        return [
            SkillParameter(
                name="filename",
                description="要保存的文件名（包含扩展名），如'文档.txt'",
                param_type="string",
                required=True
            ),
            SkillParameter(
                name="use_ctrl_s",
                description="是否使用 Ctrl+S（默认 True）。设为 False 时使用 Ctrl+Shift+S",
                param_type="bool",
                required=False,
                default=True
            )
        ]

    @property
    def tags(self) -> List[str]:
        return ["save", "file", "保存"]

    def execute(self, params: Dict[str, Any], executor) -> SkillResult:
        filename = params["filename"]
        use_ctrl_s = params.get("use_ctrl_s", True)

        try:
            # Step 1: Trigger save dialog
            if use_ctrl_s:
                action = Action(action_type=ActionType.HOTKEY, keys=["ctrl", "s"])
            else:
                action = Action(action_type=ActionType.HOTKEY, keys=["ctrl", "shift", "s"])

            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法打开保存对话框",
                    steps_executed=0
                )
            time.sleep(0.8)

            # Step 2: Type filename
            action = Action(action_type=ActionType.TYPE, text=filename)
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法输入文件名",
                    steps_executed=1
                )
            time.sleep(0.3)

            # Step 3: Press Enter to save
            action = Action(action_type=ActionType.HOTKEY, keys=["enter"])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法确认保存",
                    steps_executed=2
                )
            time.sleep(0.5)

            return SkillResult(
                status=SkillStatus.SUCCESS,
                message=f"文件已保存为: {filename}",
                steps_executed=3,
                data={"filename": filename}
            )

        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"保存文件失败: {str(e)}",
                error=str(e)
            )


# =============================================================================
# Navigate to URL Skill
# =============================================================================

class NavigateToUrlSkill(Skill):
    """Skill to navigate to a URL in browser."""

    @property
    def name(self) -> str:
        return "navigate_to_url"

    @property
    def description(self) -> str:
        return "在当前浏览器标签页中导航到指定 URL"

    @property
    def parameters(self) -> List[SkillParameter]:
        return [
            SkillParameter(
                name="url",
                description="要访问的网址，如'google.com'或'https://github.com'",
                param_type="string",
                required=True
            )
        ]

    @property
    def tags(self) -> List[str]:
        return ["browser", "navigate", "url", "网址"]

    @property
    def required_apps(self) -> List[str]:
        return ["Chrome", "Edge", "Firefox"]

    def execute(self, params: Dict[str, Any], executor) -> SkillResult:
        url = params["url"]

        try:
            # Step 1: Focus address bar with Ctrl+L
            action = Action(action_type=ActionType.HOTKEY, keys=["ctrl", "l"])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法选中地址栏",
                    steps_executed=0
                )
            time.sleep(0.3)

            # Step 2: Type URL
            action = Action(action_type=ActionType.TYPE, text=url)
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法输入网址",
                    steps_executed=1
                )
            time.sleep(0.3)

            # Step 3: Press Enter
            action = Action(action_type=ActionType.HOTKEY, keys=["enter"])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法导航",
                    steps_executed=2
                )
            time.sleep(1.0)

            return SkillResult(
                status=SkillStatus.SUCCESS,
                message=f"已导航到: {url}",
                steps_executed=3,
                data={"url": url}
            )

        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"导航失败: {str(e)}",
                error=str(e)
            )


# =============================================================================
# New Document Skill
# =============================================================================

class NewDocumentSkill(Skill):
    """Skill to create a new document in current application."""

    @property
    def name(self) -> str:
        return "new_document"

    @property
    def description(self) -> str:
        return "在当前应用中新建空白文档（使用 Ctrl+N）"

    @property
    def parameters(self) -> List[SkillParameter]:
        return [
            SkillParameter(
                name="handle_save_prompt",
                description="如果弹出保存提示，是否自动选择'不保存'",
                param_type="bool",
                required=False,
                default=True
            )
        ]

    @property
    def tags(self) -> List[str]:
        return ["new", "document", "新建", "文档"]

    def execute(self, params: Dict[str, Any], executor) -> SkillResult:
        handle_save = params.get("handle_save_prompt", True)

        try:
            # Step 1: Press Ctrl+N
            action = Action(action_type=ActionType.HOTKEY, keys=["ctrl", "n"])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法执行新建命令",
                    steps_executed=0
                )
            time.sleep(0.5)

            # Step 2: Handle save prompt if needed
            if handle_save:
                # Press 'N' for "Don't Save" or "No"
                action = Action(action_type=ActionType.HOTKEY, keys=["n"])
                executor.execute(action)  # May fail if no dialog, that's OK
                time.sleep(0.3)

            return SkillResult(
                status=SkillStatus.SUCCESS,
                message="已创建新文档",
                steps_executed=2 if handle_save else 1
            )

        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"新建文档失败: {str(e)}",
                error=str(e)
            )


# =============================================================================
# Type and Enter Skill
# =============================================================================

class TypeAndEnterSkill(Skill):
    """Skill to type text and press Enter."""

    @property
    def name(self) -> str:
        return "type_and_enter"

    @property
    def description(self) -> str:
        return "输入文本并按 Enter 键（常用于搜索、命令输入等）"

    @property
    def parameters(self) -> List[SkillParameter]:
        return [
            SkillParameter(
                name="text",
                description="要输入的文本",
                param_type="string",
                required=True
            ),
            SkillParameter(
                name="clear_first",
                description="是否先清空输入框（使用 Ctrl+A 后输入）",
                param_type="bool",
                required=False,
                default=False
            )
        ]

    @property
    def tags(self) -> List[str]:
        return ["type", "enter", "search", "输入"]

    def execute(self, params: Dict[str, Any], executor) -> SkillResult:
        text = params["text"]
        clear_first = params.get("clear_first", False)

        try:
            steps = 0

            # Optional: Clear first
            if clear_first:
                action = Action(action_type=ActionType.HOTKEY, keys=["ctrl", "a"])
                executor.execute(action)
                steps += 1
                time.sleep(0.1)

            # Type text
            action = Action(action_type=ActionType.TYPE, text=text)
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法输入文本",
                    steps_executed=steps
                )
            steps += 1
            time.sleep(0.2)

            # Press Enter
            action = Action(action_type=ActionType.HOTKEY, keys=["enter"])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法按 Enter",
                    steps_executed=steps
                )
            steps += 1

            return SkillResult(
                status=SkillStatus.SUCCESS,
                message=f"已输入并提交: {text[:50]}...",
                steps_executed=steps
            )

        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"输入失败: {str(e)}",
                error=str(e)
            )


# =============================================================================
# Copy and Paste Skill
# =============================================================================

class CopyPasteSkill(Skill):
    """Skill to copy selected content and paste it."""

    @property
    def name(self) -> str:
        return "copy_paste"

    @property
    def description(self) -> str:
        return "复制当前选中内容并粘贴到目标位置"

    @property
    def parameters(self) -> List[SkillParameter]:
        return [
            SkillParameter(
                name="target_x",
                description="粘贴目标位置的 X 坐标",
                param_type="int",
                required=True
            ),
            SkillParameter(
                name="target_y",
                description="粘贴目标位置的 Y 坐标",
                param_type="int",
                required=True
            )
        ]

    @property
    def tags(self) -> List[str]:
        return ["copy", "paste", "复制", "粘贴"]

    def execute(self, params: Dict[str, Any], executor) -> SkillResult:
        target_x = params["target_x"]
        target_y = params["target_y"]

        try:
            # Step 1: Copy
            action = Action(action_type=ActionType.HOTKEY, keys=["ctrl", "c"])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法复制",
                    steps_executed=0
                )
            time.sleep(0.2)

            # Step 2: Click target
            action = Action(action_type=ActionType.CLICK, coordinates=(target_x, target_y))
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法点击目标位置",
                    steps_executed=1
                )
            time.sleep(0.2)

            # Step 3: Paste
            action = Action(action_type=ActionType.HOTKEY, keys=["ctrl", "v"])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message="无法粘贴",
                    steps_executed=2
                )

            return SkillResult(
                status=SkillStatus.SUCCESS,
                message=f"已复制并粘贴到 ({target_x}, {target_y})",
                steps_executed=3
            )

        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"复制粘贴失败: {str(e)}",
                error=str(e)
            )


# =============================================================================
# Confirm Dialog Skill
# =============================================================================

class ConfirmDialogSkill(Skill):
    """Skill to handle confirmation dialogs."""

    @property
    def name(self) -> str:
        return "confirm_dialog"

    @property
    def description(self) -> str:
        return "处理确认对话框（选择是/否/确定/取消）"

    @property
    def parameters(self) -> List[SkillParameter]:
        return [
            SkillParameter(
                name="action",
                description="要执行的操作",
                param_type="choice",
                required=True,
                choices=["yes", "no", "ok", "cancel"]
            )
        ]

    @property
    def tags(self) -> List[str]:
        return ["dialog", "confirm", "对话框", "确认"]

    def execute(self, params: Dict[str, Any], executor) -> SkillResult:
        dialog_action = params["action"]

        try:
            # Map action to key
            key_map = {
                "yes": "y",
                "no": "n",
                "ok": "enter",
                "cancel": "escape"
            }

            key = key_map.get(dialog_action, "enter")

            action = Action(action_type=ActionType.HOTKEY, keys=[key])
            if not executor.execute(action):
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message=f"无法执行 {dialog_action}",
                    steps_executed=0
                )

            return SkillResult(
                status=SkillStatus.SUCCESS,
                message=f"已在对话框中选择: {dialog_action}",
                steps_executed=1
            )

        except Exception as e:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"处理对话框失败: {str(e)}",
                error=str(e)
            )


# =============================================================================
# Registration Function
# =============================================================================

def register_builtin_skills(registry: Optional[SkillRegistry] = None) -> None:
    """
    Register all built-in skills.

    Args:
        registry: SkillRegistry to register skills to (uses singleton if None)
    """
    if registry is None:
        registry = SkillRegistry.get_instance()

    skills = [
        OpenApplicationSkill(),
        SaveFileSkill(),
        NavigateToUrlSkill(),
        NewDocumentSkill(),
        TypeAndEnterSkill(),
        CopyPasteSkill(),
        ConfirmDialogSkill(),
    ]

    for skill in skills:
        registry.register(skill)

    logger.info(f"Registered {len(skills)} built-in skills")
