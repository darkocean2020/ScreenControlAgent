"""Knowledge store for RAG system.

Stores and manages knowledge entries that can be retrieved to augment
the agent's understanding of applications, UI patterns, and workflows.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum

from ..utils.logger import get_logger

logger = get_logger(__name__)


class KnowledgeType(Enum):
    """Types of knowledge entries."""
    APP_GUIDE = "app_guide"          # How to use an application
    UI_PATTERN = "ui_pattern"        # Common UI patterns and how to interact
    WORKFLOW = "workflow"            # Multi-step workflow guide
    ERROR_HANDLING = "error_handling" # How to handle errors/dialogs
    SHORTCUT = "shortcut"            # Keyboard shortcuts
    TIP = "tip"                      # General tips and tricks


@dataclass
class KnowledgeEntry:
    """A single knowledge entry."""
    id: str
    title: str
    content: str
    knowledge_type: KnowledgeType
    tags: List[str] = field(default_factory=list)
    app_name: Optional[str] = None  # Associated application
    keywords: List[str] = field(default_factory=list)  # For keyword matching
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    usage_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["knowledge_type"] = self.knowledge_type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeEntry":
        """Create from dictionary."""
        data = data.copy()
        data["knowledge_type"] = KnowledgeType(data["knowledge_type"])
        return cls(**data)

    def matches(self, query: str) -> float:
        """Calculate simple keyword-based relevance score (0-1)."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        score = 0.0

        # Title match (high weight)
        if query_lower in self.title.lower():
            score += 0.4

        # Keyword match
        matched_keywords = sum(1 for kw in self.keywords if kw.lower() in query_lower)
        if self.keywords:
            score += 0.3 * (matched_keywords / len(self.keywords))

        # Tag match
        matched_tags = sum(1 for tag in self.tags if tag.lower() in query_lower)
        if self.tags:
            score += 0.2 * (matched_tags / len(self.tags))

        # App name match
        if self.app_name and self.app_name.lower() in query_lower:
            score += 0.1

        # Content word overlap
        content_words = set(self.content.lower().split())
        overlap = len(query_words & content_words)
        if query_words:
            score += 0.1 * min(1.0, overlap / len(query_words))

        return min(1.0, score)


class KnowledgeStore:
    """
    Storage and retrieval system for knowledge entries.

    Provides simple keyword-based retrieval. Can be extended with
    vector embeddings for semantic search.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize knowledge store.

        Args:
            storage_path: Path to JSON file for persistent storage
        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.entries: Dict[str, KnowledgeEntry] = {}

        if self.storage_path and self.storage_path.exists():
            self._load()
        else:
            self._load_default_knowledge()

    def _load(self) -> None:
        """Load knowledge from storage file."""
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for entry_data in data.get("entries", []):
                entry = KnowledgeEntry.from_dict(entry_data)
                self.entries[entry.id] = entry

            logger.info(f"Loaded {len(self.entries)} knowledge entries")
        except Exception as e:
            logger.error(f"Failed to load knowledge store: {e}")
            self._load_default_knowledge()

    def _save(self) -> None:
        """Save knowledge to storage file."""
        if not self.storage_path:
            return

        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "version": "1.0",
                "entries": [entry.to_dict() for entry in self.entries.values()]
            }

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Saved {len(self.entries)} knowledge entries")
        except Exception as e:
            logger.error(f"Failed to save knowledge store: {e}")

    def _load_default_knowledge(self) -> None:
        """Load default built-in knowledge."""
        default_entries = [
            # Notepad knowledge
            KnowledgeEntry(
                id="notepad_save",
                title="记事本保存文件",
                content="""在记事本中保存文件的步骤：
1. 按 Ctrl+S 打开保存对话框
2. 如果是新文件，会弹出"另存为"对话框
3. 在"文件名"输入框中输入文件名（包含.txt扩展名）
4. 点击"保存"按钮或按 Enter 键
5. 如果文件已存在，会询问是否替换，选择"是"确认替换

常见问题：
- 如果"保存"按钮点击无效，尝试使用 Enter 键
- 确保文件名输入框已获得焦点再输入""",
                knowledge_type=KnowledgeType.APP_GUIDE,
                tags=["notepad", "记事本", "保存", "save"],
                app_name="Notepad",
                keywords=["保存", "save", "记事本", "notepad", "文件", "ctrl+s"]
            ),
            KnowledgeEntry(
                id="notepad_new",
                title="记事本新建文件",
                content="""在记事本中新建文件：
