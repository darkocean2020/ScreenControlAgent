"""Skills system for extending agent capabilities.

Skills are reusable, parameterized action sequences that the agent
can invoke to perform common tasks reliably.
"""

from .skill_base import Skill, SkillParameter, SkillResult, SkillStatus
from .skill_registry import SkillRegistry
from .skill_executor import SkillExecutor
from .builtin_skills import register_builtin_skills

__all__ = [
    "Skill",
    "SkillParameter",
    "SkillResult",
    "SkillStatus",
    "SkillRegistry",
    "SkillExecutor",
    "register_builtin_skills"
]
