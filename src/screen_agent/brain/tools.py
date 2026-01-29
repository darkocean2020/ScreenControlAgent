"""Tool definitions for LLM-driven controller.

This module defines all tools available to the LLM controller using
Claude's tool_use feature.
"""

from typing import Dict, List, Any

# =============================================================================
# Tool Definitions (JSON Schema format for Claude API)
# =============================================================================

LOOK_AT_SCREEN_TOOL = {
    "name": "look_at_screen",
    "description": "查看当前屏幕内容。返回屏幕状态描述、可见元素列表及其坐标。在需要了解屏幕当前状态时调用此工具。",
    "input_schema": {
        "type": "object",
        "properties": {
            "focus_hint": {
                "type": "string",
                "description": "可选的关注提示，告诉视觉模型重点关注什么，例如'查找保存按钮'或'关注弹出对话框'"
            }
        },
        "required": []
    }
}

CLICK_TOOL = {
    "name": "click",
    "description": "在指定坐标点击鼠标左键。坐标从屏幕左上角(0,0)开始。\n\n**警告**: 直接使用坐标点击容易因坐标不精确而失败。请优先使用 click_element(name) 工具，仅在 click_element 找不到目标元素时才使用此工具。\n如果必须使用此工具，请务必填写 element_name 参数以启用自动坐标校正。",
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {
                "type": "integer",
                "description": "X 坐标（像素）"
            },
            "y": {
                "type": "integer",
                "description": "Y 坐标（像素）"
            },
            "element_name": {
                "type": "string",
                "description": "目标元素名称（强烈建议提供！系统会自动使用 UIAutomation 校正坐标，大幅提高点击精度）"
            }
        },
        "required": ["x", "y"]
    }
}

DOUBLE_CLICK_TOOL = {
    "name": "double_click",
    "description": "在指定坐标双击鼠标左键。常用于打开文件或应用程序。",
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {
                "type": "integer",
                "description": "X 坐标（像素）"
            },
            "y": {
                "type": "integer",
                "description": "Y 坐标（像素）"
            },
            "element_name": {
                "type": "string",
                "description": "目标元素名称（用于日志记录，可选）"
            }
        },
        "required": ["x", "y"]
    }
}

RIGHT_CLICK_TOOL = {
    "name": "right_click",
    "description": "在指定坐标点击鼠标右键，打开上下文菜单。",
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {
                "type": "integer",
                "description": "X 坐标（像素）"
            },
            "y": {
                "type": "integer",
                "description": "Y 坐标（像素）"
            }
        },
        "required": ["x", "y"]
    }
}

TYPE_TEXT_TOOL = {
    "name": "type_text",
    "description": "输入文本内容。支持中文、日文等 Unicode 字符。在输入前请确保已点击目标输入框。",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "要输入的文本内容"
            }
        },
        "required": ["text"]
    }
}

HOTKEY_TOOL = {
    "name": "hotkey",
    "description": "按下快捷键组合。常用键包括: ctrl, alt, shift, win, enter, tab, escape, backspace, delete, up, down, left, right, f1-f12 等。",
    "input_schema": {
        "type": "object",
        "properties": {
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "按键列表，如 ['ctrl', 'c'] 表示 Ctrl+C，['win'] 表示 Windows 键，['enter'] 表示回车键"
            }
        },
        "required": ["keys"]
    }
}

SCROLL_TOOL = {
    "name": "scroll",
    "description": "滚动鼠标滚轮。正数向上滚动，负数向下滚动。",
    "input_schema": {
        "type": "object",
        "properties": {
            "amount": {
                "type": "integer",
                "description": "滚动量。正数向上滚动，负数向下滚动。建议值: 3（小滚动）到 10（大滚动）"
            },
            "x": {
                "type": "integer",
                "description": "滚动位置的 X 坐标（可选，默认使用当前鼠标位置）"
            },
            "y": {
                "type": "integer",
                "description": "滚动位置的 Y 坐标（可选，默认使用当前鼠标位置）"
            }
        },
        "required": ["amount"]
    }
}

