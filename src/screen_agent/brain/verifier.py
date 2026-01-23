"""Action verifier that checks execution results."""

import json
import re
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from ..perception.vlm_client import VLMClient
from ..utils.logger import get_logger
from .prompts import VERIFY_SYSTEM_PROMPT, VERIFY_USER_PROMPT

logger = get_logger(__name__)


@dataclass
class VerificationResult:
    """Result of action verification."""
    action_successful: bool
    task_completed: bool
    observation: str
    issues: Optional[str] = None


class Verifier:
    """Verifies action execution results using VLM."""

    def __init__(self, vlm_client: VLMClient):
        """
        Initialize the verifier.

        Args:
            vlm_client: VLM client for analyzing screenshots
        """
        self.vlm_client = vlm_client

    def verify_action(
        self,
        screenshot: Image.Image,
        task: str,
        action_description: str
    ) -> VerificationResult:
        """
        Verify if an action was successful.

        Args:
            screenshot: Screenshot taken after the action
            task: Original task description
            action_description: Description of the action taken

        Returns:
            VerificationResult with success status and observations
        """
        user_prompt = VERIFY_USER_PROMPT.format(
            task=task,
            action_description=action_description
        )

        logger.debug("Calling VLM for verification...")
        response = self.vlm_client.analyze_screen(
            screenshot=screenshot,
            prompt=user_prompt,
            system_prompt=VERIFY_SYSTEM_PROMPT
        )
        logger.debug(f"Verification response: {response[:200]}...")

        return self._parse_verification_response(response)

    def _parse_verification_response(self, response: str) -> VerificationResult:
        """
        Parse VLM response into VerificationResult.

        Args:
            response: Raw VLM response text

        Returns:
            Parsed VerificationResult
        """
        json_match = re.search(r'\{[\s\S]*\}', response)

        if not json_match:
            logger.warning("No JSON in verification response, using heuristics")
            response_lower = response.lower()
            return VerificationResult(
                action_successful="success" in response_lower or "successful" in response_lower,
                task_completed="completed" in response_lower or "done" in response_lower,
                observation=response[:500]
            )

        try:
            data = json.loads(json_match.group())
            return VerificationResult(
                action_successful=data.get("action_successful", False),
                task_completed=data.get("task_completed", False),
                observation=data.get("observation", ""),
                issues=data.get("issues")
            )
        except json.JSONDecodeError:
            logger.warning("Failed to parse verification JSON")
            return VerificationResult(
                action_successful=True,
                task_completed=False,
                observation="Could not parse verification response"
            )
