# ScreenControlAgent

基于 VLM（视觉语言模型）的智能屏幕控制代理，能够理解自然语言指令并自动操作计算机完成任务。
目前仅支持1080p显示屏，运行时需要把屏幕调成1080p。

## 特性

- **自然语言控制** - 用自然语言描述任务，代理自动执行
- **多模态感知** - 视觉（VLM）+ 结构化信息（Accessibility Tree）融合
- **双模式驱动**
  - `LLM_driven`: LLM 作为大脑，VLM 作为工具（推荐）
  - `VLM_driven`: VLM 直接输出动作（传统模式，慢，不精确）
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
│                大脑层 (Brain Layer - LLM)                     │
│  ┌───────────┐  ┌───────────┐  ┌─────────────────────────┐   │
│  │ 任务规划器 │  │ 记忆系统   │  │ 反思与自我纠错模块       │   │
│  │ (Planner) │  │ (Memory)  │  │ (Reflection & Recovery) │   │
│  └───────────┘  └───────────┘  └─────────────────────────┘   │
└─────────────────────────────┬────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                   感知层 (Perception Layer)                   │
│  ┌────────────────┐  ┌───────────────────────────────────┐   │
│  │ 视觉感知 (VLM)  │  │ 结构化感知 (Accessibility Tree)    │   │
│  │ - 截图理解      │  │ - UI 元素树                        │   │
│  │                │  │ - 元素属性、层级关系                │   │
│  └────────────────┘  └───────────────────────────────────┘   │
│                             ↓                                │
│               多模态融合 (Grounding Module)                   │
└─────────────────────────────┬────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                    执行层 (Action Layer)                      │
│         ┌─────────────┐          ┌─────────────┐             │
│         │ 鼠标控制器   │          │ 键盘控制器   │             │
│         └─────────────┘          └─────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

## 安装

### 环境要求

- Python 3.10+
- Windows 10/11（当前仅支持 Windows）
- API 密钥：Anthropic（LLM） 和 OpenAI（VLM）

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

# LLM 驱动模式（推荐）
python -m screen_agent.main --mode llm_driven "打开计算器，计算 123 + 456"

# 交互模式
python -m screen_agent.main -i

# 详细日志
python -m screen_agent.main --verbose "打开浏览器"
```

### GUI 模式

```bash
python run_ui.py
```

### Python API

```python
from screen_agent.agent import ScreenControlAgent
from screen_agent.perception.vlm_client import ClaudeVLMClient
from screen_agent.utils.config import load_config

# 加载配置
config = load_config()

# 创建 VLM 客户端
vlm_client = ClaudeVLMClient(
    api_key=config.anthropic_api_key,
    model="claude-sonnet-4-20250514"
)

# 创建代理
agent = ScreenControlAgent(
    vlm_client=vlm_client,
    max_steps=15,
    verify_each_step=True
)

# 执行任务
success = agent.run("打开记事本并输入 Hello World")
print("成功" if success else "失败")
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `task` | 要执行的任务描述 |
| `-i, --interactive` | 交互模式 |
| `--mode` | 控制器模式：`llm_driven` 或 `vlm_driven` |
| `--provider` | VLM 提供商：`claude` 或 `openai` |
| `--max-steps` | 最大执行步数 |
| `--planning-mode` | 规划模式：`visual_only`、`grounded`、`hybrid` |
| `--no-verify` | 禁用每步验证 |
| `-v, --verbose` | 详细日志 |
| `-c, --config` | 配置文件路径 |

## 规划模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `visual_only` | 纯 VLM 输出坐标 | 简单任务，无需精确定位 |
| `grounded` | VLM + UIAutomation 融合 | 需要精确点击的场景 |
| `hybrid` | 优先 Grounding，失败回退 VLM | 推荐，平衡准确性和兼容性 |

## 项目结构

```
src/screen_agent/
├── agent.py              # 核心智能体
├── main.py               # CLI 入口
├── brain/                # 大脑层
│   ├── planner.py        # 任务规划器
│   ├── verifier.py       # 动作验证器
│   ├── grounding.py      # 多模态融合
│   ├── llm_controller.py # LLM 驱动控制器
│   ├── task_planner.py   # 复杂任务分解
│   └── error_recovery.py # 错误恢复
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

## 路线图

- [x] **Phase 1**: 基础截图 + VLM 调用 + 简单控制
- [x] **Phase 2**: Accessibility Tree 集成 + Grounding 模块
- [x] **Phase 3**: 记忆系统 + 任务分解 + 错误恢复
- [ ] **Phase 4**: 多平台支持（macOS、Linux）
- [ ] **Phase 4**: 浏览器专用通道（CDP）
- [ ] **Phase 4**: API 自动化接口

## 技术栈

| 组件 | 技术 |
|------|------|
| VLM | Claude / GPT-4o |
| LLM | Claude Sonnet (tool_use) |
| 屏幕捕获 | mss |
| UI 自动化 | Windows UIAutomation |
| 鼠标/键盘 | pyautogui |
| GUI | PyQt5 |

## 参考项目

- [ScreenAgent](https://github.com/niuzaisheng/ScreenAgent) - IJCAI 2024
- [Claude Computer Use](https://docs.anthropic.com/en/docs/build-with-claude/computer-use)
- [UI-TARS](https://github.com/nicholaschenai/UI-TARS)

