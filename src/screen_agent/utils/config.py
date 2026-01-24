"""Configuration management for ScreenControlAgent."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class AgentConfig:
    """Agent behavior configuration."""
    max_steps: int = 20
    action_delay: float = 0.5
    verify_each_step: bool = True
    timeout: int = 300


@dataclass
class VLMConfig:
    """VLM provider configuration."""
    provider: str = "claude"
    claude_model: str = "claude-3-5-sonnet-20241022"
    openai_model: str = "gpt-4o"
    max_tokens: int = 4096


@dataclass
class ScreenConfig:
    """Screen capture configuration."""
    monitor_index: int = 1
    jpeg_quality: int = 85
    max_width: int = 1920
    max_height: int = 1080


@dataclass
class ExecutionConfig:
    """Execution behavior configuration."""
    mouse_move_duration: float = 0.3
    fail_safe: bool = True
    typing_interval: float = 0.05


@dataclass
class GroundingConfig:
    """Grounding/UIAutomation configuration (Phase 2)."""
    enabled: bool = True
    mode: str = "hybrid"  # visual_only, grounded, hybrid, separated
    confidence_threshold: float = 0.4
    uia_max_depth: int = 15
    uia_cache_duration: float = 0.5


@dataclass
class SeparatedArchConfig:
    """Configuration for separated VLM/LLM architecture."""
    enabled: bool = False  # Set to True to use separated architecture
    perception_provider: str = "openai"  # VLM for perception: openai or claude
    perception_model: str = "gpt-4o-mini"  # Fast/cheap model for perception
    reasoning_provider: str = "openai"  # LLM for reasoning: openai or claude
    reasoning_model: str = "gpt-4o"  # Powerful model for reasoning


@dataclass
class MemoryConfig:
    """Memory system configuration (Phase 3)."""
    enabled: bool = True
    short_term_context_size: int = 10
    long_term_storage: str = "data/memory.json"
    element_cache_ttl: float = 300.0


@dataclass
class TaskPlanningConfig:
    """Task planning configuration (Phase 3)."""
    enabled: bool = True
    auto_decompose: bool = True
    max_subtasks: int = 10


@dataclass
class ErrorRecoveryConfig:
    """Error recovery configuration (Phase 3)."""
    enabled: bool = True
    max_recovery_attempts: int = 3


@dataclass
class Config:
    """Main configuration class."""
    agent: AgentConfig = field(default_factory=AgentConfig)
    vlm: VLMConfig = field(default_factory=VLMConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    grounding: GroundingConfig = field(default_factory=GroundingConfig)

    # Phase 3 configurations
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    task_planning: TaskPlanningConfig = field(default_factory=TaskPlanningConfig)
    error_recovery: ErrorRecoveryConfig = field(default_factory=ErrorRecoveryConfig)

    # Separated architecture configuration
    separated_arch: SeparatedArchConfig = field(default_factory=SeparatedArchConfig)

    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file and environment variables.

    Priority: environment variables > config file > defaults

    Args:
        config_path: Optional path to YAML config file

    Returns:
        Config object with loaded settings
    """
    load_dotenv()

    config = Config()

    yaml_path = config_path or os.getenv("SCREEN_AGENT_CONFIG", "config/settings.yaml")
    if Path(yaml_path).exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if "agent" in data:
            config.agent = AgentConfig(**data["agent"])

        if "vlm" in data:
            vlm_data = data["vlm"]
            config.vlm = VLMConfig(
                provider=vlm_data.get("provider", "claude"),
                claude_model=vlm_data.get("claude", {}).get("model", "claude-sonnet-4-5-20250514"),
                openai_model=vlm_data.get("openai", {}).get("model", "gpt-4o"),
                max_tokens=vlm_data.get("claude", {}).get("max_tokens", 4096)
            )

        if "screen" in data:
            config.screen = ScreenConfig(**data["screen"])

        if "execution" in data:
            exec_data = data["execution"]
            config.execution = ExecutionConfig(
                mouse_move_duration=exec_data.get("mouse", {}).get("move_duration", 0.3),
                fail_safe=exec_data.get("mouse", {}).get("fail_safe", True),
                typing_interval=exec_data.get("keyboard", {}).get("typing_interval", 0.05)
            )

        if "grounding" in data:
            grounding_data = data["grounding"]
            config.grounding = GroundingConfig(
                enabled=grounding_data.get("enabled", True),
                mode=grounding_data.get("mode", "hybrid"),
                confidence_threshold=grounding_data.get("confidence_threshold", 0.4),
                uia_max_depth=grounding_data.get("uia_max_depth", 15),
                uia_cache_duration=grounding_data.get("uia_cache_duration", 0.5)
            )

        # Phase 3: Memory configuration
        if "memory" in data:
            memory_data = data["memory"]
            config.memory = MemoryConfig(
                enabled=memory_data.get("enabled", True),
                short_term_context_size=memory_data.get("short_term_context_size", 10),
                long_term_storage=memory_data.get("long_term_storage", "data/memory.json"),
                element_cache_ttl=memory_data.get("element_cache_ttl", 300.0)
            )

        # Phase 3: Task planning configuration
        if "task_planning" in data:
            planning_data = data["task_planning"]
            config.task_planning = TaskPlanningConfig(
                enabled=planning_data.get("enabled", True),
                auto_decompose=planning_data.get("auto_decompose", True),
                max_subtasks=planning_data.get("max_subtasks", 10)
            )

        # Phase 3: Error recovery configuration
        if "error_recovery" in data:
            recovery_data = data["error_recovery"]
            config.error_recovery = ErrorRecoveryConfig(
                enabled=recovery_data.get("enabled", True),
                max_recovery_attempts=recovery_data.get("max_recovery_attempts", 3)
            )

        # Separated architecture configuration
        if "separated_arch" in data:
            sep_data = data["separated_arch"]
            config.separated_arch = SeparatedArchConfig(
                enabled=sep_data.get("enabled", False),
                perception_provider=sep_data.get("perception_provider", "openai"),
                perception_model=sep_data.get("perception_model", "gpt-4o-mini"),
                reasoning_provider=sep_data.get("reasoning_provider", "openai"),
                reasoning_model=sep_data.get("reasoning_model", "gpt-4o")
            )

    config.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    config.openai_api_key = os.getenv("OPENAI_API_KEY")

    return config
