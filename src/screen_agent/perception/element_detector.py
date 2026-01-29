"""Hybrid element detector combining UIAutomation and Chrome CDP.

Uses a tiered approach:
  - Tier 1: UIAutomation (fast, works for native Windows apps)
  - Tier 2: Chrome CDP (for web page elements UIAutomation can't see)

Returns a unified list of SoMElement for the SoM annotator.
"""

import logging
from typing import Any, List, Optional

from ..models.som_element import SoMElement

logger = logging.getLogger(__name__)


class HybridElementDetector:
    """Detect interactive elements from multiple sources."""

    def __init__(
        self,
        uia_client: Optional[Any] = None,
        cdp_client: Optional[Any] = None,
        uia_min_elements: int = 3,
    ):
        """
        Args:
            uia_client: Windows UIAutomation client instance
            cdp_client: Chrome CDP client instance
            uia_min_elements: Minimum UIA elements to consider sufficient
                              (below this, CDP is also queried)
        """
        self.uia_client = uia_client
        self.cdp_client = cdp_client
        self.uia_min_elements = uia_min_elements

    def detect(self) -> List[SoMElement]:
        """Detect interactive elements from all available sources.

        Strategy:
        1. Always try UIAutomation first (native app elements)
        2. If Chrome CDP is available and UIA found few elements,
           also query CDP for web page elements
        3. Merge results, deduplicating overlapping elements

        Returns:
            Unified list of SoMElement
        """
        uia_elements = self._detect_uia()
        cdp_elements = self._detect_cdp()

        if not cdp_elements:
            return uia_elements

        if not uia_elements:
            return cdp_elements

        # Merge: UIA elements first, then CDP elements that don't overlap
        merged = list(uia_elements)
        for cdp_elem in cdp_elements:
            if not self._overlaps_any(cdp_elem, uia_elements):
                merged.append(cdp_elem)

        logger.info(
            f"HybridDetector: {len(uia_elements)} UIA + "
            f"{len(merged) - len(uia_elements)} CDP = {len(merged)} total"
        )
        return merged

    def _detect_uia(self) -> List[SoMElement]:
        """Detect elements via UIAutomation."""
        if not self.uia_client or not self.uia_client.is_available():
            return []

        try:
            ui_tree = self.uia_client.get_element_tree()
            clickable = ui_tree.find_clickable()

            elements = []
            for elem in clickable:
                if elem.bounding_rect:
                    elements.append(SoMElement(
                        mark_id=0,
                        name=elem.name or "",
                        element_type=str(elem.control_type),
                        bounding_rect=elem.bounding_rect,
                        source="uia",
                        is_enabled=elem.is_enabled,
                        is_visible=elem.is_visible,
                    ))

            logger.info(f"UIA: Found {len(elements)} clickable elements")
            return elements

        except Exception as e:
            logger.warning(f"UIA element detection failed: {e}")
            return []

    def _detect_cdp(self) -> List[SoMElement]:
        """Detect elements via Chrome DevTools Protocol."""
        if not self.cdp_client:
            return []

        try:
            if not self.cdp_client.is_available():
                return []
            return self.cdp_client.get_interactive_elements()
        except Exception as e:
            logger.warning(f"CDP element detection failed: {e}")
            return []

    @staticmethod
    def _overlaps_any(
        elem: SoMElement,
        others: List[SoMElement],
        iou_threshold: float = 0.5,
    ) -> bool:
        """Check if elem significantly overlaps with any element in others."""
        r1 = elem.bounding_rect
        for other in others:
            r2 = other.bounding_rect

            # Compute intersection
            ix_left = max(r1.left, r2.left)
            iy_top = max(r1.top, r2.top)
            ix_right = min(r1.right, r2.right)
            iy_bottom = min(r1.bottom, r2.bottom)

            if ix_right <= ix_left or iy_bottom <= iy_top:
                continue  # no intersection

            intersection = (ix_right - ix_left) * (iy_bottom - iy_top)
            area1 = max(1, r1.width * r1.height)
            area2 = max(1, r2.width * r2.height)
            union = area1 + area2 - intersection
            iou = intersection / max(1, union)

            if iou >= iou_threshold:
                return True

        return False
