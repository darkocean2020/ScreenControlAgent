"""Task planner that uses VLM to determine next actions."""

import json
import re
from enum import Enum
from typing import Tuple, Optional, Any

from ..models.action import Action, ActionType, AgentState
from ..models.ui_element import UIElementTree
from ..perception.vlm_client import VLMClient, LLMClient
from ..utils.logger import get_logger
from .prompts import (
    PLANNING_SYSTEM_PROMPT,
    PLANNING_USER_PROMPT,
    GROUNDED_PLANNING_SYSTEM_PROMPT,
    GROUNDED_PLANNING_USER_PROMPT,
    # Separated architecture prompts
    PERCEPTION_SYSTEM_PROMPT,
    PERCEPTION_USER_PROMPT,
    REASONING_SYSTEM_PROMPT,
    REASONING_USER_PROMPT
)
from .grounding import ElementGrounder, ElementDescription, GroundingResult

logger = get_logger(__name__)


class PlanningMode(Enum):
    """Planning mode for coordinate determination."""
    VISUAL_ONLY = "visual_only"
    GROUNDED = "grounded"
    HYBRID = "hybrid"
    SEPARATED = "separated"  # VLM for perception, LLM for reasoning


class Planner:
    """Plans next actions based on screen state and task."""

    def __init__(
        self,
        vlm_client: VLMClient,
        mode: PlanningMode = PlanningMode.HYBRID,
        uia_client: Any = None,
        grounding_confidence_threshold: float = 0.4,
        llm_client: Optional[LLMClient] = None
    ):
        """
        Initialize the planner.

        Args:
            vlm_client: VLM client for analyzing screenshots
            mode: Planning mode (visual_only, grounded, hybrid, or separated)
            uia_client: UIAutomation client (optional, created if needed)
            grounding_confidence_threshold: Minimum confidence for grounded coords
            llm_client: LLM client for reasoning (required for separated mode)
        """
        self.vlm_client = vlm_client
        self.llm_client = llm_client
        self.mode = mode
        self.grounding_threshold = grounding_confidence_threshold

        # Validate separated mode has LLM client
        if mode == PlanningMode.SEPARATED and llm_client is None:
            logger.warning("Separated mode requires llm_client, falling back to hybrid")
            self.mode = PlanningMode.HYBRID

        # Initialize UIAutomation for grounded/hybrid/separated modes
        self.uia_client = None
        self.grounder = None

        if mode in (PlanningMode.GROUNDED, PlanningMode.HYBRID, PlanningMode.SEPARATED):
            if uia_client:
                self.uia_client = uia_client
            else:
                try:
                    from ..perception.ui_automation import UIAutomationClient
                    self.uia_client = UIAutomationClient()
                except Exception as e:
                    logger.warning(f"Failed to initialize UIAutomation: {e}")
                    if mode == PlanningMode.GROUNDED:
                        raise
                    # For hybrid/separated mode, fall back to visual_only
                    if mode == PlanningMode.SEPARATED:
                        logger.warning("UIAutomation failed, separated mode falling back to visual_only")
                    self.mode = PlanningMode.VISUAL_ONLY

            if self.uia_client:
                self.grounder = ElementGrounder()

    def plan_next_action(
        self,
        state: AgentState,
        screen_size: Tuple[int, int] = None
    ) -> Tuple[Action, str]:
        """
        Plan the next action based on current state.

        Args:
            state: Current agent state including screenshot and history
            screen_size: Tuple of (width, height) for the screen

        Returns:
            Tuple of (Action object, raw VLM response)
        """
        history_str = self._format_action_history(state.get_recent_history())

        if screen_size is None and state.screenshot:
            screen_size = state.screenshot.size
        screen_width, screen_height = screen_size or (1920, 1080)

        if self.mode == PlanningMode.VISUAL_ONLY:
            return self._plan_visual_only(state, history_str, screen_width, screen_height)
        elif self.mode == PlanningMode.GROUNDED:
            return self._plan_grounded(state, history_str, screen_width, screen_height)
        elif self.mode == PlanningMode.SEPARATED:
            return self._plan_separated(state, history_str, screen_width, screen_height)
        else:  # HYBRID
            return self._plan_hybrid(state, history_str, screen_width, screen_height)

    def _plan_visual_only(
        self,
        state: AgentState,
        history_str: str,
        screen_width: int,
        screen_height: int
    ) -> Tuple[Action, str]:
        """Original visual-only planning."""
        user_prompt = PLANNING_USER_PROMPT.format(
            task=state.current_task,
            action_history=history_str or "None yet",
            screen_width=screen_width,
            screen_height=screen_height
        )

        logger.debug("Planning (visual-only mode)...")
        response = self.vlm_client.analyze_screen(
            screenshot=state.screenshot,
            prompt=user_prompt,
            system_prompt=PLANNING_SYSTEM_PROMPT
        )
        logger.debug(f"VLM response: {response[:200]}...")

        action = self._parse_action_response(response)
        return action, response

    def _plan_grounded(
        self,
        state: AgentState,
        history_str: str,
        screen_width: int,
        screen_height: int
    ) -> Tuple[Action, str]:
        """Grounded planning: VLM describes element, grounding provides coordinates."""
        # Get UI element tree
        ui_tree = self.uia_client.get_element_tree()
        element_context = ui_tree.to_text_representation(max_elements=80)

        user_prompt = GROUNDED_PLANNING_USER_PROMPT.format(
            task=state.current_task,
            action_history=history_str or "None yet",
            screen_width=screen_width,
            screen_height=screen_height,
            element_list=element_context if element_context else "No elements detected"
        )

        logger.debug("Planning (grounded mode)...")
        response = self.vlm_client.analyze_screen(
            screenshot=state.screenshot,
            prompt=user_prompt,
            system_prompt=GROUNDED_PLANNING_SYSTEM_PROMPT
        )
        logger.debug(f"VLM response: {response[:200]}...")

        action, element_desc = self._parse_grounded_response(response)

        # If action requires coordinates, ground the element
        if action.action_type in (
            ActionType.CLICK, ActionType.DOUBLE_CLICK,
            ActionType.RIGHT_CLICK, ActionType.MOVE
        ):
            grounding_result = self.grounder.ground(
                element_desc, ui_tree, (screen_width, screen_height)
            )

            if grounding_result.success:
                action.coordinates = grounding_result.coordinates
                action.target_element_name = element_desc.name
                action.grounding_confidence = grounding_result.confidence
                logger.info(
                    f"Grounded to {grounding_result.coordinates} "
                    f"(confidence={grounding_result.confidence:.2f})"
                )
            else:
                # Use VLM's approximate coordinates
                if element_desc.approximate_coords:
                    action.coordinates = element_desc.approximate_coords
                    action.grounding_confidence = 0.0
                    logger.warning(
                        f"Grounding failed, using VLM coords: {action.coordinates}"
                    )
                else:
                    raise ValueError("Grounding failed and no fallback coordinates")

        return action, response

    def _plan_hybrid(
        self,
        state: AgentState,
        history_str: str,
        screen_width: int,
        screen_height: int
    ) -> Tuple[Action, str]:
        """Hybrid: try grounded first, fall back to visual if low confidence."""
        try:
            action, response = self._plan_grounded(
                state, history_str, screen_width, screen_height
            )

            # Check confidence
            if (action.grounding_confidence is not None and
                action.grounding_confidence < self.grounding_threshold):
                logger.warning(
                    f"Low grounding confidence ({action.grounding_confidence:.2f}), "
                    f"falling back to visual"
                )
                return self._plan_visual_only(
                    state, history_str, screen_width, screen_height
                )

            return action, response

        except Exception as e:
            logger.warning(f"Grounded planning failed: {e}, falling back to visual")
            return self._plan_visual_only(
                state, history_str, screen_width, screen_height
            )

    def _plan_separated(
        self,
        state: AgentState,
        history_str: str,
        screen_width: int,
        screen_height: int
    ) -> Tuple[Action, str]:
        """
        Separated planning: VLM for perception, LLM for reasoning.

        This approach:
        1. VLM (fast/cheap) extracts visual information from screenshot
        2. UIAutomation provides element coordinates
        3. LLM (powerful) reasons about action to take
        """
        # Phase 1: VLM Perception - extract visual information
        logger.debug("Phase 1: VLM Perception...")
        perception_prompt = PERCEPTION_USER_PROMPT.format(
            task=state.current_task,
            screen_width=screen_width,
            screen_height=screen_height
        )

        perception_response = self.vlm_client.analyze_screen(
            screenshot=state.screenshot,
            prompt=perception_prompt,
            system_prompt=PERCEPTION_SYSTEM_PROMPT
        )
        logger.debug(f"Perception response: {perception_response[:200]}...")

        # Phase 2: Get UI element tree from Accessibility Tree
        element_context = ""
        ui_tree = None
        if self.uia_client:
            ui_tree = self.uia_client.get_element_tree()
            element_context = ui_tree.to_text_representation(max_elements=80)

        # Phase 3: LLM Reasoning - decide action based on perception + elements
        logger.debug("Phase 2: LLM Reasoning...")
        reasoning_prompt = REASONING_USER_PROMPT.format(
            task=state.current_task,
            perception_data=perception_response,
            element_list=element_context if element_context else "No elements detected",
            action_history=history_str or "None yet",
            screen_width=screen_width,
            screen_height=screen_height
        )

        reasoning_response = self.llm_client.reason(
            prompt=reasoning_prompt,
            system_prompt=REASONING_SYSTEM_PROMPT
        )
        logger.debug(f"Reasoning response: {reasoning_response[:200]}...")

        # Parse action and element description from reasoning response
        action, element_desc = self._parse_grounded_response(reasoning_response)

        # Phase 4: Ground element to get precise coordinates
        if action.action_type in (
            ActionType.CLICK, ActionType.DOUBLE_CLICK,
            ActionType.RIGHT_CLICK, ActionType.MOVE
        ) and ui_tree:
            grounding_result = self.grounder.ground(
                element_desc, ui_tree, (screen_width, screen_height)
            )

            if grounding_result.success:
                action.coordinates = grounding_result.coordinates
                action.target_element_name = element_desc.name
                action.grounding_confidence = grounding_result.confidence
                logger.info(
                    f"Grounded to {grounding_result.coordinates} "
                    f"(confidence={grounding_result.confidence:.2f})"
                )
            else:
                # Use approximate coordinates from LLM response
                if element_desc.approximate_coords:
                    action.coordinates = element_desc.approximate_coords
                    action.grounding_confidence = 0.0
                    logger.warning(
                        f"Grounding failed, using LLM coords: {action.coordinates}"
                    )
                else:
                    raise ValueError("Grounding failed and no fallback coordinates")

        # Combine responses for callback (perception + reasoning)
        combined_response = json.dumps({
            "perception": perception_response,
            "reasoning": reasoning_response,
            "observation": self._extract_observation(perception_response),
            "action": {
                "type": action.action_type.value,
                "coordinates": list(action.coordinates) if action.coordinates else None,
                "text": action.text,
                "keys": action.keys
            }
        }, ensure_ascii=False)

        return action, combined_response

    def _extract_observation(self, perception_response: str) -> str:
        """Extract observation text from perception response."""
        try:
            json_match = re.search(r'\{[\s\S]*\}', perception_response)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("screen_state", perception_response[:200])
        except:
            pass
        return perception_response[:200]

    def _format_action_history(self, history: list) -> str:
        """Format action history for the prompt."""
        if not history:
            return ""
        lines = []
        for i, action in enumerate(history, 1):
            lines.append(f"{i}. {str(action)}")
        return "\n".join(lines)

    def _parse_action_response(self, response: str) -> Action:
        """Parse VLM response into an Action object (visual mode)."""
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            raise ValueError(f"No JSON found in response: {response[:200]}")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in response: {e}")

        action_data = data.get("action", {})
        action_type_str = action_data.get("type", "").lower()

        if action_type_str == "done":
            return Action(
                action_type=ActionType.DONE,
                description="Task completed"
            )

        type_mapping = {
            "click": ActionType.CLICK,
            "double_click": ActionType.DOUBLE_CLICK,
            "right_click": ActionType.RIGHT_CLICK,
            "type": ActionType.TYPE,
            "hotkey": ActionType.HOTKEY,
            "scroll": ActionType.SCROLL,
            "move": ActionType.MOVE,
            "wait": ActionType.WAIT,
        }

        action_type = type_mapping.get(action_type_str)
        if not action_type:
            raise ValueError(f"Unknown action type: {action_type_str}")

        coordinates = None
        if "coordinates" in action_data:
            coords = action_data["coordinates"]
            if isinstance(coords, list) and len(coords) >= 2:
                coordinates = (int(coords[0]), int(coords[1]))

        return Action(
            action_type=action_type,
            coordinates=coordinates,
            text=action_data.get("text"),
            keys=action_data.get("keys"),
            scroll_amount=action_data.get("scroll_amount"),
            duration=action_data.get("duration"),
            description=data.get("reasoning", "")
        )

    def _parse_grounded_response(
        self,
        response: str
    ) -> Tuple[Action, ElementDescription]:
        """Parse VLM response with element description for grounding."""
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            raise ValueError(f"No JSON found in response: {response[:200]}")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in response: {e}")

        # Parse action
        action_data = data.get("action", {})
        action_type_str = action_data.get("type", "").lower()

        if action_type_str == "done":
            return Action(
                action_type=ActionType.DONE,
                description="Task completed"
            ), ElementDescription()

        type_mapping = {
            "click": ActionType.CLICK,
            "double_click": ActionType.DOUBLE_CLICK,
            "right_click": ActionType.RIGHT_CLICK,
            "type": ActionType.TYPE,
            "hotkey": ActionType.HOTKEY,
            "scroll": ActionType.SCROLL,
            "move": ActionType.MOVE,
            "wait": ActionType.WAIT,
        }

        action_type = type_mapping.get(action_type_str)
        if not action_type:
            raise ValueError(f"Unknown action type: {action_type_str}")

        action = Action(
            action_type=action_type,
            coordinates=None,
            text=action_data.get("text"),
            keys=action_data.get("keys"),
            scroll_amount=action_data.get("scroll_amount"),
            duration=action_data.get("duration"),
            description=data.get("reasoning", "")
        )

        # Parse element description
        target_data = data.get("target_element", {})
        element_desc = ElementDescription.from_dict(target_data)

        return action, element_desc
