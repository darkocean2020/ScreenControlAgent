# ScreenControlAgent 架构设计

基于 ScreenAgent (IJCAI 2024) 的改进版本，融合现代 VLM 技术和多模态感知能力。

---

## 原版 ScreenAgent 的局限性

| 问题 | 说明 |
|------|------|
| 模型能力受限 | 当时的 VLM（GPT-4V、CogAgent）在 GUI 理解和坐标定位上精度不足 |
| 单一 VNC 依赖 | VNC 延迟高、画质有损，不适合精细操作 |
| 缺乏结构化理解 | 纯视觉方式，无法获取 UI 元素的语义信息 |
| 反思机制简单 | 反思阶段缺乏记忆和长期规划能力 |
| 错误恢复弱 | 一旦操作失误，难以自我纠正 |

---

## 整体架构

```
┌────────────────────────────────────────────────────────────────┐
│                        用户任务输入                              │
└─────────────────────────────┬──────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                大脑层 (Brain Layer - GPT-5.2 VLM)               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ 任务规划器   │  │ 记忆系统     │  │ 反思与自我纠错模块       │ │
│  │ (Planner)   │  │ (Memory)    │  │ (Reflection & Recovery) │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐                              │
│  │ 技能系统     │  │ 知识库(RAG) │                              │
│  │ (Skills)    │  │ (Knowledge) │                              │
│  └─────────────┘  └─────────────┘                              │
└─────────────────────────────┬──────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                     感知层 (Perception Layer)                   │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐│
│  │ 视觉感知 (VLM)    │  │ 结构化感知 (Accessibility Tree/DOM) ││
│  │ - GPT-5.2/4o     │  │ - Windows UIAutomation              ││
│  └──────────────────┘  └──────────────────────────────────────┘│
│                              ↓                                  │
│              多模态融合 (Grounding Module)                       │
└─────────────────────────────┬──────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                     执行层 (Action Layer)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ 本地控制     │  │ 远程控制    │  │ API/自动化接口          │ │
│  │ (pyautogui) │  │ (VNC/RDP)   │  │ (Browser CDP, AT-SPI)  │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

---

## 各层详细设计

### 1. 大脑层 (Brain Layer)

#### VLM Brain 控制器 (OpenAILLMController)
- 核心中枢，驱动整个代理工作流
- 默认使用 GPT-5.2 作为统一 VLM Brain（同时处理视觉和推理）
- 支持分离架构：感知用 GPT-4o，推理用 Claude Opus
- 使用 function calling 调用工具
- 管理任务状态和执行循环

#### 任务规划器 (TaskPlanner)
- 将复杂任务分解为子任务序列
- 支持动态调整计划（当环境变化时）
- 使用 VLM 评估任务复杂度

#### 记忆系统 (Memory)
- **短期记忆**：当前任务的操作历史、最近观察快照、元素位置缓存
- **长期记忆**：成功的操作模式、任务执行结果（JSON 持久化）
- **情景记忆**：之前类似任务的经验检索

#### 反思与自我纠错 (ReflectionWorkflow)
- 每个子任务完成后验证预期结果是否达成
- 检测异常状态（弹窗、错误提示、卡住）
- 失败后分析原因并自动重试
- 最大重试次数可配置

#### 技能系统 (Skills)
- 预定义的操作序列，提高复杂任务效率
- 内置技能：打开应用、保存文件、导航 URL、新建文档等
- 可扩展的技能注册表

#### 知识库系统 (RAG)
- 存储应用使用指南、UI 交互模式、工作流等知识
- 基于关键词匹配的知识检索
- 支持多种知识类型：APP_GUIDE, UI_PATTERN, WORKFLOW, ERROR_HANDLING, SHORTCUT, TIP

---

### 2. 感知层 (Perception Layer)

这是**最关键的升级点**——从纯视觉走向**视觉 + 结构化信息融合**。

| 感知方式 | 数据来源 | 优势 |
|----------|----------|------|
| 视觉感知 | 屏幕截图 + VLM (GPT-4o/Claude) | 通用性强，能理解任意界面 |
| 结构化感知 | Accessibility Tree (Windows UIAutomation) | 精确的元素坐标、文本、状态 |

#### VLM 客户端
- **OpenAIVLMClient**: 使用 GPT-5.2/GPT-4o，默认选择
- **ClaudeVLMClient**: 使用 Claude Vision（用于分离架构）
- 支持自定义系统提示和关注提示 (focus_hint)

#### UIAutomation 客户端
- 获取 Windows Accessibility Tree
- 支持 24+ 种控件类型
- 缓存机制和最大遍历深度控制

#### Grounding Module（多模态融合）
- 将 VLM 识别的"点击搜索框"映射到具体坐标
- `find_element` 工具：通过名称查找 UI 元素
- `click_element` 工具：直接点击具名元素
- 结合结构化信息验证/校正 VLM 的定位结果

---

### 3. 执行层 (Action Layer)

#### 动作执行器 (ActionExecutor)
- 分发动作到鼠标和键盘控制器
- 支持 8 种动作类型：CLICK, DOUBLE_CLICK, RIGHT_CLICK, TYPE, HOTKEY, SCROLL, MOVE, WAIT

#### 鼠标控制器 (MouseController)
- 基于 pyautogui，增强人类化运动
- 动态计算移动时间（基于距离）
- 添加随机变化，使操作更自然

#### 键盘控制器 (KeyboardController)
- 支持单个按键和组合键
- Unicode 字符支持（中文、日文等）
- 可配置的按键间隔

#### 多通道执行策略

| 场景 | 推荐方式 | 理由 |
|------|----------|------|
| 本地桌面 | pyautogui / pynput | 低延迟、高精度 |
| 远程机器 | VNC / RDP | 跨网络控制 |
| 浏览器任务 | CDP (Chrome DevTools Protocol) | 可直接操作 DOM，更稳定 |
| 特定应用 | 原生 API（如 Office COM） | 避免 UI 操作的不确定性 |

**原则：优先使用高层 API，视觉操作作为兜底**

---

## 工具系统

LLM 通过 function calling 调用以下工具：

| 工具 | 说明 | 使用场景 |
|------|------|---------|
| `look_at_screen` | 调用 VLM 分析屏幕 | 感知当前状态 |
| `click` | 在坐标点击 | 点击按钮、输入框 |
| `double_click` | 双击 | 打开文件、选中文本 |
| `right_click` | 右键点击 | 上下文菜单 |
| `type_text` | 输入文本 | 填表、输入命令 |
| `hotkey` | 快捷键 | Ctrl+C, Alt+Tab 等 |
| `scroll` | 滚动 | 浏览长列表 |
| `find_element` | 通过名称查找 UI 元素 | 获取元素坐标 |
| `click_element` | 直接点击具名元素 | 避免手动坐标 |
| `use_skill` | 调用预定义技能 | 复杂操作序列 |
| `task_complete` | 标记任务完成 | 结束执行 |

---

## 关键改进点总结

| 维度 | 原版 ScreenAgent | 当前实现 |
|------|------------------|----------|
| 感知 | 纯视觉 | 视觉 + Accessibility Tree 融合 |
| 模型 | GPT-4V / CogAgent | GPT-5.2 (统一 VLM Brain) |
| 记忆 | 无 | 短期 + 长期记忆 |
| 规划 | 单步规划 | 层次化任务分解 + 动态调整 |
| 执行 | 仅 VNC | 本地控制 (pyautogui) |
| 容错 | 弱 | 子任务反思 + 自动重试 |
| 技能 | 无 | 预定义技能系统 |
| 知识 | 无 | RAG 知识库 |

---

## 技术选型

| 组件 | 当前使用 |
|------|----------|
| VLM Brain (统一大脑) | GPT-5.2 (OpenAI) - 同时处理视觉和推理 |
| 分离架构 (可选) | 感知: GPT-4o + 推理: Claude Opus |
| 屏幕捕获 | mss |
| 结构化感知 | Windows UIAutomation (comtypes) |
| 鼠标/键盘 | pyautogui, pynput |
| 记忆存储 | JSON 文件 |
| GUI | PyQt5 |
| 配置 | YAML + dotenv |

---

## 项目结构

```
src/screen_agent/
├── main.py                 # CLI 入口点
├── brain/                  # 大脑层
│   ├── openai_controller.py# OpenAI GPT 控制器 (主要，GPT-5.2)
│   ├── llm_controller.py   # Claude LLM 控制器 (备用/分离架构)
│   ├── task_planner.py     # 任务分解器
│   ├── reflection.py       # 反思工作流
│   ├── verifier.py         # 动作验证
│   ├── error_recovery.py   # 错误恢复
│   ├── tools.py            # 工具定义
│   └── prompts.py          # 提示词模板
├── perception/             # 感知层
│   ├── vlm_client.py       # VLM 客户端 (Claude/OpenAI)
│   ├── screen_capture.py   # 屏幕捕获 (mss)
│   └── ui_automation.py    # Windows UIAutomation
├── action/                 # 执行层
│   ├── executor.py         # 动作执行器
│   ├── mouse.py            # 鼠标控制
│   └── keyboard.py         # 键盘控制
├── memory/                 # 记忆系统
│   ├── memory_manager.py   # 统一管理接口
│   ├── short_term.py       # 短期记忆
│   └── long_term.py        # 长期记忆
├── skills/                 # 技能系统
│   ├── skill_base.py       # 技能基类
│   ├── skill_registry.py   # 技能注册表
│   ├── skill_executor.py   # 技能执行器
│   └── builtin_skills.py   # 内置技能
├── rag/                    # 知识检索系统
│   ├── knowledge_store.py  # 知识库存储
│   └── retriever.py        # 知识检索
├── models/                 # 数据模型
│   ├── action.py           # Action, ActionType
│   ├── task.py             # Subtask, TaskPlan
│   └── ui_element.py       # UIElement, ControlType
├── ui/                     # PyQt5 界面
│   ├── main_window.py      # 主窗口
│   ├── floating_overlay.py # 浮动覆盖层
│   └── styles.py           # 样式定义
└── utils/                  # 工具函数
    ├── config.py           # 配置管理
    └── logger.py           # 日志系统
