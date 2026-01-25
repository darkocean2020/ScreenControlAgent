"""Base classes for the Skills system.

Skills are parameterized, reusable action sequences that encapsulate
common operations like opening applications, saving files, etc.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Callable
import time


class SkillStatus(Enum):
    """Status of skill execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SkillParameter:
    """Definition of a skill parameter."""
    name: str
    description: str
    param_type: str = "string"  # string, int, bool, choice
    required: bool = True
    default: Any = None
    choices: Optional[List[str]] = None  # For choice type

    def validate(self, value: Any) -> bool:
        """Validate a parameter value."""
        if value is None:
            return not self.required

        if self.param_type == "string":
            return isinstance(value, str)
        elif self.param_type == "int":
            return isinstance(value, int)
        elif self.param_type == "bool":
            return isinstance(value, bool)
        elif self.param_type == "choice":
            return value in (self.choices or [])

        return True

    def to_schema(self) -> Dict[str, Any]:
        """Convert to JSON schema format."""
        schema = {
            "type": self.param_type if self.param_type != "choice" else "string",
            "description": self.description
        }

        if self.choices:
            schema["enum"] = self.choices

        if self.default is not None:
            schema["default"] = self.default

        return schema


@dataclass
class SkillResult:
    """Result of skill execution."""
    status: SkillStatus
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    steps_executed: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == SkillStatus.SUCCESS


@dataclass
class SkillStep:
    """A single step in a skill."""
    action: str  # Tool name: click, type_text, hotkey, etc.
    params: Dict[str, Any]
    description: str = ""
    wait_after: float = 0.3  # Seconds to wait after this step
    condition: Optional[Callable[[], bool]] = None  # Skip if returns False


class Skill(ABC):
    """
    Base class for all skills.

    A skill is a reusable, parameterized action sequence that performs
    a specific task. Skills can be invoked by the agent's LLM through
    the use_skill tool.
    """

    def __init__(self):
        self._status = SkillStatus.PENDING
        self._cancelled = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the skill."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the skill does."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> List[SkillParameter]:
        """List of parameters the skill accepts."""
        pass

    @property
    def tags(self) -> List[str]:
        """Tags for categorization and search."""
        return []

    @property
    def required_apps(self) -> List[str]:
        """Applications this skill requires."""
        return []

    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate provided parameters.

        Returns:
            Tuple of (is_valid, error_message)
        """
        for param in self.parameters:
            value = params.get(param.name, param.default)

            if param.required and value is None:
                return False, f"Missing required parameter: {param.name}"

            if value is not None and not param.validate(value):
                return False, f"Invalid value for parameter {param.name}: {value}"

        return True, ""

    @abstractmethod
    def execute(
        self,
        params: Dict[str, Any],
        executor: Any  # ActionExecutor
    ) -> SkillResult:
        """
        Execute the skill with given parameters.

        Args:
            params: Validated parameters
            executor: ActionExecutor instance for performing actions

        Returns:
            SkillResult indicating success/failure
        """
        pass

    def cancel(self):
        """Request cancellation of the skill."""
        self._cancelled = True

    def to_tool_schema(self) -> Dict[str, Any]:
        """Convert skill to LLM tool schema format."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required.append(param.name)

        return {
            "name": f"skill_{self.name}",
            "description": f"[技能] {self.description}",
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }


class SimpleSkill(Skill):
    """
    A skill defined by a sequence of steps.

    For simple skills that are just a list of actions,
    without complex logic.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: List[SkillParameter],
        steps: List[SkillStep],
        tags: Optional[List[str]] = None,
        required_apps: Optional[List[str]] = None
    ):
        super().__init__()
        self._name = name
        self._description = description
        self._parameters = parameters
        self._steps = steps
        self._tags = tags or []
        self._required_apps = required_apps or []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> List[SkillParameter]:
        return self._parameters

    @property
    def tags(self) -> List[str]:
        return self._tags

    @property
    def required_apps(self) -> List[str]:
        return self._required_apps

    def execute(
        self,
        params: Dict[str, Any],
        executor: Any
    ) -> SkillResult:
        """Execute the skill steps sequentially."""
        from ..models.action import Action, ActionType

        steps_executed = 0

        for step in self._steps:
            if self._cancelled:
                return SkillResult(
                    status=SkillStatus.CANCELLED,
                    message="Skill cancelled",
                    steps_executed=steps_executed
                )

            # Check condition
            if step.condition and not step.condition():
                continue

            # Resolve parameter references in step params
            resolved_params = self._resolve_params(step.params, params)

            try:
                # Create and execute action
                action = self._create_action(step.action, resolved_params)
                if action:
                    success = executor.execute(action)
                    if not success:
                        return SkillResult(
                            status=SkillStatus.FAILED,
                            message=f"Step failed: {step.description or step.action}",
                            steps_executed=steps_executed,
                            error=f"Action {step.action} failed"
                        )

                steps_executed += 1

                # Wait after step
                if step.wait_after > 0:
                    time.sleep(step.wait_after)

            except Exception as e:
                return SkillResult(
                    status=SkillStatus.FAILED,
                    message=f"Step error: {step.description or step.action}",
                    steps_executed=steps_executed,
                    error=str(e)
                )

        return SkillResult(
            status=SkillStatus.SUCCESS,
            message=f"Skill {self.name} completed successfully",
            steps_executed=steps_executed
        )

    def _resolve_params(
        self,
        step_params: Dict[str, Any],
        skill_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve parameter references like ${param_name}."""
        resolved = {}

        for key, value in step_params.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                param_name = value[2:-1]
                resolved[key] = skill_params.get(param_name, value)
            else:
                resolved[key] = value

        return resolved

    def _create_action(self, action_type: str, params: Dict[str, Any]):
        """Create an Action object from step definition."""
        from ..models.action import Action, ActionType

        action_map = {
            "click": ActionType.CLICK,
            "double_click": ActionType.DOUBLE_CLICK,
            "right_click": ActionType.RIGHT_CLICK,
            "type": ActionType.TYPE,
            "type_text": ActionType.TYPE,
            "hotkey": ActionType.HOTKEY,
            "scroll": ActionType.SCROLL,
            "wait": ActionType.WAIT,
        }

        if action_type not in action_map:
            return None

        at = action_map[action_type]

        if at == ActionType.CLICK:
            return Action(action_type=at, coordinates=(params["x"], params["y"]))
        elif at == ActionType.DOUBLE_CLICK:
            return Action(action_type=at, coordinates=(params["x"], params["y"]))
        elif at == ActionType.RIGHT_CLICK:
            return Action(action_type=at, coordinates=(params["x"], params["y"]))
        elif at == ActionType.TYPE:
            return Action(action_type=at, text=params.get("text", ""))
        elif at == ActionType.HOTKEY:
            return Action(action_type=at, keys=params.get("keys", []))
        elif at == ActionType.SCROLL:
            return Action(
                action_type=at,
                scroll_amount=params.get("amount", 3),
                coordinates=(params.get("x"), params.get("y")) if "x" in params else None
            )
        elif at == ActionType.WAIT:
            time.sleep(params.get("seconds", 1))
            return None

        return None
