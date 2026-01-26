# ScreenControlAgent

基于 VLM 的智能屏幕控制代理，能够理解自然语言指令并自动操作计算机完成任务。

> 目前仅支持 Windows 10/11，建议使用 1080p 显示屏。

## 特性

- **自然语言控制** - 用自然语言描述任务，代理自动执行
- **GPT-5.2 驱动** - 统一 VLM Brain，同时处理视觉理解和决策推理
- **多模态感知** - 视觉 (VLM) + 结构化信息 (Accessibility Tree) 融合
- **智能规划（Decompose Tasks）** - 支持复杂任务分解、多步规划
- **子任务反思(Reflection Workflow)** - 每个子任务完成后验证，失败自动重试
- **记忆系统(Memory)** - 短期 + 长期记忆，从历史经验中学习
- **技能系统（Skills）** - 预定义操作序列，高效完成常见任务
- **知识库 (RAG)** - 存储应用指南、UI 模式等知识

## 前言

这是一个简单的AI Hackanthon的项目，我们认为Claude Code这样的Agent的强大之处之一在于“本地”和“接口”，将手深入电脑，可以赋予的动作范围急速扩大，所以我们做了一个能够控制鼠标和键盘的ScreenControlAgent，尝试实现无API无接口场景的自动化。

在尝试不同VLM作为agent的大脑的时候，不同参数的LLM/VLM对屏幕识别，规划任务，操作精确度都有很大影响。Chatgpt-4O是参数很高的VLM，但是思考仍然有局限性，比如玩扫雷会打开Steam等等。而Chatgpt-5.2无论是决策还是速度都有很高的效率。

我们也尝试过"VLM+LLM双大脑"(VLM为眼睛，输入json给LLM)，以及“LLM为大脑，VLM为工具”，到最后还是选择回来VLM为大脑。虽然“LLM为大脑，VLM为工具”效率最快，尤其是处理有接口的任务的时候，但是处理没有接口的任务或需要图像识别的任务时，仍然有些图像元素捕捉非常不精确。

这个Agent的局限性仍然很大，需要更多数据集， 目前RAG可以补齐“硬知识”，Skills可以补上一些“方法论”。但要创造出更加精确和智能的Agent，仍然需要创建数据飞轮来对VLM进行微调，要继续发展，仍然需要强化学习(Reinforcement Learning)。
  

## 希望解决的痛点

### 无API/MCP的自动化
现状痛点：
很多系统没有 API，或者：

老旧系统（银行核心系统、ERP、政务系统）
第三方 SaaS 平台不开放接口
跨系统操作需要人工复制粘贴

典型场景：
场景具体痛点财务对账从银行网银导出流水 → 粘贴到 Excel → 与 ERP 核对HR 入职在 5-6 个系统中重复录入新员工信息客服工单从工单系统复制信息 → 查 CRM → 查订单系统 → 回复报表汇总登录多个平台导出数据 → 手动整合
价值： 一个能操作任意界面的 Agent 可以打通这些"信息孤岛"

### 传统 RPA 的困境
现状痛点：
传统 RPA（UiPath、Blue Prism 等）依赖精确的元素选择器（XPath、CSS Selector）
界面稍有变动（按钮换位置、文字改了）就会失效
需要专业开发人员维护，成本高
每个流程都要单独开发，无法泛化

AI Agent 的用处：
基于视觉理解，像人一样"看"界面，不依赖底层代码
界面小改动不影响执行
用自然语言描述任务，非技术人员也能用

### 软件测试自动化
现状痛点：
UI 测试脚本维护成本极高（界面改了就要改脚本）
测试用例编写需要开发能力
探索性测试很难自动化

