"""Terminal entrypoint with a polished TUI and a script-friendly fallback."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

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
    sub.add_parser("config", help="Show safe effective configuration.")
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
        print(
            f"model={settings.deeplens_model or '(not configured)'}\nsearch={'tavily' if settings.has_live_search else 'unconfigured'}\nextractor={'firecrawl' if settings.firecrawl_api_key else 'httpx'}\noutput={settings.output_dir}"
        )
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
