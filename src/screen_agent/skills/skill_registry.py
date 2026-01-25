"""Skill registry for managing available skills.

The registry maintains a collection of skills that can be
discovered and invoked by the agent.
"""

from typing import Dict, List, Optional, Type
from .skill_base import Skill
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SkillRegistry:
    """
    Registry for managing skills.

    Provides registration, discovery, and retrieval of skills.
    """

    _instance: Optional["SkillRegistry"] = None

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._skill_classes: Dict[str, Type[Skill]] = {}

    @classmethod
    def get_instance(cls) -> "SkillRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, skill: Skill) -> None:
        """
        Register a skill instance.

        Args:
            skill: Skill instance to register
        """
        if skill.name in self._skills:
            logger.warning(f"Overwriting existing skill: {skill.name}")

        self._skills[skill.name] = skill
        logger.debug(f"Registered skill: {skill.name}")

    def register_class(self, skill_class: Type[Skill]) -> None:
        """
        Register a skill class (instantiated on first use).

        Args:
            skill_class: Skill class to register
        """
        # Create temporary instance to get name
        temp = skill_class()
        name = temp.name

        if name in self._skill_classes:
            logger.warning(f"Overwriting existing skill class: {name}")

        self._skill_classes[name] = skill_class
        logger.debug(f"Registered skill class: {name}")

    def get(self, name: str) -> Optional[Skill]:
        """
        Get a skill by name.

        Args:
            name: Skill name

        Returns:
            Skill instance or None
        """
        # First check instances
        if name in self._skills:
            return self._skills[name]

        # Then check classes (instantiate if found)
        if name in self._skill_classes:
            skill = self._skill_classes[name]()
            self._skills[name] = skill
            return skill

        return None

    def get_all(self) -> List[Skill]:
        """Get all registered skills."""
        # Instantiate all classes
        for name, skill_class in self._skill_classes.items():
            if name not in self._skills:
                self._skills[name] = skill_class()

        return list(self._skills.values())

    def get_by_tag(self, tag: str) -> List[Skill]:
        """Get skills with a specific tag."""
        return [
            skill for skill in self.get_all()
            if tag in skill.tags
        ]

    def get_by_app(self, app_name: str) -> List[Skill]:
        """Get skills for a specific application."""
        return [
            skill for skill in self.get_all()
            if app_name.lower() in [a.lower() for a in skill.required_apps]
        ]

    def search(self, query: str) -> List[Skill]:
        """
        Search for skills matching a query.

        Args:
            query: Search query

        Returns:
            List of matching skills
        """
        query_lower = query.lower()
        results = []

        for skill in self.get_all():
            score = 0

            # Name match
            if query_lower in skill.name.lower():
                score += 3

            # Description match
            if query_lower in skill.description.lower():
                score += 2

            # Tag match
            if any(query_lower in tag.lower() for tag in skill.tags):
                score += 1

            if score > 0:
                results.append((score, skill))

        results.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in results]

    def unregister(self, name: str) -> bool:
        """
        Unregister a skill.

        Args:
            name: Skill name

        Returns:
            True if skill was unregistered
        """
        removed = False

        if name in self._skills:
            del self._skills[name]
            removed = True

        if name in self._skill_classes:
            del self._skill_classes[name]
            removed = True

        return removed

    def clear(self) -> None:
        """Remove all registered skills."""
        self._skills.clear()
        self._skill_classes.clear()

    def get_tool_schemas(self) -> List[Dict]:
        """Get all skills as LLM tool schemas."""
        return [skill.to_tool_schema() for skill in self.get_all()]

    def list_skills(self) -> str:
        """Get formatted list of available skills."""
        lines = ["可用技能列表:"]

        for skill in self.get_all():
            params_str = ", ".join(
                f"{p.name}: {p.param_type}" + ("?" if not p.required else "")
                for p in skill.parameters
            )
            lines.append(f"  - {skill.name}({params_str}): {skill.description}")

        return "\n".join(lines)
