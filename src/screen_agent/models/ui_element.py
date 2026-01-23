"""UI Element data structures for Accessibility Tree integration."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Tuple, Dict, Any
from difflib import SequenceMatcher


class ControlType(Enum):
    """Windows UI Automation control types."""
    BUTTON = "Button"
    EDIT = "Edit"
    TEXT = "Text"
    LIST = "List"
    LIST_ITEM = "ListItem"
    MENU = "Menu"
    MENU_ITEM = "MenuItem"
    MENU_BAR = "MenuBar"
    COMBO_BOX = "ComboBox"
    TAB = "Tab"
    TAB_ITEM = "TabItem"
    TREE = "Tree"
    TREE_ITEM = "TreeItem"
    CHECK_BOX = "CheckBox"
    RADIO_BUTTON = "RadioButton"
    HYPERLINK = "Hyperlink"
    IMAGE = "Image"
    TOOLBAR = "ToolBar"
    STATUS_BAR = "StatusBar"
    WINDOW = "Window"
    PANE = "Pane"
    GROUP = "Group"
    DOCUMENT = "Document"
    CUSTOM = "Custom"
    UNKNOWN = "Unknown"


@dataclass
class BoundingRect:
    """Bounding rectangle for a UI element."""
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> Tuple[int, int]:
        """Get center point of the rectangle."""
        return (
            self.left + self.width // 2,
            self.top + self.height // 2
        )

    def contains_point(self, x: int, y: int) -> bool:
        """Check if a point is within this rectangle."""
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def to_dict(self) -> Dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height
        }


@dataclass
class UIElement:
    """Represents a UI element from the Accessibility Tree."""
    name: str
    control_type: ControlType
    automation_id: str = ""
    class_name: str = ""
    bounding_rect: Optional[BoundingRect] = None
    is_enabled: bool = True
    is_visible: bool = True
    is_focusable: bool = False
    has_keyboard_focus: bool = False
    parent_name: str = ""
    parent_type: Optional[ControlType] = None
    depth: int = 0
    child_count: int = 0
    value: str = ""
    help_text: str = ""
    children: List["UIElement"] = field(default_factory=list)
    _handle: Any = field(default=None, repr=False)

    @property
    def center(self) -> Optional[Tuple[int, int]]:
        """Get center coordinates for clicking."""
        if self.bounding_rect:
            return self.bounding_rect.center
        return None

    @property
    def clickable_point(self) -> Optional[Tuple[int, int]]:
        """Get the best point to click on this element."""
        return self.center

    def matches_description(self, description: str) -> float:
        """Calculate how well this element matches a text description."""
        description_lower = description.lower()
        score = 0.0

        if self.name:
            name_lower = self.name.lower()
            if name_lower == description_lower:
                score += 0.5
            elif description_lower in name_lower or name_lower in description_lower:
                score += 0.3

        type_keywords = {
            ControlType.BUTTON: ["button", "btn", "click"],
            ControlType.EDIT: ["input", "text", "field", "textbox", "edit", "search"],
            ControlType.MENU_ITEM: ["menu", "option"],
            ControlType.HYPERLINK: ["link", "url"],
            ControlType.CHECK_BOX: ["checkbox", "check"],
            ControlType.LIST_ITEM: ["item", "option", "result"],
        }
        for ctrl_type, keywords in type_keywords.items():
            if self.control_type == ctrl_type:
                if any(kw in description_lower for kw in keywords):
                    score += 0.2
                break

        return min(score, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "control_type": self.control_type.value,
            "automation_id": self.automation_id,
            "bounding_rect": self.bounding_rect.to_dict() if self.bounding_rect else None,
            "is_enabled": self.is_enabled,
            "is_visible": self.is_visible,
            "depth": self.depth,
            "value": self.value[:100] if self.value else "",
        }

    def __str__(self) -> str:
        rect_str = f"@{self.bounding_rect.center}" if self.bounding_rect else ""
        return f"{self.control_type.value}['{self.name}']{rect_str}"


@dataclass
class UIElementTree:
    """Container for the UI element tree with query capabilities."""
    root: Optional[UIElement] = None
    all_elements: List[UIElement] = field(default_factory=list)
    timestamp: float = 0.0

    def find_by_name(self, name: str, partial: bool = True) -> List[UIElement]:
        """Find elements by name."""
        name_lower = name.lower()
        if partial:
            return [e for e in self.all_elements
                    if e.name and name_lower in e.name.lower()]
        return [e for e in self.all_elements
                if e.name and e.name.lower() == name_lower]

    def find_by_type(self, control_type: ControlType) -> List[UIElement]:
        """Find elements by control type."""
        return [e for e in self.all_elements if e.control_type == control_type]

    def find_by_automation_id(self, automation_id: str) -> Optional[UIElement]:
        """Find element by automation ID."""
        for e in self.all_elements:
            if e.automation_id == automation_id:
                return e
        return None

    def find_clickable(self) -> List[UIElement]:
        """Find all clickable elements."""
        clickable_types = {
            ControlType.BUTTON, ControlType.HYPERLINK, ControlType.MENU_ITEM,
            ControlType.LIST_ITEM, ControlType.TAB_ITEM, ControlType.TREE_ITEM,
            ControlType.CHECK_BOX, ControlType.RADIO_BUTTON
        }
        return [e for e in self.all_elements
                if e.control_type in clickable_types
                and e.is_enabled and e.is_visible and e.bounding_rect]

    def find_at_point(self, x: int, y: int) -> List[UIElement]:
        """Find elements at a specific point, ordered by depth."""
        matches = [e for e in self.all_elements
                   if e.bounding_rect and e.bounding_rect.contains_point(x, y)]
        return sorted(matches, key=lambda e: e.depth, reverse=True)

    def find_near_point(self, x: int, y: int, radius: int = 50) -> List[UIElement]:
        """Find elements near a point within a radius."""
        results = []
        for e in self.all_elements:
            if not e.bounding_rect:
                continue
            cx, cy = e.bounding_rect.center
            distance = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
            if distance <= radius:
                results.append((e, distance))
        return [e for e, _ in sorted(results, key=lambda x: x[1])]

    def to_text_representation(self, max_elements: int = 80) -> str:
        """Create a text representation for VLM context."""
        lines = []
        visible_elements = [e for e in self.all_elements
                           if e.is_visible and e.bounding_rect and e.name]

        prioritized = sorted(visible_elements,
                            key=lambda e: (e.is_enabled, e.is_focusable),
                            reverse=True)[:max_elements]

        for i, elem in enumerate(prioritized):
            rect = elem.bounding_rect
            line = f"[{i}] {elem.control_type.value}: \"{elem.name}\" at ({rect.center[0]}, {rect.center[1]})"
            if elem.value:
                line += f" value=\"{elem.value[:30]}\""
            lines.append(line)

        return "\n".join(lines)