AI Agent 的用处：
用自然语言描述测试场景："登录后检查余额是否显示正确"
自动适应界面变化
可以做智能探索测试（随机操作找 bug）

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
### 反思系统（Reflection Workflow）
如果每一次调用工具都需要反思，这个Agent将会执行的非常慢，所以我们都是每一次SubTask子任务完成或者失败的时候进行反思。
```
  ┌─────────────────────────────────────────────────────────────────┐
  │                    执行子任务 (Subtask)                          │
  └─────────────────────────────┬───────────────────────────────────┘
                                ↓                                                                                      
                      ┌─────────┴─────────┐
                      │  completed &&     │
                      │  confidence > 0.7 │
                      └─────────┬─────────┘
                       Yes ↓         ↓ No                                                                             
                ┌──────────┐    ┌──────────────────────────────────┐
                │ 子任务完成 │    │     反思阶段 (reflect_on_failure) │
                │ 继续下一个 │    │  ┌────────────────────────────┐  │
                └──────────┘    │  │ 分析:                       │  │
                                │  │   - 失败的根本原因           │  │
                                │  │   - 参考相似成功案例         │  │
                                │  │   - 生成替代方案             │  │
                                │  │   - 判断是否应该重试         │  │
                                │  └────────────────────────────┘  │
                                └─────────────┬────────────────────┘
                                              ↓                                                                        
                                    ┌─────────┴─────────┐
                                    │ should_retry &&   │
                                    │ attempts < max(2) │
                                    └─────────┬─────────┘
                                     Yes ↓         ↓ No                                                               
                              ┌────────────┐  ┌────────────┐
                              │ 使用替代方案 │  │ 子任务失败  │
                              │ 重新执行    │  │ 记录到记忆  │
                              └──────┬─────┘  └────────────┘
                                     │
                                     └──→ 回到"执行子任务" 
```


### 记忆系统 (Memory System)
有短期记忆和长期记忆系统。短期记忆缓存当前会话的元素位置和失败操作避免重复错误，长期记忆持久化历史任务的成功模式和失败模式供相似任务来检索参考。
```
  ┌─────────────────────────────────────────────────────────────────────────┐                                             
  │─────────────────────────MemoryManager─(统一接口)─────────────────────────│
  │  ┌───────────────────────────────┐  ┌─────────────────────────────────┐ │                                             
  │  │      ShortTermMemory          │  │       LongTermMemory            │ │
  │  │         (短期记忆)             │  │         (长期记忆)               │ │
  │  │                               │  │                                 │ │
  │  │  ┌─────────────────────────┐  │  │  ┌───────────────────────────┐  │ │
  │  │  │ ContextWindow           │  │  │  │ TaskRecords               │  │ │
  │  │  │ 最近 10 个操作上下文     │  │  │  │ 任务执行历史 (max 500)    │  │ │
  │  │  └─────────────────────────┘  │  │  └───────────────────────────┘  │ │
  │  │                               │  │                                 │ │
  │  │  ┌─────────────────────────┐  │  │  ┌───────────────────────────┐  │ │
  │  │  │ ElementCache (LRU)      │  │  │  │ Patterns                  │  │ │
  │  │  │ 元素位置缓存             │  │  │  │ 成功模式 (按任务类型)      │  │ │
  │  │  │ TTL: 300s, Max: 100     │  │  │  └───────────────────────────┘  │ │
  │  │  └─────────────────────────┘  │  │                                 │ │
  │  │                               │  │  ┌───────────────────────────┐  │ │
  │  │  ┌─────────────────────────┐  │  │  │ Failures                  │  │ │
  │  │  │ FailedActions           │  │  │  │ 失败模式 (按动作类型)      │  │ │
  │  │  │ 失败操作记录 (避免重复)  │  │  │  └───────────────────────────┘  │ │
  │  │  └─────────────────────────┘  │  │                                 │ │
  │  │                               │  │         持久化存储              │ │
  │  │       会话内有效              │  │      data/memory.json           │ │
  │  └───────────────────────────────┘  └─────────────────────────────────┘ │
  └─────────────────────────────────────────────────────────────────────────┘
```

```
    任务开始
      │
      ├── start_session(task)
      │       └── 清空短期记忆，初始化会话
      │
      ↓                                                                                                                
  ┌───────────────────────────────────────┐
  │           规划阶段                     │
  │  get_context_for_planning(task)       │
  │    ├── 检索相似历史任务                │
  │    ├── 获取成功模式                   │
  │    ├── 获取失败操作列表               │
  │    └── 获取元素位置缓存               │
  └───────────────────────────────────────┘
      │
      ↓                                                                                                                
  ┌───────────────────────────────────────┐
  │           执行阶段                     │
  │  update_after_action(action, ...)     │
  │    ├── 更新上下文窗口                 │
  │    ├── 缓存成功的元素位置             │
  │    └── 记录失败的操作                 │
  └───────────────────────────────────────┘
      │
      ↓                                                                                                                
  任务结束
      │
      └── save_session(success, patterns)
              ├── 创建 TaskRecord
              ├── 提取成功模式
              ├── 记录失败模式
              └── 持久化到 JSON
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