TASK_COMPLETE_TOOL = {
    "name": "task_complete",
    "description": "标记任务已完成。只有在确认任务目标已达成时才调用此工具。",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "任务完成的简要说明"
            }
        },
        "required": ["summary"]
    }
}

# =============================================================================
# Grounding Tools (UIAutomation-based precise element interaction)
# =============================================================================

FIND_ELEMENT_TOOL = {
    "name": "find_element",
    "description": "【首选】通过名称或文本查找屏幕上的UI元素，返回精确坐标（像素级精度）。使用 Windows Accessibility API，精度远超截图估计。在点击任何UI元素之前应先调用此工具或 click_element。",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "要查找的元素名称或文本，如'保存'、'确定'、'取消'、'文件名'等"
            },
            "element_type": {
                "type": "string",
                "description": "元素类型过滤（可选），如'Button'、'Edit'、'MenuItem'、'ListItem'等",
                "enum": ["Button", "Edit", "MenuItem", "ListItem", "CheckBox", "RadioButton", "ComboBox", "Tab", "Link", "Text", "Any"]
            }
        },
        "required": ["name"]
    }
}

CLICK_ELEMENT_TOOL = {
    "name": "click_element",
    "description": "【首选点击方式】通过名称直接点击UI元素，无需手动指定坐标。系统使用 Windows Accessibility API 自动查找元素并点击其精确中心位置。精度和可靠性远超手动指定坐标的 click(x,y) 工具。只有当此工具找不到目标元素时，才应使用 click(x,y) 工具。",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "要点击的元素名称或文本，如'保存'、'确定'、'取消'等"
            },
            "element_type": {
                "type": "string",
                "description": "元素类型过滤（可选），如'Button'、'Edit'等",
                "enum": ["Button", "Edit", "MenuItem", "ListItem", "CheckBox", "RadioButton", "ComboBox", "Tab", "Link", "Text", "Any"]
            },
            "click_type": {
                "type": "string",
                "description": "点击类型（可选），默认为单击",
                "enum": ["single", "double", "right"],
                "default": "single"
            }
        },
        "required": ["name"]
    }
}

# =============================================================================
# Skills Tool (invoke pre-defined skills)
# =============================================================================

USE_SKILL_TOOL = {
    "name": "use_skill",
    "description": """调用预定义技能来执行常见任务。技能是经过优化的动作序列，比手动操作更可靠。

可用技能:
- open_app(app_name): 通过 Windows 搜索打开应用程序
- save_file(filename): 保存当前文件（Ctrl+S + 输入文件名 + Enter）
- navigate_to_url(url): 在浏览器中导航到指定网址
- new_document(): 新建空白文档（Ctrl+N）
- type_and_enter(text): 输入文本并按 Enter
- copy_paste(target_x, target_y): 复制选中内容并粘贴到目标位置
- confirm_dialog(action): 处理确认对话框（yes/no/ok/cancel）

使用技能可以减少出错，推荐用于常见操作。""",
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "技能名称，如 'open_app', 'save_file', 'navigate_to_url' 等"
            },
            "params": {
                "type": "object",
                "description": "技能参数，根据技能不同而不同。例如 open_app 需要 {\"app_name\": \"记事本\"}",
                "additionalProperties": True
            }
        },
        "required": ["skill_name", "params"]
    }
}

# All tools list
ALL_TOOLS: List[Dict[str, Any]] = [
    LOOK_AT_SCREEN_TOOL,
    FIND_ELEMENT_TOOL,
    CLICK_ELEMENT_TOOL,
    USE_SKILL_TOOL,
    CLICK_TOOL,
    DOUBLE_CLICK_TOOL,
    RIGHT_CLICK_TOOL,
    TYPE_TEXT_TOOL,
    HOTKEY_TOOL,
    SCROLL_TOOL,
    TASK_COMPLETE_TOOL,
]


def get_tool_names() -> List[str]:
    """Get list of all tool names."""
    return [tool["name"] for tool in ALL_TOOLS]
