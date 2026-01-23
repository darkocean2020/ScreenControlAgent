"""Grounding module for matching VLM element descriptions to UI elements."""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional, List, Tuple, Dict, Any

from ..models.ui_element import UIElement, UIElementTree, ControlType
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GroundingResult:
    """Result of element grounding."""
    element: Optional[UIElement]
    confidence: float
    match_method: str
    candidates: List[Tuple[UIElement, float]] = field(default_factory=list)
    coordinates: Optional[Tuple[int, int]] = None

    @property
    def success(self) -> bool:
        return self.element is not None and self.confidence > 0.3

    def __str__(self) -> str:
        if self.element:
            return f"Grounded to {self.element} (confidence={self.confidence:.2f})"
        return f"Grounding failed (candidates: {len(self.candidates)})"


@dataclass
class ElementDescription:
    """Structured description of a target element from VLM."""
    name: Optional[str] = None
    text_content: Optional[str] = None
    control_type: Optional[str] = None
    parent_description: Optional[str] = None
    relative_position: Optional[str] = None
    approximate_coords: Optional[Tuple[int, int]] = None
    additional_context: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ElementDescription":
        """Create from dictionary (VLM response)."""
        coords = None
        if "approximate_coordinates" in data:
            c = data["approximate_coordinates"]
            if isinstance(c, list) and len(c) >= 2:
                coords = (int(c[0]), int(c[1]))

        return cls(
            name=data.get("name") or data.get("element_name"),
            text_content=data.get("text") or data.get("label"),
            control_type=data.get("type") or data.get("control_type"),
            parent_description=data.get("parent") or data.get("container"),
            relative_position=data.get("position") or data.get("location"),
            approximate_coords=coords,
            additional_context=data.get("context") or data.get("description")
        )


