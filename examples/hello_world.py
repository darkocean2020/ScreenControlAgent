#!/usr/bin/env python
"""
Example: Open Notepad and type Hello World

This is a simple example to verify the MVP functionality.

Usage:
    python examples/hello_world.py

Requirements:
    - Set ANTHROPIC_API_KEY in .env file
    - Windows operating system
"""

import sys
import os

# Add src to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from screen_agent.agent import ScreenControlAgent
from screen_agent.perception.vlm_client import ClaudeVLMClient, OpenAIVLMClient
from screen_agent.utils.config import load_config
from screen_agent.utils.logger import setup_logger, get_logger


def main():
    # Setup logging
    setup_logger(level="INFO")
    logger = get_logger(__name__)

    # Load configuration
    config = load_config()

    # Check API key
    if config.vlm.provider == "claude":
        if not config.anthropic_api_key:
            print("Error: ANTHROPIC_API_KEY not set")
            print("Please create a .env file with your API key:")
            print("  ANTHROPIC_API_KEY=sk-ant-your-key-here")
            return 1
        vlm_client = ClaudeVLMClient(
            api_key=config.anthropic_api_key,
            model=config.vlm.claude_model
        )
    else:
        if not config.openai_api_key:
            print("Error: OPENAI_API_KEY not set")
            return 1
        vlm_client = OpenAIVLMClient(
            api_key=config.openai_api_key,
            model=config.vlm.openai_model
        )

    # Create agent
    agent = ScreenControlAgent(
        vlm_client=vlm_client,
        max_steps=15,
        action_delay=0.5,
        verify_each_step=True
    )

    # Define task
    task = """
    Open Windows Notepad and type "Hello World".

    Steps:
    1. Click the Windows Start button or press the Windows key
    2. Type "notepad" to search
    3. Click on Notepad in the search results
    4. Wait for Notepad to open
    5. Type "Hello World" in the text area
    6. The task is complete when "Hello World" is visible in Notepad
    """

    # Run
    print("=" * 50)
    print("Task: Open Notepad and type Hello World")
    print("=" * 50)
    print()

    try:
        success = agent.run(task)

        print()
        print("=" * 50)
        if success:
            print("SUCCESS! Task completed.")
        else:
            print("FAILED. Task did not complete.")
            if agent.state and agent.state.error_message:
                print(f"Error: {agent.state.error_message}")
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
