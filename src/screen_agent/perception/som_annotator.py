"""Set-of-Mark screenshot annotator.

Draws numbered marks on interactive elements in a screenshot so the VLM
can reference elements by number instead of guessing pixel coordinates.
"""

from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from ..models.som_element import SoMElement

# 10 high-contrast colors for mark badges (cycled)
MARK_COLORS = [
    (220, 50, 50),    # red
    (50, 100, 220),   # blue
    (40, 180, 60),    # green
    (230, 140, 20),   # orange
    (150, 50, 200),   # purple
    (20, 180, 200),   # cyan
    (200, 50, 150),   # magenta
    (100, 180, 40),   # lime
    (200, 180, 30),   # yellow
    (220, 100, 130),  # pink
]


class SoMAnnotator:
    """Draws Set-of-Mark annotations on screenshots."""

    def __init__(
        self,
        max_marks: int = 40,
        min_element_size: int = 8,
        outline_width: int = 2,
    ):
        self.max_marks = max_marks
        self.min_element_size = min_element_size
        self.outline_width = outline_width
        self._font = self._load_font()

    def _load_font(self) -> ImageFont.FreeTypeFont:
        """Load a font for mark numbers, falling back to default."""
        for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, 13)
            except (IOError, OSError):
                continue
        return ImageFont.load_default()

    def annotate(
        self,
        screenshot: Image.Image,
        elements: List[SoMElement],
    ) -> Tuple[Image.Image, Dict[int, SoMElement]]:
        """Draw marks on screenshot and return annotated image + mapping.

        Args:
            screenshot: PIL Image of the screen
            elements: Interactive elements to mark

        Returns:
            (annotated_image, mark_map) where mark_map is {mark_id: SoMElement}
        """
        filtered = self._filter_elements(elements, screenshot.size)

        # Assign sequential mark IDs
        for idx, elem in enumerate(filtered):
            elem.mark_id = idx + 1

        # Draw on a copy
        annotated = screenshot.copy()
        overlay = Image.new("RGBA", annotated.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        for elem in filtered:
            color = MARK_COLORS[(elem.mark_id - 1) % len(MARK_COLORS)]
            self._draw_mark(overlay_draw, elem, color)

        # Composite overlay onto screenshot
        if annotated.mode != "RGBA":
            annotated = annotated.convert("RGBA")
        annotated = Image.alpha_composite(annotated, overlay)
        annotated = annotated.convert("RGB")

        mark_map = {e.mark_id: e for e in filtered}
        return annotated, mark_map

    def _filter_elements(
        self,
        elements: List[SoMElement],
        screen_size: Tuple[int, int],
    ) -> List[SoMElement]:
        """Filter and limit elements for annotation."""
        sw, sh = screen_size
        result = []

        for elem in elements:
            r = elem.bounding_rect
            # Skip too small
            if r.width < self.min_element_size or r.height < self.min_element_size:
                continue
            # Skip off-screen
            if r.right < 0 or r.bottom < 0 or r.left > sw or r.top > sh:
                continue
            # Skip disabled/invisible
            if not elem.is_enabled or not elem.is_visible:
                continue
            result.append(elem)

        # Sort by position (top-to-bottom, left-to-right) for intuitive numbering
        result.sort(key=lambda e: (e.bounding_rect.top, e.bounding_rect.left))

        # Cap at max
        return result[:self.max_marks]

    def _draw_mark(
        self,
        draw: ImageDraw.ImageDraw,
        elem: SoMElement,
        color: Tuple[int, int, int],
    ) -> None:
        """Draw a single mark: outline around element + numbered badge."""
        r = elem.bounding_rect

        # Draw outline around element (semi-transparent)
        outline_color = (*color, 150)
        for i in range(self.outline_width):
            draw.rectangle(
                [r.left - i, r.top - i, r.right + i, r.bottom + i],
                outline=outline_color,
            )

        # Draw badge with number at top-left corner
        label = str(elem.mark_id)
        bbox = self._font.getbbox(label)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        pad_x, pad_y = 4, 2
        badge_w = text_w + pad_x * 2
        badge_h = text_h + pad_y * 2

        # Position badge at top-left of element, nudge inside if needed
        bx = max(0, r.left)
        by = max(0, r.top - badge_h)

        # Badge background
        badge_color = (*color, 220)
        draw.rectangle([bx, by, bx + badge_w, by + badge_h], fill=badge_color)

        # Badge text
        draw.text(
            (bx + pad_x, by + pad_y - bbox[1]),
            label,
            fill=(255, 255, 255, 255),
            font=self._font,
        )
