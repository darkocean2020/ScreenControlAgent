"""CLI entry point for ScreenControlAgent."""

import argparse
import sys

from .agent import ScreenControlAgent
from .perception.vlm_client import ClaudeVLMClient, OpenAIVLMClient
from .utils.config import load_config
from .utils.logger import setup_logger, get_logger


def create_vlm_client(config, provider_override=None, model_override=None):
    """Create VLM client based on configuration."""
    provider = provider_override or config.vlm.provider

    if provider == "claude":
        if not config.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Please set it in .env file or environment variable."
            )
        model = model_override or config.vlm.claude_model
        return ClaudeVLMClient(
            api_key=config.anthropic_api_key,
            model=model
        )
    else:
        if not config.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY not set. "
                "Please set it in .env file or environment variable."
            )
        model = model_override or config.vlm.openai_model
        return OpenAIVLMClient(
            api_key=config.openai_api_key,
            model=model
        )


def create_llm_controller(config):
    """Create LLM controller for llm_driven mode."""
    from .brain.llm_controller import LLMController
    from .perception.ui_automation import UIAutomationClient

    # Get controller config
    controller_config = getattr(config, 'controller', None)

    # Determine LLM settings
    if controller_config and hasattr(controller_config, 'llm'):
        llm_provider = controller_config.llm.get('provider', 'claude')
        llm_model = controller_config.llm.get('model', 'claude-sonnet-4-20250514')
    else:
        llm_provider = 'claude'
        llm_model = 'claude-sonnet-4-20250514'

    # Get API key for LLM
    if llm_provider == 'claude':
        if not config.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Please set it in .env file or environment variable."
            )
        llm_api_key = config.anthropic_api_key
    else:
        if not config.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY not set for LLM. "
                "Please set it in .env file or environment variable."
            )
        llm_api_key = config.openai_api_key

    # Create VLM client for look_at_screen tool
    if controller_config and hasattr(controller_config, 'vlm_tool'):
        vlm_provider = controller_config.vlm_tool.get('provider', 'openai')
        vlm_model = controller_config.vlm_tool.get('model', 'gpt-4o')
    else:
        vlm_provider = config.vlm.provider
        vlm_model = None

    vlm_client = create_vlm_client(config, vlm_provider, vlm_model)

    # Create UIAutomation client
    uia_client = None
    if config.grounding.enabled:
        try:
            uia_client = UIAutomationClient(
                max_depth=config.grounding.get('uia_max_depth', 15),
                cache_duration=config.grounding.get('uia_cache_duration', 0.5)
            )
        except Exception as e:
            get_logger(__name__).warning(f"Failed to initialize UIAutomation: {e}")

    return LLMController(
        api_key=llm_api_key,
        model=llm_model,
        vlm_client=vlm_client,
        uia_client=uia_client,
        max_tokens=controller_config.llm.get('max_tokens', 4096) if controller_config else 4096,
        monitor_index=config.screen.monitor_index,
        action_delay=config.agent.action_delay
    )


def create_agent(config, planning_mode_override: str = None):
    """Create agent instance from configuration."""
    vlm_client = create_vlm_client(config)

    # Determine planning mode
    planning_mode = planning_mode_override or config.grounding.mode
    if not config.grounding.enabled:
        planning_mode = "visual_only"

    return ScreenControlAgent(
        vlm_client=vlm_client,
        max_steps=config.agent.max_steps,
        action_delay=config.agent.action_delay,
        verify_each_step=config.agent.verify_each_step,
        monitor_index=config.screen.monitor_index,
        planning_mode=planning_mode,
        grounding_confidence_threshold=config.grounding.confidence_threshold
    )


def run_task(agent, task: str) -> bool:
    """Run a single task."""
    return agent.run(task)


def interactive_mode(agent):
    """Run in interactive mode (legacy)."""
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


def interactive_mode_unified(controller, mode: str):
    """Run in interactive mode with unified controller interface."""
    mode_display = "LLM-Driven" if mode == "llm_driven" else "VLM-Driven"
    print(f"ScreenControlAgent Interactive Mode ({mode_display})")
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

            if mode == "llm_driven":
                success = controller.run(task)
            else:
                success = run_task(controller, task)

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
  screen-agent --mode llm_driven "Open calculator"
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
        "--mode",
        choices=["llm_driven", "vlm_driven"],
        help="Controller mode: llm_driven (LLM as brain, VLM as tool) or vlm_driven (legacy VLM-based)"
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

    parser.add_argument(
        "--planning-mode",
        choices=["visual_only", "grounded", "hybrid"],
        help="Planning mode (vlm_driven only): visual_only, grounded, or hybrid"
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

    # Determine controller mode
    controller_mode = args.mode
    if not controller_mode:
        # Use config setting if available
        controller_config = getattr(config, 'controller', None)
        if controller_config and hasattr(controller_config, 'mode'):
            controller_mode = controller_config.mode
        else:
            controller_mode = "vlm_driven"  # Default to legacy mode

    logger.info(f"Controller mode: {controller_mode}")

    # Create controller or agent based on mode
    try:
        if controller_mode == "llm_driven":
            controller = create_llm_controller(config)
        else:
            controller = create_agent(config, planning_mode_override=args.planning_mode)
    except ValueError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Failed to create controller: {e}")
        return 1

    # Run
    if args.interactive:
        interactive_mode_unified(controller, controller_mode)
        return 0
    elif args.task:
        try:
            max_steps = args.max_steps or config.agent.max_steps
            if controller_mode == "llm_driven":
                success = controller.run(args.task, max_steps=max_steps)
            else:
                success = run_task(controller, args.task)
            return 0 if success else 1
        except Exception as e:
            logger.error(f"Task failed: {e}")
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
