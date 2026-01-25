# ScreenControlAgent

基于 LLM + VLM 的智能屏幕控制代理，能够理解自然语言指令并自动操作计算机完成任务。

> 目前仅支持 1080p 显示屏，运行时需要把屏幕调成 1080p。

## 特性

- **自然语言控制** - 用自然语言描述任务，代理自动执行
- **LLM 驱动架构** - Claude 作为大脑决策，GPT-4o 作为视觉工具
- **多模态感知** - 视觉（VLM）+ 结构化信息（Accessibility Tree）融合
- **智能规划** - 支持复杂任务分解、多步规划
- **记忆系统** - 短期 + 长期记忆，从历史经验中学习
- **错误恢复** - 自动检测异常状态并尝试恢复

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                        用户任务输入                           │
└─────────────────────────────┬────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│              大脑层 (Brain Layer - Claude LLM)                │
│                                                              │
│  LLM 通过 tool_use 调用以下工具:                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │
│  │look_at_screen│ │ click/type │ │ hotkey/scroll/wait     │ │
│  │   (VLM)     │ │             │ │                        │ │
│  └─────────────┘ └─────────────┘ └─────────────────────────┘ │
└─────────────────────────────┬────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                   感知层 (Perception Layer)                   │
│  ┌────────────────┐  ┌───────────────────────────────────┐   │
│  │ 视觉感知 (VLM)  │  │ 结构化感知 (Accessibility Tree)    │   │
│  │ GPT-4o         │  │ Windows UIAutomation              │   │
│  └────────────────┘  └───────────────────────────────────┘   │
└─────────────────────────────┬────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                    执行层 (Action Layer)                      │
│         ┌─────────────┐          ┌─────────────┐             │
│         │ 鼠标控制器   │          │ 键盘控制器   │             │
│         │ (pyautogui) │          │ (pyautogui) │             │
│         └─────────────┘          └─────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

## 安装

### 环境要求

- Python 3.10+
- Windows 10/11（当前仅支持 Windows）
- API 密钥：Anthropic（LLM）和 OpenAI（VLM）

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/darkocean2020/ScreenControlAgent
cd ScreenControlAgent

# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 如需使用 GUI，额外安装 PyQt5
pip install PyQt5>=5.15.0
```

### 配置 API 密钥

```bash
# 复制环境变量模板
copy .env.example .env

# 编辑 .env 文件，填入你的 API 密钥
# ANTHROPIC_API_KEY=sk-ant-your-key-here
# OPENAI_API_KEY=sk-your-key-here
```

## 快速开始

### 命令行模式

```bash
# 执行单个任务
python -m screen_agent.main "打开记事本并输入 Hello World"

# 交互模式
python -m screen_agent.main -i

# 详细日志
python -m screen_agent.main --verbose "打开浏览器"

# 指定最大步数
python -m screen_agent.main --max-steps 30 "完成复杂任务"
```

### GUI 模式

```bash
python run_ui.py
```

### Python API

```python
from screen_agent.brain.llm_controller import LLMController
from screen_agent.perception.vlm_client import OpenAIVLMClient
from screen_agent.perception.ui_automation import UIAutomationClient
from screen_agent.utils.config import load_config

# 加载配置
config = load_config()

# 创建 VLM 客户端 (用于 look_at_screen 工具)
vlm_client = OpenAIVLMClient(
    api_key=config.openai_api_key,
    model="gpt-4o"
)

# 创建 UIAutomation 客户端 (可选但推荐)
uia_client = UIAutomationClient()

# 创建 LLM 控制器
controller = LLMController(
    api_key=config.anthropic_api_key,
    model="claude-sonnet-4-20250514",
    vlm_client=vlm_client,
    uia_client=uia_client
)

# 执行任务
success = controller.run("打开记事本并输入 Hello World")
print("成功" if success else "失败")
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `task` | 要执行的任务描述 |
| `-i, --interactive` | 交互模式 |
| `--max-steps` | 最大执行步数（默认 40） |
| `-v, --verbose` | 详细日志 |
| `-c, --config` | 配置文件路径 |

## 项目结构

```
src/screen_agent/
├── main.py               # CLI 入口
├── brain/                # 大脑层
│   ├── llm_controller.py # LLM 驱动控制器（核心）
│   ├── verifier.py       # 动作验证器
│   ├── task_planner.py   # 复杂任务分解
│   ├── error_recovery.py # 错误恢复
│   ├── tools.py          # LLM 工具定义
│   └── prompts.py        # 提示词模板
├── perception/           # 感知层
│   ├── screen_capture.py # 屏幕截图
│   ├── vlm_client.py     # VLM 客户端
│   └── ui_automation.py  # Windows UIAutomation
├── action/               # 执行层
│   ├── executor.py       # 动作执行器
│   ├── mouse.py          # 鼠标控制
│   └── keyboard.py       # 键盘控制
├── memory/               # 记忆系统
│   ├── memory_manager.py # 记忆管理器
│   ├── short_term.py     # 短期记忆
│   └── long_term.py      # 长期记忆
├── models/               # 数据模型
└── ui/                   # PyQt5 界面
```

## 工作原理

1. **LLM 作为大脑** - Claude 使用 tool_use 功能决定下一步操作
2. **VLM 作为眼睛** - GPT-4o 通过 `look_at_screen` 工具分析屏幕
3. **UIAutomation 提供精确坐标** - Windows Accessibility Tree 获取 UI 元素位置
4. **执行动作** - pyautogui 控制鼠标和键盘
5. **循环直到完成** - LLM 判断任务是否完成，调用 `task_complete` 结束

## 可用工具

| 工具 | 说明 |
|------|------|
| `look_at_screen` | 查看屏幕状态，返回 VLM 分析结果和 UI 元素列表 |
| `click(x, y)` | 在指定坐标点击 |
| `double_click(x, y)` | 双击 |
| `right_click(x, y)` | 右键点击 |
| `type_text(text)` | 输入文本 |
| `hotkey(keys)` | 按快捷键，如 `["ctrl", "c"]` |
| `scroll(amount)` | 滚动，正数向上，负数向下 |
| `task_complete(summary)` | 任务完成 |

## 技术栈

| 组件 | 技术 |
|------|------|
| LLM (大脑) | Claude Sonnet (tool_use) |
| VLM (视觉) | GPT-4o |
| 屏幕捕获 | mss |
| UI 自动化 | Windows UIAutomation |
| 鼠标/键盘 | pyautogui |
| GUI | PyQt5 |

## 参考项目

- [ScreenAgent](https://github.com/niuzaisheng/ScreenAgent) - IJCAI 2024
- [Claude Computer Use](https://docs.anthropic.com/en/docs/build-with-claude/computer-use)
- [UI-TARS](https://github.com/nicholaschenai/UI-TARS)
