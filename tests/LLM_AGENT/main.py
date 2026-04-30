import argparse
import json

from configs.settings import AGENT_VERSION
from core.agent import Agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI IT Engineer Agent.")
    parser.add_argument("--version", action="version", version=f"AI IT Engineer Agent {AGENT_VERSION}")
    parser.add_argument(
        "goal",
        nargs="?",
        default="Open browser and search for error logs",
        help="Goal for the agent to pursue.",
    )
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan and evaluate actions without clicking or typing.",
    )
    parser.add_argument(
        "--chat",
        help="Respond conversationally instead of running the goal loop.",
    )
    parser.add_argument(
        "--auto-run",
        action="store_true",
        help="In chat mode, run the extracted goal when the message is a command.",
    )
    parser.add_argument(
        "--speak",
        action="store_true",
        help="Speak the conversational response with local text-to-speech.",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List local text-to-speech voices.",
    )
    parser.add_argument(
        "--learn",
        help="Build or update a learning path for a topic.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Approved web source URL for --learn. Can be passed multiple times.",
    )
    parser.add_argument(
        "--learning-status",
        action="store_true",
        help="Show knowledge, learning path, and expertise profile counts.",
    )
    args = parser.parse_args()

    agent = Agent(max_steps=args.max_steps, dry_run=args.dry_run, voice_enabled=args.speak)

    if args.list_voices:
        result = agent.voices()
    elif args.learning_status:
        result = agent.learning_status()
    elif args.learn:
        result = agent.learn(args.learn, sources=args.source, speak=args.speak)
    elif args.chat:
        result = agent.chat(args.chat, speak=args.speak, auto_run=args.auto_run)
    else:
        result = agent.run(goal=args.goal, speak=args.speak)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
