"""CLI entrypoint for Code Buddy."""

from __future__ import annotations

import argparse
import json
import sys
import traceback

from agent.config import AVAILABLE_MODELS, get_settings
from agent.runner import run_generation


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Code Buddy — multi-agent project generator"
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=str,
        default=None,
        help="Project prompt (if omitted, you will be asked interactively)",
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        choices=list(AVAILABLE_MODELS),
        help=f"Groq model (default: {settings.groq_default_model})",
    )
    parser.add_argument(
        "--recursion-limit",
        "-r",
        type=int,
        default=None,
        help="LangGraph recursion limit (default from env)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the final result as JSON",
    )
    args = parser.parse_args()

    try:
        user_prompt = args.prompt or input("Enter your project prompt: ").strip()
        if not user_prompt:
            print("Prompt cannot be empty.", file=sys.stderr)
            sys.exit(1)

        def on_progress(stage: str, payload: dict) -> None:
            message = payload.get("message") or stage
            print(f"[{stage}] {message}")

        result = run_generation(
            user_prompt=user_prompt,
            model=args.model,
            recursion_limit=args.recursion_limit,
            on_progress=on_progress,
        )

        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print("\nGeneration complete.")
            print(f"Project: {result['project_dir']}")
            print(f"Files ({len(result['files'])}):")
            for path in result["files"]:
                print(f"  - {path}")
            if result.get("zip_path"):
                print(f"ZIP: {result['zip_path']}")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
