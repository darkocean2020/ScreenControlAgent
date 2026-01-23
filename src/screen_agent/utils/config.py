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
    mode: str = "hybrid"  # visual_only, grounded, hybrid
    confidence_threshold: float = 0.4
    uia_max_depth: int = 15
    uia_cache_duration: float = 0.5


@dataclass
class Config:
    """Main configuration class."""
    agent: AgentConfig = field(default_factory=AgentConfig)
    vlm: VLMConfig = field(default_factory=VLMConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    grounding: GroundingConfig = field(default_factory=GroundingConfig)

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

    config.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    config.openai_api_key = os.getenv("OPENAI_API_KEY")

    return config