1. 按 Ctrl+N 新建空白文档
2. 如果当前文档有未保存的更改，会询问是否保存
3. 选择"不保存"跳过，或"保存"先保存当前文件
4. 新的空白文档会打开，状态栏显示"0 个字符"

提示：始终在新文档中工作，避免覆盖已有内容""",
                knowledge_type=KnowledgeType.APP_GUIDE,
                tags=["notepad", "记事本", "新建", "new"],
                app_name="Notepad",
                keywords=["新建", "new", "记事本", "notepad", "ctrl+n", "空白"]
            ),

            # Windows common dialogs
            KnowledgeEntry(
                id="windows_save_dialog",
                title="Windows 保存对话框操作",
                content="""Windows "另存为/保存" 对话框的操作方法：
1. 对话框通常包含：文件夹导航区、文件列表、文件名输入框、保存按钮
2. 文件名输入框：直接输入文件名，包含扩展名
3. 保存按钮：通常在右下角，标签为"保存(S)"或"Save"
4. 如果保存按钮点击不准，使用 find_element("保存") 获取精确坐标
5. 也可以输入完文件名后直接按 Enter 键保存

常见元素名称（用于 find_element）：
- 保存按钮: "保存", "Save", "保存(S)"
- 取消按钮: "取消", "Cancel"
- 文件名输入框: "文件名", "File name" """,
                knowledge_type=KnowledgeType.UI_PATTERN,
                tags=["windows", "dialog", "save", "保存"],
                keywords=["保存", "对话框", "文件名", "save", "dialog"]
            ),
            KnowledgeEntry(
                id="windows_confirm_replace",
                title="Windows 文件替换确认对话框",
                content="""当保存文件时遇到同名文件，会弹出确认对话框：
- 对话框标题通常为"确认另存为"
- 提示文本："xxx 已存在。要替换它吗？"
- 按钮：
  - "是(Y)" - 确认替换
  - "否(N)" - 取消保存

操作方法：
1. 使用 find_element("是") 查找确认按钮
2. 使用 click_element("是") 点击确认
3. 或者直接按 hotkey(["y"]) 快捷键""",
                knowledge_type=KnowledgeType.UI_PATTERN,
                tags=["windows", "dialog", "confirm", "replace"],
                keywords=["替换", "确认", "已存在", "replace", "confirm"]
            ),

            # Chrome / Browser
            KnowledgeEntry(
                id="chrome_navigation",
                title="Chrome 浏览器导航",
                content="""Chrome 浏览器导航操作：
1. 打开地址栏：按 Ctrl+L 或 F6 选中地址栏
2. 输入网址后按 Enter 导航
3. 新建标签页：Ctrl+T
4. 关闭标签页：Ctrl+W
5. 刷新页面：Ctrl+R 或 F5

注意：
- 地址栏元素名称可能是 "Address and search bar" 或 "地址栏"
- 使用快捷键 Ctrl+L 比点击地址栏更可靠""",
                knowledge_type=KnowledgeType.APP_GUIDE,
                tags=["chrome", "browser", "navigation"],
                app_name="Chrome",
                keywords=["chrome", "浏览器", "地址栏", "导航", "网址", "url"]
            ),
            KnowledgeEntry(
                id="chrome_profile_select",
                title="Chrome 配置文件选择",
                content="""Chrome 启动时可能显示配置文件选择界面：
- 标题："Who's using Chrome?" 或 "谁在使用 Chrome?"
- 显示多个用户配置文件
- 点击要使用的配置文件即可进入

操作方法：
1. 使用 find_element 查找配置文件按钮
2. 通常按钮名称包含 "profile" 或用户名
3. 点击后等待浏览器主界面加载""",
                knowledge_type=KnowledgeType.UI_PATTERN,
                tags=["chrome", "profile", "选择"],
                app_name="Chrome",
                keywords=["chrome", "profile", "配置文件", "用户", "选择"]
            ),

            # Google Drive / Docs
            KnowledgeEntry(
                id="google_drive_new_doc",
                title="Google Drive 创建新文档",
                content="""在 Google Drive 中创建新 Google Doc：

方法1 - 通过 Drive 界面：
1. 打开 drive.google.com
2. 点击左上角 "+ New/新建" 按钮
3. 在下拉菜单中选择 "Google Docs/Google 文档"
4. 选择 "Blank document/空白文档"

方法2 - 直接 URL（更可靠）：
1. 在地址栏输入 docs.google.com/document
2. 按 Enter 进入 Google Docs 主页
3. 点击 "Blank/空白" 模板创建新文档

方法3 - 快捷方式：
- 直接访问 docs.new 会创建新文档

