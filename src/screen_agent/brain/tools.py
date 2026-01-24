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
    "description": "在指定坐标点击鼠标左键。坐标从屏幕左上角(0,0)开始。",
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

WAIT_TOOL = {
    "name": "wait",
    "description": "等待指定的秒数。用于等待页面加载、动画完成等。",
    "input_schema": {
        "type": "object",
        "properties": {
            "seconds": {
                "type": "number",
                "description": "等待的秒数，如 0.5, 1, 2 等"
            }
        },
        "required": ["seconds"]
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

# All tools list
ALL_TOOLS: List[Dict[str, Any]] = [
    LOOK_AT_SCREEN_TOOL,
    CLICK_TOOL,
    DOUBLE_CLICK_TOOL,
    RIGHT_CLICK_TOOL,
    TYPE_TEXT_TOOL,
    HOTKEY_TOOL,
    SCROLL_TOOL,
    WAIT_TOOL,
    TASK_COMPLETE_TOOL,
]


def get_tool_names() -> List[str]:
    """Get list of all tool names."""
    return [tool["name"] for tool in ALL_TOOLS]


def get_tool_by_name(name: str) -> Dict[str, Any]:
    """Get tool definition by name."""
    for tool in ALL_TOOLS:
        if tool["name"] == name:
            return tool
    return None
