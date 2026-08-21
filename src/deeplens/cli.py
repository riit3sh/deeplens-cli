"""Terminal entrypoint with a polished TUI and a script-friendly fallback."""

from __future__ import annotations

import argparse
import asyncio
import sys
import warnings
from collections.abc import Sequence
from pathlib import Path

# Suppress messy LangChain/LangGraph deprecation warnings from showing up in the user's terminal
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)
warnings.filterwarnings("ignore", message=".*allowed_objects.*")
warnings.filterwarnings("ignore", message=".*LangChainPendingDeprecationWarning.*")

from . import __version__
from .config import Settings
from .providers import FirecrawlExtractor, HttpxPageExtractor, TavilySearchProvider
from .reports import export_run
from .research import ResearchEngine, RunEvent
from .tui import ResearchApp

def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="deeplens", description="Citation-grounded research.")
    command.add_argument("--version", action="version", version=f"deeplens {__version__}")
    sub = command.add_subparsers(dest="command", required=True)
    research = sub.add_parser("research", help="Research a question from multiple perspectives.")
    research.add_argument(
        "question", nargs="?", help="Question to investigate (optional in the TUI)."
    )
    research.add_argument("--output", type=Path, default=Path("reports"))
    research.add_argument("--format", choices=("all", "markdown", "pdf"), default="all")
    research.add_argument("--max-perspectives", type=int, choices=range(1, 6), metavar="1-5")
    research.add_argument(
        "--non-interactive", action="store_true", help="Run without the TUI; suitable for CI."
    )
    sub.add_parser("config", help="Show or set up global API keys and configuration.")
    return command


async def _script_research(args: argparse.Namespace, settings: Settings) -> int:
    if not args.question:
        print("A question is required with --non-interactive.", file=sys.stderr)
        return 2
    if not settings.tavily_api_key:
        print("TAVILY_API_KEY is required for live research.", file=sys.stderr)
        return 2

    def progress(event: RunEvent) -> None:
        print(f"[{event.name}] {event.data}")

    extractor = (
        FirecrawlExtractor(settings) if settings.firecrawl_api_key else HttpxPageExtractor(settings)
    )
    try:
        artifact = await ResearchEngine(
            settings, TavilySearchProvider(settings), extractor, progress
        ).run(args.question)
        print(f"Report written to {export_run(artifact, settings.output_dir)}")
        return 0
    except KeyboardInterrupt:
        return 130


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "config":
        settings = Settings()
        print("--- DeepLens Configuration ---")
        print(f"  Model:      {settings.deeplens_model or '(default)'}")
        print(f"  Search:     {'tavily' if settings.has_live_search else 'unconfigured'}")
        print(f"  Extractor:  {'firecrawl' if settings.firecrawl_api_key else 'httpx'}")
        print(f"  Output Dir: {settings.output_dir}\n")
        
        print("--- API Key Setup ---")
        print("Leave blank to keep current value.")
        
        local_env = Path(".env")
        updates = {}
        
        def save_local_config(new_vars: dict[str, str]) -> None:
            env_vars = {}
            if local_env.exists():
                for line in local_env.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip()
            env_vars.update(new_vars)
            lines = [f"{k}={v}" for k, v in env_vars.items()]
            local_env.write_text("\n".join(lines), encoding="utf-8")

        def prompt_key(name: str, key_var: str, current: str | None) -> None:
            masked = f"{current[:4]}...{current[-4:]}" if current and len(current) > 8 else ("(Set)" if current else "(Not Set)")
            val = input(f"{name} [{masked}]: ").strip()
            if val:
                updates[key_var] = val

        try:
            prompt_key("OpenAI API Key", "OPENAI_API_KEY", settings.openai_api_key)
            prompt_key("OpenAI Base URL (Optional)", "OPENAI_BASE_URL", settings.openai_base_url)
            prompt_key("DeepLens Model (Optional)", "DEEPLENS_MODEL", settings.deeplens_model)
            prompt_key("Tavily API Key", "TAVILY_API_KEY", settings.tavily_api_key)
            prompt_key("Firecrawl API Key (Optional)", "FIRECRAWL_API_KEY", settings.firecrawl_api_key)
            
            if updates:
                save_local_config(updates)
                print(f"\n[+] Configuration securely saved to local {local_env.absolute()}")
            else:
                print("\nNo changes made.")
        except KeyboardInterrupt:
            print("\nSetup cancelled.")
            
        return 0
    settings = Settings(
        output_dir=args.output,
        max_perspectives=args.max_perspectives or Settings().max_perspectives,
    )
    if args.non_interactive:
        return asyncio.run(_script_research(args, settings))
    ResearchApp(settings, args.question).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