```

---

## 开发进度

### Phase 1: 最小可用版本 ✅
- [x] 基础截图捕获 + VLM 调用
- [x] 简单的鼠标/键盘控制（pyautogui）
- [x] 单步 规划-执行-验证 循环
- [x] 支持单一平台（Windows）

### Phase 2: 增强感知 ✅
- [x] 集成 Accessibility Tree (UIAutomation)
- [x] Grounding 工具 (find_element, click_element)
- [x] VLM 视觉分析

### Phase 3: 智能化 ✅
- [x] 记忆系统（短期 + 长期）
- [x] 多步任务规划 (TaskPlanner)
- [x] 子任务反思验证 (ReflectionWorkflow)
- [x] 技能系统 (Skills)
- [x] 知识库系统 (RAG)

### Phase 4: 扩展 (计划中)
- [ ] 多平台支持 (macOS, Linux)
- [ ] 浏览器专用通道 (CDP)
- [ ] API 自动化接口
- [ ] 向量数据库集成 (Chroma/Qdrant)

---

## 配置说明

主要配置项 (`config/settings.yaml`):

```yaml
# 统一 VLM Brain 模式（默认）
controller:
  mode: "vlm_brain"
  llm:
    model: "gpt-5.2"    # 统一 VLM Brain，同时处理视觉和推理
    max_tokens: 4096

# VLM 设置（用于 look_at_screen 工具）
vlm:
  provider: "openai"
  openai:
    model: "gpt-4o"

grounding:
  enabled: true
  mode: "hybrid"        # visual_only, grounded, hybrid

memory:
  enabled: true
  long_term_storage: "data/memory.json"

task_planning:
  enabled: true
  auto_decompose: true

# 分离架构模式（可选）- 感知和推理使用不同模型
separated_arch:
  enabled: true
  perception_provider: "openai"    # VLM 感知: GPT-4o
  perception_model: "gpt-4o"
  reasoning_provider: "claude"     # LLM 推理: Claude Opus
  reasoning_model: "claude-opus-4-20250514"
```
