# ScreenControlAgent

基于 LLM + VLM 的智能屏幕控制代理，能够理解自然语言指令并自动操作计算机完成任务。

> 目前仅支持 1080p 显示屏，运行时需要把屏幕调成 1080p。

## 特性

- **自然语言控制** - 用自然语言描述任务，代理自动执行
- **OpenAI 驱动架构** - GPT-5.2/GPT-4o 作为大脑决策和视觉工具
- **多模态感知** - 视觉（VLM）+ 结构化信息（Accessibility Tree）融合
- **智能规划** - 支持复杂任务分解、多步规划
- **子任务反思** - 每个子任务完成后验证，失败自动重试
- **记忆系统** - 短期 + 长期记忆，从历史经验中学习
- **错误恢复** - 自动检测异常状态并尝试恢复

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                        用户任务输入                           │
└─────────────────────────────┬────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│              大脑层 (Brain Layer - OpenAI LLM)               │
│                                                              │
│  LLM 通过 function calling 调用以下工具:                      │
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
- API 密钥：OpenAI

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
# OPENAI_API_KEY=sk-your-key-here
```

## 快速开始

### GUI 模式（推荐）

```bash
python run_ui.py
```

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

### Python API

```python
from screen_agent.brain.openai_controller import OpenAILLMController
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

# 创建 OpenAI LLM 控制器
controller = OpenAILLMController(
    api_key=config.openai_api_key,
    model="gpt-5.2",  # 或 gpt-4o
    vlm_client=vlm_client,
    uia_client=uia_client
)

# 执行任务
success = controller.run("打开记事本并输入 Hello World")
print("成功" if success else "失败")
```

## 配置

配置文件位于 `config/settings.yaml`:

```yaml
controller:
  llm:
    model: "gpt-5.2"  # OpenAI 模型: gpt-4o, gpt-5.2, o1 等
    max_tokens: 4096

  vlm_tool:
    model: "gpt-4o"  # VLM 用于 look_at_screen 工具

agent:
  max_steps: 40
  action_delay: 0.5
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
│   ├── openai_controller.py # OpenAI LLM 控制器（主要）
│   ├── llm_controller.py # Claude LLM 控制器（备用）
│   ├── task_planner.py   # 复杂任务分解
│   ├── reflection.py     # 子任务反思验证
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

1. **任务分解** - 复杂任务自动分解为多个子任务
2. **LLM 作为大脑** - OpenAI GPT 使用 function calling 决定下一步操作
3. **VLM 作为眼睛** - GPT-4o 通过 `look_at_screen` 工具分析屏幕
4. **UIAutomation 提供精确坐标** - Windows Accessibility Tree 获取 UI 元素位置
5. **执行动作** - pyautogui 控制鼠标和键盘
6. **子任务验证** - 每个子任务完成后验证结果，失败则反思并重试
7. **循环直到完成** - LLM 判断任务是否完成，调用 `task_complete` 结束

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
| LLM (大脑) | OpenAI GPT-5.2 / GPT-4o (function calling) |
| VLM (视觉) | GPT-4o |
| 屏幕捕获 | mss |
| UI 自动化 | Windows UIAutomation |
| 鼠标/键盘 | pyautogui |
| GUI | PyQt5 |

## 参考项目

- [ScreenAgent](https://github.com/niuzaisheng/ScreenAgent) - IJCAI 2024
- [Claude Computer Use](https://docs.anthropic.com/en/docs/build-with-claude/computer-use)
- [UI-TARS](https://github.com/nicholaschenai/UI-TARS)