class ElementGrounder:
    """Grounds VLM element descriptions to actual UI elements."""

    TYPE_KEYWORDS = {
        ControlType.BUTTON: ["button", "btn", "click", "press"],
        ControlType.EDIT: ["input", "textbox", "text field", "edit", "search box", "search bar", "field"],
        ControlType.HYPERLINK: ["link", "hyperlink", "url"],
        ControlType.CHECK_BOX: ["checkbox", "check box", "toggle"],
        ControlType.RADIO_BUTTON: ["radio", "option button"],
        ControlType.COMBO_BOX: ["dropdown", "combo box", "select", "combobox"],
        ControlType.LIST_ITEM: ["list item", "item", "option", "result", "search result"],
        ControlType.MENU_ITEM: ["menu item", "menu option", "menu"],
        ControlType.TAB_ITEM: ["tab"],
        ControlType.TREE_ITEM: ["tree item", "folder"],
        ControlType.TEXT: ["text", "label"],
    }

    def __init__(
        self,
        name_match_threshold: float = 0.5,
        spatial_weight: float = 0.3,
        type_match_bonus: float = 0.15,
        min_confidence: float = 0.3
    ):
        """Initialize the grounding module."""
        self.name_match_threshold = name_match_threshold
        self.spatial_weight = spatial_weight
        self.type_match_bonus = type_match_bonus
        self.min_confidence = min_confidence

    def ground(
        self,
        description: ElementDescription,
        ui_tree: UIElementTree,
        screen_size: Tuple[int, int] = (1920, 1080)
    ) -> GroundingResult:
        """Ground an element description to a UI element."""
        logger.debug(f"Grounding: name='{description.name}', type='{description.control_type}'")

        candidates: List[Tuple[UIElement, float, str]] = []

        # Filter to visible, enabled elements with bounds
        eligible = [
            e for e in ui_tree.all_elements
            if e.is_visible and e.bounding_rect and e.is_enabled
        ]

        for element in eligible:
            score, method = self._score_element(element, description, screen_size)
            if score > 0.1:
                candidates.append((element, score, method))

        candidates.sort(key=lambda x: x[1], reverse=True)

        if not candidates:
            logger.warning("No candidates found for grounding")
            # Fallback to spatial search if we have coordinates
            if description.approximate_coords:
                return self.ground_by_coordinates(
                    description.approximate_coords, ui_tree
                )
            return GroundingResult(
                element=None,
                confidence=0.0,
                match_method="none",
                candidates=[]
            )

        best_element, best_score, best_method = candidates[0]

        if best_score < self.min_confidence:
            logger.warning(f"Best match {best_score:.2f} below threshold")
            # Try spatial fallback
            if description.approximate_coords:
                spatial_result = self.ground_by_coordinates(
                    description.approximate_coords, ui_tree
                )
                if spatial_result.success:
                    return spatial_result

            return GroundingResult(
                element=None,
                confidence=best_score,
                match_method=best_method,
                candidates=[(e, s) for e, s, _ in candidates[:5]]
            )

        logger.info(f"Grounded: {best_element} (score={best_score:.2f})")

        return GroundingResult(
            element=best_element,
            confidence=best_score,
            match_method=best_method,
            candidates=[(e, s) for e, s, _ in candidates[1:6]],
            coordinates=best_element.clickable_point
        )

    def _score_element(
        self,
        element: UIElement,
        description: ElementDescription,
        screen_size: Tuple[int, int]
    ) -> Tuple[float, str]:
        """Score how well an element matches the description."""
        score = 0.0
        method_parts = []

        # 1. Name matching
        if description.name:
            name_score = self._name_similarity(element.name, description.name)
            if name_score > self.name_match_threshold:
                score += name_score * 0.5
                method_parts.append(f"name({name_score:.2f})")

            if element.value:
                value_score = self._name_similarity(element.value, description.name)
                if value_score > self.name_match_threshold:
                    score += value_score * 0.3
                    method_parts.append(f"value({value_score:.2f})")

        # 2. Text content matching
        if description.text_content:
            text_score = self._name_similarity(element.name, description.text_content)
            score += text_score * 0.4
            if text_score > 0.5:
                method_parts.append(f"text({text_score:.2f})")

        # 3. Control type matching
        if description.control_type:
            if self._type_matches(element.control_type, description.control_type):
                score += self.type_match_bonus
                method_parts.append("type")

        # 4. Spatial proximity
        if description.approximate_coords and element.bounding_rect:
            target_x, target_y = description.approximate_coords
            elem_x, elem_y = element.bounding_rect.center

            max_dist = (screen_size[0]**2 + screen_size[1]**2) ** 0.5
            distance = ((target_x - elem_x)**2 + (target_y - elem_y)**2) ** 0.5
            proximity_score = 1.0 - min(distance / max_dist, 1.0)

            if proximity_score > 0.7:
                score += proximity_score * self.spatial_weight
                method_parts.append(f"spatial({proximity_score:.2f})")

        # 5. Parent context
        if description.parent_description and element.parent_name:
            parent_score = self._name_similarity(
                element.parent_name, description.parent_description
            )
            if parent_score > 0.5:
                score += parent_score * 0.1
                method_parts.append(f"parent({parent_score:.2f})")

        method = "+".join(method_parts) if method_parts else "none"
        return score, method

    def _name_similarity(self, s1: str, s2: str) -> float:
        """Calculate similarity between two strings."""
        if not s1 or not s2:
            return 0.0

        s1_lower = s1.lower().strip()
        s2_lower = s2.lower().strip()

        if s1_lower == s2_lower:
            return 1.0

        if s1_lower in s2_lower or s2_lower in s1_lower:
            return 0.8

        return SequenceMatcher(None, s1_lower, s2_lower).ratio()

    def _type_matches(self, element_type: ControlType, described_type: str) -> bool:
        """Check if described type matches element control type."""
        described_lower = described_type.lower()

        if element_type.value.lower() in described_lower:
            return True

        for ctrl_type, keywords in self.TYPE_KEYWORDS.items():
            if ctrl_type == element_type:
                return any(kw in described_lower for kw in keywords)

        return False

    def ground_by_coordinates(
        self,
        approximate_coords: Tuple[int, int],
        ui_tree: UIElementTree,
        radius: int = 150
    ) -> GroundingResult:
        """Ground using only approximate coordinates (fallback)."""
        x, y = approximate_coords

        nearby = ui_tree.find_near_point(x, y, radius=radius)
        clickable = [e for e in nearby if e.is_enabled and e.bounding_rect]

        if not clickable:
            return GroundingResult(
                element=None,
                confidence=0.0,
                match_method="spatial_fallback",
                candidates=[]
            )

        best = clickable[0]
        cx, cy = best.bounding_rect.center
        distance = ((cx - x)**2 + (cy - y)**2) ** 0.5
        confidence = max(0.0, 1.0 - distance / radius)

        return GroundingResult(
            element=best,
            confidence=confidence,
            match_method="spatial_fallback",
            candidates=[(e, 0.5) for e in clickable[1:4]],
            coordinates=best.clickable_point
        )
