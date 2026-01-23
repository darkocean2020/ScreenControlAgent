"""CLI entry point for ScreenControlAgent."""

import argparse
import sys

from .agent import ScreenControlAgent
from .perception.vlm_client import ClaudeVLMClient, OpenAIVLMClient
from .utils.config import load_config
from .utils.logger import setup_logger, get_logger


def create_vlm_client(config):
    """Create VLM client based on configuration."""
    if config.vlm.provider == "claude":
        if not config.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Please set it in .env file or environment variable."
            )
        return ClaudeVLMClient(
            api_key=config.anthropic_api_key,
            model=config.vlm.claude_model
        )
    else:
        if not config.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY not set. "
                "Please set it in .env file or environment variable."
            )
        return OpenAIVLMClient(
            api_key=config.openai_api_key,
            model=config.vlm.openai_model
        )


def create_agent(config):
    """Create agent instance from configuration."""
    vlm_client = create_vlm_client(config)

    return ScreenControlAgent(
        vlm_client=vlm_client,
        max_steps=config.agent.max_steps,
        action_delay=config.agent.action_delay,
        verify_each_step=config.agent.verify_each_step,
        monitor_index=config.screen.monitor_index
    )


def run_task(agent, task: str) -> bool:
    """Run a single task."""
    return agent.run(task)


def interactive_mode(agent):
    """Run in interactive mode."""
    print("ScreenControlAgent Interactive Mode")
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

            success = run_task(agent, task)
            status = "SUCCESS" if success else "FAILED"
            print(f"\nResult: {status}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="VLM-based Screen Control Agent",
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
        "--provider",
        choices=["claude", "openai"],
        help="Override VLM provider"
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        help="Override maximum steps"
    )

    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Disable step verification"
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

    # Apply command-line overrides
    if args.provider:
        config.vlm.provider = args.provider
    if args.max_steps:
        config.agent.max_steps = args.max_steps
    if args.no_verify:
        config.agent.verify_each_step = False

    # Create agent
    try:
        agent = create_agent(config)
    except ValueError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        return 1

    # Run
    if args.interactive:
        interactive_mode(agent)
        return 0
    elif args.task:
        try:
            success = run_task(agent, args.task)
            return 0 if success else 1
        except Exception as e:
            logger.error(f"Task failed: {e}")
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
