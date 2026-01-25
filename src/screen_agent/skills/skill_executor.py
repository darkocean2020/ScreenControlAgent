"""Skill executor for running skills.

Handles skill execution with proper error handling,
logging, and integration with the agent's action system.
"""

from typing import Dict, Any, Optional
from .skill_base import Skill, SkillResult, SkillStatus
from .skill_registry import SkillRegistry
from ..action.executor import ActionExecutor
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SkillExecutor:
    """
    Executor for running skills.

    Manages skill execution lifecycle, parameter validation,
    and result handling.
    """

    def __init__(
        self,
        action_executor: Optional[ActionExecutor] = None,
        registry: Optional[SkillRegistry] = None
    ):
        """
        Initialize skill executor.

        Args:
            action_executor: ActionExecutor for performing actions
            registry: SkillRegistry for skill lookup
        """
        self.action_executor = action_executor or ActionExecutor()
        self.registry = registry or SkillRegistry.get_instance()
        self._current_skill: Optional[Skill] = None

    def execute(
        self,
        skill_name: str,
        params: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute a skill by name.

        Args:
            skill_name: Name of the skill to execute
            params: Parameters for the skill

        Returns:
            SkillResult indicating success/failure
        """
        # Look up skill
        skill = self.registry.get(skill_name)
        if not skill:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"Skill not found: {skill_name}",
                error=f"No skill registered with name '{skill_name}'"
            )

        # Validate parameters
        valid, error = skill.validate_params(params)
        if not valid:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"Invalid parameters for skill {skill_name}",
                error=error
            )

        # Execute skill
        logger.info(f"Executing skill: {skill_name} with params: {params}")
        self._current_skill = skill

        try:
            result = skill.execute(params, self.action_executor)
            logger.info(f"Skill {skill_name} completed: {result.status.value}")
            return result

        except Exception as e:
            logger.error(f"Skill {skill_name} failed with exception: {e}")
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"Skill {skill_name} failed",
                error=str(e)
            )

        finally:
            self._current_skill = None

    def execute_skill(self, skill: Skill, params: Dict[str, Any]) -> SkillResult:
        """
        Execute a skill instance directly.

        Args:
            skill: Skill instance to execute
            params: Parameters for the skill

        Returns:
            SkillResult indicating success/failure
        """
        valid, error = skill.validate_params(params)
        if not valid:
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"Invalid parameters for skill {skill.name}",
                error=error
            )

        logger.info(f"Executing skill: {skill.name}")
        self._current_skill = skill

        try:
            result = skill.execute(params, self.action_executor)
            return result

        except Exception as e:
            logger.error(f"Skill {skill.name} failed: {e}")
            return SkillResult(
                status=SkillStatus.FAILED,
                message=f"Skill {skill.name} failed",
                error=str(e)
            )

        finally:
            self._current_skill = None

    def cancel_current(self) -> bool:
        """
        Cancel the currently running skill.

        Returns:
            True if a skill was cancelled
        """
        if self._current_skill:
            self._current_skill.cancel()
            logger.info(f"Cancelled skill: {self._current_skill.name}")
            return True
        return False

    def get_skill_info(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Dictionary with skill info or None
        """
        skill = self.registry.get(skill_name)
        if not skill:
            return None

        return {
            "name": skill.name,
            "description": skill.description,
            "parameters": [
                {
                    "name": p.name,
                    "description": p.description,
                    "type": p.param_type,
                    "required": p.required,
                    "default": p.default,
                    "choices": p.choices
                }
                for p in skill.parameters
            ],
            "tags": skill.tags,
            "required_apps": skill.required_apps
        }

    def list_skills(self) -> str:
        """Get formatted list of available skills."""
        return self.registry.list_skills()


def create_skill_tool_result(result: SkillResult) -> str:
    """
    Create a tool result string from a SkillResult.

    Args:
        result: SkillResult from skill execution

    Returns:
        Formatted result string for LLM
    """
    if result.success:
        return f"技能执行成功: {result.message}\n执行了 {result.steps_executed} 个步骤"
    else:
        return f"技能执行失败: {result.message}\n错误: {result.error or 'Unknown error'}"
