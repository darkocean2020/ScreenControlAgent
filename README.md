# ScreenControlAgent

基于 LLM + VLM 的智能屏幕控制代理，能够理解自然语言指令并自动操作计算机完成任务。

> 目前仅支持 Windows 10/11，建议使用 1080p 显示屏。

## 特性

- **自然语言控制** - 用自然语言描述任务，代理自动执行
- **GPT-5.2 驱动** - 统一 VLM Brain，同时处理视觉理解和决策推理
- **多模态感知** - 视觉 (VLM) + 结构化信息 (Accessibility Tree) 融合
- **智能规划** - 支持复杂任务分解、多步规划
- **子任务反思** - 每个子任务完成后验证，失败自动重试
- **记忆系统** - 短期 + 长期记忆，从历史经验中学习
- **技能系统** - 预定义操作序列，高效完成常见任务
- **知识库 (RAG)** - 存储应用指南、UI 模式等知识

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                        用户任务输入                           │
└─────────────────────────────┬────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│              大脑层 (Brain Layer - GPT-5.2 VLM)              │
│                                                              │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────┐ │
│  │任务规划器  │ │ 记忆系统  │ │ 反思验证  │ │ 技能/知识库  │ │
│  └───────────┘ └───────────┘ └───────────┘ └──────────────┘ │
│                                                              │
│  VLM Brain 通过 function calling 调用工具:                    │
│  look_at_screen | click | type_text | hotkey | scroll | ...  │
└─────────────────────────────┬────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                   感知层 (Perception Layer)                   │
│  ┌────────────────┐  ┌───────────────────────────────────┐   │
│  │ 视觉感知 (VLM)  │  │ 结构化感知 (Accessibility Tree)    │   │
│  │ GPT-5.2/4o     │  │ Windows UIAutomation              │   │
│  └────────────────┘  └───────────────────────────────────┘   │
│                              ↓                                │
│               多模态融合 (Grounding Module)                   │
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
- Windows 10/11
- API 密钥：OpenAI (GPT-5.2/GPT-4o)

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
# ANTHROPIC_API_KEY=sk-ant-your-key-here  # 可选，用于分离架构模式
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

# 创建 OpenAI VLM Brain 控制器
controller = OpenAILLMController(
    api_key=config.openai_api_key,
    model="gpt-5.2",  # 统一 VLM Brain
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
# 统一 VLM Brain 模式
controller:
  mode: "vlm_brain"
  llm:
    model: "gpt-5.2"  # 统一 VLM Brain，同时处理视觉和推理
    max_tokens: 4096

vlm:
  provider: "openai"
  openai:
    model: "gpt-4o"  # VLM 用于 look_at_screen 工具

agent:
  max_steps: 0  # 0 = 无限制
  action_delay: 0.5

grounding:
  enabled: true
  mode: "hybrid"  # visual_only, grounded, hybrid

memory:
  enabled: true
  long_term_storage: "data/memory.json"

task_planning:
  enabled: true
  auto_decompose: true

# 分离架构模式（可选）
separated_arch:
  enabled: false  # 设为 true 启用分离架构
  perception_provider: "openai"
  perception_model: "gpt-4o"
  reasoning_provider: "claude"
  reasoning_model: "claude-opus-4-20250514"
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `task` | 要执行的任务描述 |
| `-i, --interactive` | 交互模式 |
| `--max-steps` | 最大执行步数（默认无限制） |
| `-v, --verbose` | 详细日志 |
| `-c, --config` | 配置文件路径 |

## 项目结构

```
src/screen_agent/
├── main.py               # CLI 入口
├── brain/                # 大脑层
│   ├── openai_controller.py # OpenAI GPT 控制器 (主要，GPT-5.2)
│   ├── llm_controller.py # Claude LLM 控制器 (备用/分离架构)
│   ├── task_planner.py   # 复杂任务分解
│   ├── reflection.py     # 子任务反思验证
│   ├── tools.py          # LLM 工具定义
│   └── prompts.py        # 提示词模板
├── perception/           # 感知层
│   ├── screen_capture.py # 屏幕截图 (mss)
│   ├── vlm_client.py     # VLM 客户端 (Claude/OpenAI)
│   └── ui_automation.py  # Windows UIAutomation
├── action/               # 执行层
│   ├── executor.py       # 动作执行器
│   ├── mouse.py          # 鼠标控制 (人类化运动)
│   └── keyboard.py       # 键盘控制
├── memory/               # 记忆系统
│   ├── memory_manager.py # 记忆管理器
│   ├── short_term.py     # 短期记忆
│   └── long_term.py      # 长期记忆
├── skills/               # 技能系统
│   ├── skill_base.py     # 技能基类
│   ├── skill_registry.py # 技能注册表
│   ├── skill_executor.py # 技能执行器
│   └── builtin_skills.py # 内置技能
├── rag/                  # 知识检索系统
│   ├── knowledge_store.py# 知识库存储
│   └── retriever.py      # 知识检索
├── models/               # 数据模型
│   ├── action.py         # Action, ActionType
│   ├── task.py           # Subtask, TaskPlan
│   └── ui_element.py     # UIElement, ControlType
└── ui/                   # PyQt5 界面
    ├── main_window.py    # 主窗口
    └── floating_overlay.py # 浮动覆盖层
```

## 工作原理

1. **任务分解** - 复杂任务自动分解为多个子任务
2. **VLM Brain** - GPT-5.2 作为统一大脑，同时处理视觉理解和决策推理
3. **Function Calling** - VLM Brain 通过 `look_at_screen` 工具分析屏幕
4. **UIAutomation 提供精确坐标** - Windows Accessibility Tree 获取 UI 元素位置
5. **执行动作** - pyautogui 控制鼠标和键盘
6. **子任务验证** - 每个子任务完成后验证结果，失败则反思并重试
7. **循环直到完成** - VLM Brain 判断任务是否完成，调用 `task_complete` 结束

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
| `find_element(name)` | 通过名称查找 UI 元素，返回坐标 |
| `click_element(name)` | 直接点击具名元素 |
| `use_skill(name, params)` | 调用预定义技能 |
| `task_complete(summary)` | 任务完成 |

## 内置技能

| 技能 | 说明 | 参数 |
|------|------|------|
| `open_app` | 通过 Windows 搜索打开应用 | app_name |
| `save_file` | 保存文件 (Ctrl+S) | filename |
| `navigate_to_url` | 在浏览器中导航 | url |
| `new_document` | 新建文档 (Ctrl+N) | - |
| `type_and_enter` | 输入并按 Enter | text |
| `copy_paste` | 复制粘贴 | target_x, target_y |
| `confirm_dialog` | 处理确认对话框 | action (yes/no/ok/cancel) |

## 技术栈

| 组件 | 技术 |
|------|------|
| VLM Brain (统一大脑) | GPT-5.2 (OpenAI) - 同时处理视觉和推理 |
| 分离架构 (可选) | 感知: GPT-4o + 推理: Claude Opus |
| 屏幕捕获 | mss |
| UI 自动化 | Windows UIAutomation (comtypes) |
| 鼠标/键盘 | pyautogui, pynput |
| 记忆存储 | JSON |
| GUI | PyQt5 |
| 配置 | YAML + dotenv |

## 参考项目

- [ScreenAgent](https://github.com/niuzaisheng/ScreenAgent) - IJCAI 2024
- [Claude Computer Use](https://docs.anthropic.com/en/docs/build-with-claude/computer-use)
- [UI-TARS](https://github.com/nicholaschenai/UI-TARS)

## License

MIT
