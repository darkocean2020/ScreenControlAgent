#!/usr/bin/env python
"""
Example: Open Notepad and type Hello World

This is a simple example to verify the LLM-driven functionality.

Usage:
    python examples/hello_world.py

Requirements:
    - Set ANTHROPIC_API_KEY and OPENAI_API_KEY in .env file
    - Windows operating system
"""

import sys
import os

# Add src to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from screen_agent.brain.llm_controller import LLMController
from screen_agent.perception.vlm_client import OpenAIVLMClient
from screen_agent.perception.ui_automation import UIAutomationClient
from screen_agent.utils.config import load_config
from screen_agent.utils.logger import setup_logger, get_logger


def main():
    # Setup logging
    setup_logger(level="INFO")
    logger = get_logger(__name__)

    # Load configuration
    config = load_config()

    # Check API keys
    if not config.anthropic_api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        print("Please create a .env file with your API key:")
        print("  ANTHROPIC_API_KEY=sk-ant-your-key-here")
        return 1

    if not config.openai_api_key:
        print("Error: OPENAI_API_KEY not set")
        print("Please create a .env file with your API key:")
        print("  OPENAI_API_KEY=sk-your-key-here")
        return 1

    # Create VLM client (for look_at_screen tool)
    vlm_client = OpenAIVLMClient(
        api_key=config.openai_api_key,
        model=config.vlm.openai_model
    )

    # Create UIAutomation client (optional but recommended)
    uia_client = None
    try:
        uia_client = UIAutomationClient()
    except Exception as e:
        logger.warning(f"UIAutomation not available: {e}")

    # Create LLM controller
    controller = LLMController(
        api_key=config.anthropic_api_key,
        model="claude-sonnet-4-20250514",
        vlm_client=vlm_client,
        uia_client=uia_client,
        max_tokens=4096,
        action_delay=0.5
    )

    # Define task
    task = "Open Windows Notepad and type 'Hello World'"

    # Run
    print("=" * 50)
    print("Task: Open Notepad and type Hello World")
    print("=" * 50)
    print()

    try:
        success = controller.run(task, max_steps=15)

        print()
        print("=" * 50)
        if success:
            print("SUCCESS! Task completed.")
        else:
            print("FAILED. Task did not complete.")
        print("=" * 50)

        return 0 if success else 1

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
