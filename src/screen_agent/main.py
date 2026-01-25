"""CLI entry point for ScreenControlAgent."""

import argparse
import sys

from .brain.llm_controller import LLMController
from .perception.vlm_client import ClaudeVLMClient, OpenAIVLMClient
from .perception.ui_automation import UIAutomationClient
from .utils.config import load_config
from .utils.logger import setup_logger, get_logger


def create_vlm_client(config):
    """Create VLM client based on configuration."""
    # VLM uses OpenAI (GPT-4o) by default for better vision
    if not config.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY not set. "
            "Please set it in .env file or environment variable."
        )
    return OpenAIVLMClient(
        api_key=config.openai_api_key,
        model=config.vlm.openai_model
    )


def create_controller(config):
    """Create LLM controller."""
    # LLM (brain) uses Claude
    if not config.anthropic_api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not set. "
            "Please set it in .env file or environment variable."
        )

    # Create VLM client for look_at_screen tool
    vlm_client = create_vlm_client(config)

    # Create UIAutomation client
    uia_client = None
    try:
        uia_client = UIAutomationClient(
            max_depth=config.grounding.get('uia_max_depth', 15),
            cache_duration=config.grounding.get('uia_cache_duration', 0.5)
        )
    except Exception as e:
        get_logger(__name__).warning(f"Failed to initialize UIAutomation: {e}")

    # Get controller settings
    controller_config = getattr(config, 'controller', None)
    llm_model = 'claude-sonnet-4-20250514'
    max_tokens = 4096

    if controller_config and hasattr(controller_config, 'llm'):
        llm_model = controller_config.llm.get('model', llm_model)
        max_tokens = controller_config.llm.get('max_tokens', max_tokens)

    return LLMController(
        api_key=config.anthropic_api_key,
        model=llm_model,
        vlm_client=vlm_client,
        uia_client=uia_client,
        max_tokens=max_tokens,
        monitor_index=config.screen.monitor_index,
        action_delay=config.agent.action_delay
    )


def interactive_mode(controller):
    """Run in interactive mode."""
    print("ScreenControlAgent Interactive Mode (LLM-Driven)")
    print("Type 'quit' or 'exit' to stop")
    print("-" * 40)

    while True:
        try:
            task = input("\nTask> ").strip()

            if task.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            if not task:
                continue

            success = controller.run(task)
            status = "SUCCESS" if success else "FAILED"
            print(f"\nResult: {status}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LLM-driven Screen Control Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  screen-agent "Open Notepad and type Hello World"
  screen-agent -i
  screen-agent --verbose "Open calculator"
        """
    )

    parser.add_argument(
        "task",
        nargs="?",
        help="Task to execute"
    )

    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Run in interactive mode"
    )

    parser.add_argument(
        "-c", "--config",
        help="Path to config file"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Maximum steps (0 = unlimited, default: unlimited)"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logger(level=log_level)
    logger = get_logger(__name__)

    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return 1

    # Create controller
    try:
        controller = create_controller(config)
    except ValueError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Failed to create controller: {e}")
        return 1

    # Run
    if args.interactive:
        interactive_mode(controller)
        return 0
    elif args.task:
        try:
            success = controller.run(args.task, max_steps=args.max_steps)
            return 0 if success else 1
        except Exception as e:
            logger.error(f"Task failed: {e}")
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
