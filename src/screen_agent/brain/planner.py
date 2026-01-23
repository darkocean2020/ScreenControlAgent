"""Task planner that uses VLM to determine next actions."""

import json
import re
from typing import Tuple, Optional

from ..models.action import Action, ActionType, AgentState
from ..perception.vlm_client import VLMClient
from ..utils.logger import get_logger
from .prompts import PLANNING_SYSTEM_PROMPT, PLANNING_USER_PROMPT

logger = get_logger(__name__)


class Planner:
    """Plans next actions based on screen state and task."""

    def __init__(self, vlm_client: VLMClient):
        """
        Initialize the planner.

        Args:
            vlm_client: VLM client for analyzing screenshots
        """
        self.vlm_client = vlm_client

    def plan_next_action(self, state: AgentState) -> Tuple[Action, str]:
        """
        Plan the next action based on current state.

        Args:
            state: Current agent state including screenshot and history

        Returns:
            Tuple of (Action object, raw VLM response)
        """
        history_str = self._format_action_history(state.get_recent_history())

        user_prompt = PLANNING_USER_PROMPT.format(
            task=state.current_task,
            action_history=history_str or "None yet"
        )

        logger.debug("Calling VLM for action planning...")
        response = self.vlm_client.analyze_screen(
            screenshot=state.screenshot,
            prompt=user_prompt,
            system_prompt=PLANNING_SYSTEM_PROMPT
        )
        logger.debug(f"VLM response: {response[:200]}...")

        action = self._parse_action_response(response)
        return action, response

    def _format_action_history(self, history: list) -> str:
        """Format action history for the prompt."""
        if not history:
            return ""
        lines = []
        for i, action in enumerate(history, 1):
            lines.append(f"{i}. {str(action)}")
        return "\n".join(lines)

    def _parse_action_response(self, response: str) -> Action:
        """
        Parse VLM response into an Action object.

        Args:
            response: Raw VLM response text

        Returns:
            Parsed Action object
        """
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
