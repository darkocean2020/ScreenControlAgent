"""Data model for Set-of-Mark (SoM) annotated elements."""

from dataclasses import dataclass
from typing import Tuple

from .ui_element import BoundingRect


@dataclass
class SoMElement:
    """An interactive element detected for Set-of-Mark annotation."""
    mark_id: int
    name: str
    element_type: str  # "Button", "Link", "Input", etc.
    bounding_rect: BoundingRect
    source: str  # "uia", "cdp"
    is_enabled: bool = True
    is_visible: bool = True

    @property
    def center(self) -> Tuple[int, int]:
        return self.bounding_rect.center

    def __str__(self) -> str:
        cx, cy = self.center
        return f"[{self.mark_id}] {self.element_type}: \"{self.name}\" at ({cx}, {cy})"