注意：Google Drive 是网页应用，UI 元素可能无法通过 UIAutomation 找到""",
                knowledge_type=KnowledgeType.WORKFLOW,
                tags=["google", "drive", "docs", "document", "新建"],
                app_name="Chrome",
                keywords=["google", "drive", "docs", "文档", "新建", "create"]
            ),

            # Windows shortcuts
            KnowledgeEntry(
                id="windows_app_shortcuts",
                title="Windows 常用快捷键",
                content="""Windows 系统常用快捷键：
- Win: 打开开始菜单
- Win+D: 显示桌面
- Win+E: 打开文件资源管理器
- Win+R: 打开运行对话框
- Alt+Tab: 切换窗口
- Alt+F4: 关闭当前窗口（谨慎使用）
- Ctrl+Shift+Esc: 打开任务管理器

应用内通用：
- Ctrl+S: 保存
- Ctrl+N: 新建
- Ctrl+O: 打开
- Ctrl+Z: 撤销
- Ctrl+Y: 重做
- Ctrl+A: 全选
- Ctrl+C: 复制
- Ctrl+V: 粘贴
- Ctrl+X: 剪切""",
                knowledge_type=KnowledgeType.SHORTCUT,
                tags=["windows", "shortcut", "快捷键"],
                keywords=["快捷键", "shortcut", "ctrl", "alt", "win"]
            ),

            # Tips
            KnowledgeEntry(
                id="tip_element_not_found",
                title="找不到 UI 元素的解决方法",
                content="""当 find_element/click_element 找不到元素时：

1. 尝试不同的名称：
   - 使用部分名称匹配
   - 尝试中文/英文版本
   - 查看 look_at_screen 返回的元素列表

2. 使用坐标点击：
   - 从 look_at_screen 结果估计坐标
   - 使用 click(x, y) 直接点击

3. 使用快捷键替代：
   - 很多按钮有快捷键（如 Enter 确认，Escape 取消）
   - 查看按钮文字中的下划线字母

4. 网页应用特殊处理：
   - 网页元素可能不在 Accessibility Tree 中
   - 依赖视觉定位或快捷键""",
                knowledge_type=KnowledgeType.TIP,
                tags=["troubleshooting", "element", "找不到"],
                keywords=["找不到", "元素", "not found", "element", "失败"]
            ),
        ]

        for entry in default_entries:
            self.entries[entry.id] = entry

        logger.info(f"Loaded {len(default_entries)} default knowledge entries")

    def add(self, entry: KnowledgeEntry) -> None:
        """Add a knowledge entry."""
        self.entries[entry.id] = entry
        self._save()
        logger.debug(f"Added knowledge entry: {entry.id}")

    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        """Get a knowledge entry by ID."""
        return self.entries.get(entry_id)

    def remove(self, entry_id: str) -> bool:
        """Remove a knowledge entry."""
        if entry_id in self.entries:
            del self.entries[entry_id]
            self._save()
            return True
        return False

    def search(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.1,
        knowledge_type: Optional[KnowledgeType] = None,
        app_name: Optional[str] = None
    ) -> List[KnowledgeEntry]:
        """
        Search for relevant knowledge entries.

        Args:
            query: Search query
            top_k: Maximum number of results
            min_score: Minimum relevance score
            knowledge_type: Filter by knowledge type
            app_name: Filter by application name

        Returns:
            List of relevant knowledge entries, sorted by relevance
        """
        results = []

        for entry in self.entries.values():
            # Apply filters
            if knowledge_type and entry.knowledge_type != knowledge_type:
                continue
            if app_name and entry.app_name and entry.app_name.lower() != app_name.lower():
                continue

            score = entry.matches(query)
            if score >= min_score:
                results.append((score, entry))

        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)

        # Update usage count and return top-k
        top_entries = [entry for _, entry in results[:top_k]]
        for entry in top_entries:
            entry.usage_count += 1

        if top_entries:
            self._save()

        return top_entries

    def get_all(self) -> List[KnowledgeEntry]:
        """Get all knowledge entries."""
        return list(self.entries.values())

    def get_by_app(self, app_name: str) -> List[KnowledgeEntry]:
        """Get all knowledge entries for a specific application."""
        return [
            entry for entry in self.entries.values()
            if entry.app_name and entry.app_name.lower() == app_name.lower()
        ]

    def get_by_type(self, knowledge_type: KnowledgeType) -> List[KnowledgeEntry]:
        """Get all knowledge entries of a specific type."""
        return [
            entry for entry in self.entries.values()
            if entry.knowledge_type == knowledge_type
        ]
