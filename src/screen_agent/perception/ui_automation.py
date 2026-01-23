"""Windows UI Automation wrapper for Accessibility Tree access."""

import time
import ctypes
from typing import Optional, List, Callable, Any

from ..models.ui_element import (
    UIElement, UIElementTree, BoundingRect, ControlType
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


# Control type mapping from UIAutomation constants
CONTROL_TYPE_MAP = {
    50000: ControlType.BUTTON,
    50001: ControlType.PANE,       # Calendar
    50002: ControlType.CHECK_BOX,
    50003: ControlType.COMBO_BOX,
    50004: ControlType.EDIT,
    50005: ControlType.HYPERLINK,
    50006: ControlType.IMAGE,
    50007: ControlType.LIST_ITEM,
    50008: ControlType.LIST,
    50009: ControlType.MENU,
    50010: ControlType.MENU_BAR,
    50011: ControlType.MENU_ITEM,
    50012: ControlType.PANE,       # ProgressBar
    50013: ControlType.RADIO_BUTTON,
    50014: ControlType.PANE,       # ScrollBar
    50015: ControlType.PANE,       # Slider
    50016: ControlType.PANE,       # Spinner
    50017: ControlType.STATUS_BAR,
    50018: ControlType.TAB,
    50019: ControlType.TAB_ITEM,
    50020: ControlType.TEXT,
    50021: ControlType.TOOLBAR,
    50022: ControlType.PANE,       # ToolTip
    50023: ControlType.TREE,
    50024: ControlType.TREE_ITEM,
    50025: ControlType.CUSTOM,
    50026: ControlType.GROUP,
    50027: ControlType.PANE,       # Thumb
    50028: ControlType.PANE,       # DataGrid
    50029: ControlType.PANE,       # DataItem
    50030: ControlType.DOCUMENT,
    50031: ControlType.PANE,       # SplitButton
    50032: ControlType.WINDOW,
    50033: ControlType.PANE,
}


class UIAutomationClient:
    """
    Windows UI Automation client for extracting the Accessibility Tree.

    Uses comtypes to access the Windows UIAutomation COM interface.
    """

    def __init__(
        self,
        max_depth: int = 10,
        timeout: float = 5.0,
        cache_duration: float = 0.5
    ):
        """
        Initialize UI Automation client.

        Args:
            max_depth: Maximum tree traversal depth
            timeout: Timeout for automation operations
            cache_duration: How long to cache the element tree
        """
        self.max_depth = max_depth
        self.timeout = timeout
        self.cache_duration = cache_duration

        self._uia = None
        self._root = None
        self._last_tree: Optional[UIElementTree] = None
        self._last_tree_time: float = 0
        self._initialized = False

        self._initialize()

    def _initialize(self) -> None:
        """Initialize COM and UIAutomation."""
        try:
            import comtypes
            import comtypes.client

            # Initialize COM
            ctypes.windll.ole32.CoInitialize(None)

            # Generate and import the UIAutomation type library
            # CUIAutomation CLSID: FF48DBA4-60EF-4201-AA87-54103EEF594E
            # IUIAutomation interface ID: 30CBE57D-D9D0-452A-AB13-7AC5AC4825EE
            try:
                # Try to import pre-generated module
                from comtypes.gen import UIAutomationClient as UIA
            except ImportError:
                # Generate from type library
                comtypes.client.GetModule("UIAutomationCore.dll")
                from comtypes.gen import UIAutomationClient as UIA

            # Create UIAutomation instance with correct interface
            self._uia = comtypes.client.CreateObject(
                UIA.CUIAutomation,
                interface=UIA.IUIAutomation
            )

            self._root = self._uia.GetRootElement()
            self._initialized = True
            logger.info("UIAutomation initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize UIAutomation: {e}")
            self._initialized = False

    def is_available(self) -> bool:
        """Check if UIAutomation is available."""
        return self._initialized and self._uia is not None

    def get_element_tree(
        self,
        window_name: Optional[str] = None,
        force_refresh: bool = False
    ) -> UIElementTree:
        """
        Get the current UI element tree.

        Args:
            window_name: Optional window name to filter to
            force_refresh: Force refresh even if cache is valid

        Returns:
            UIElementTree containing accessible elements
        """
        if not self.is_available():
            logger.warning("UIAutomation not available, returning empty tree")
            return UIElementTree(timestamp=time.time())

        current_time = time.time()

        # Return cached if valid
        if (not force_refresh and
            self._last_tree and
            current_time - self._last_tree_time < self.cache_duration):
            return self._last_tree

        logger.debug("Building UI element tree...")
        start_time = time.time()

        try:
            if window_name:
                root_element = self._find_window(window_name)
            else:
                root_element = self._get_foreground_window()

            if not root_element:
                root_element = self._root

            tree = UIElementTree(timestamp=current_time)
            tree.root = self._build_element(root_element, depth=0)
            tree.all_elements = self._flatten_tree(tree.root)

            self._last_tree = tree
            self._last_tree_time = current_time

            elapsed = time.time() - start_time
            logger.debug(
                f"Built tree with {len(tree.all_elements)} elements "
                f"in {elapsed:.3f}s"
            )

            return tree

        except Exception as e:
            logger.error(f"Failed to get element tree: {e}")
            return UIElementTree(timestamp=current_time)

    def _get_foreground_window(self) -> Any:
        """Get the foreground window element."""
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            try:
                return self._uia.ElementFromHandle(hwnd)
            except Exception:
                pass
        return self._root

    def _find_window(self, name: str) -> Any:
        """Find a window by name."""
        try:
            condition = self._uia.CreatePropertyCondition(
                30005,  # UIA_NamePropertyId
                name
            )
            element = self._root.FindFirst(4, condition)  # TreeScope_Children
            return element
        except Exception:
            return None

    def _build_element(
        self,
        uia_element: Any,
        depth: int,
        parent_name: str = "",
        parent_type: Optional[ControlType] = None
    ) -> Optional[UIElement]:
        """Build UIElement from UIAutomation element."""
        if depth > self.max_depth:
            return None

        try:
            name = uia_element.CurrentName or ""
            control_type_id = uia_element.CurrentControlType
            control_type = CONTROL_TYPE_MAP.get(control_type_id, ControlType.UNKNOWN)

            # Get bounding rectangle
            rect = uia_element.CurrentBoundingRectangle
            bounding_rect = None
            if rect:
                # Check for valid rectangle
                left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
                if right > left and bottom > top and left > -10000 and top > -10000:
                    bounding_rect = BoundingRect(
                        left=left, top=top, right=right, bottom=bottom
                    )

            # Skip invisible elements without bounds at deeper levels
            if not bounding_rect and depth > 2:
                return None

            element = UIElement(
                name=name,
                control_type=control_type,
                automation_id=uia_element.CurrentAutomationId or "",
                class_name=uia_element.CurrentClassName or "",
                bounding_rect=bounding_rect,
                is_enabled=bool(uia_element.CurrentIsEnabled),
                is_visible=not bool(uia_element.CurrentIsOffscreen),
                is_focusable=bool(uia_element.CurrentIsKeyboardFocusable),
                has_keyboard_focus=bool(uia_element.CurrentHasKeyboardFocus),
                parent_name=parent_name,
                parent_type=parent_type,
                depth=depth,
                _handle=uia_element
            )

            # Get value for edit controls
            if control_type in (ControlType.EDIT, ControlType.COMBO_BOX):
                try:
                    value_pattern = uia_element.GetCurrentPatternAs(10002, None)
                    if value_pattern:
                        element.value = value_pattern.CurrentValue or ""
                except Exception:
                    pass

            # Get children (limited)
            try:
                true_condition = self._uia.CreateTrueCondition()
                child_array = uia_element.FindAll(2, true_condition)  # TreeScope_Children
                element.child_count = child_array.Length

                for i in range(min(child_array.Length, 50)):  # Limit children
                    try:
                        child_elem = child_array.GetElement(i)
                        child = self._build_element(
                            child_elem,
                            depth + 1,
                            parent_name=name,
                            parent_type=control_type
                        )
                        if child:
                            element.children.append(child)
                    except Exception:
                        continue
            except Exception:
                pass

            return element

        except Exception as e:
            logger.debug(f"Error building element at depth {depth}: {e}")
            return None

    def _flatten_tree(self, root: Optional[UIElement]) -> List[UIElement]:
        """Flatten the element tree into a list."""
        if not root:
            return []

        result = [root]
        for child in root.children:
            result.extend(self._flatten_tree(child))
        return result

    def get_element_at_point(self, x: int, y: int) -> Optional[UIElement]:
        """Get the element at a specific screen point."""
        if not self.is_available():
            return None

        try:
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = POINT(x, y)
            uia_element = self._uia.ElementFromPoint(pt)

            if uia_element:
                return self._build_element(uia_element, depth=0)
            return None

        except Exception as e:
            logger.error(f"Failed to get element at point ({x}, {y}): {e}")
            return None

    def get_focused_element(self) -> Optional[UIElement]:
        """Get the currently focused element."""
        if not self.is_available():
            return None

        try:
            focused = self._uia.GetFocusedElement()
            if focused:
                return self._build_element(focused, depth=0)
            return None
        except Exception as e:
            logger.error(f"Failed to get focused element: {e}")
            return None

    def wait_for_element(
        self,
        condition: Callable[[UIElement], bool],
        timeout: float = 5.0,
        poll_interval: float = 0.2
    ) -> Optional[UIElement]:
        """Wait for an element matching a condition to appear."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            tree = self.get_element_tree(force_refresh=True)

            for element in tree.all_elements:
                if condition(element):
                    return element

            time.sleep(poll_interval)

        return None
