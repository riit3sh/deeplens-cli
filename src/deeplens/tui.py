"""The native DeepLens research cockpit."""

from __future__ import annotations

import os
import webbrowser

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Label, ProgressBar, RichLog, Static

from .config import Settings
from .providers import FirecrawlExtractor, HttpxPageExtractor, TavilySearchProvider
from .reports import export_run
from .research import ResearchEngine

LOGO = """
 ██████╗ ███████╗███████╗██████╗ ██╗     ███████╗███╗   ██╗███████╗
 ██╔══██╗██╔════╝██╔════╝██╔══██╗██║     ██╔════╝████╗  ██║██╔════╝
 ██║  ██║█████╗  █████╗  ██████╔╝██║     █████╗  ██╔██╗ ██║███████╗
 ██║  ██║██╔══╝  ██╔══╝  ██╔═══╝ ██║     ██╔══╝  ██║╚██╗██║╚════██║
 ██████╔╝███████╗███████╗██║     ███████╗███████╗██║ ╚████║███████║
 ╚═════╝ ╚══════╝╚══════╝╚═╝     ╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝
""".strip()


class ResearchApp(App[None]):
    """Keyboard-friendly research UI using the production engine."""

    TITLE = "DeepLens"
    SUB_TITLE = "Research cockpit"
    CSS = """
    Screen { background: #07111d; color: #d7e8ff; }
    #shell { width: 94%; max-width: 120; height: 1fr; margin: 1 3; }
    #brand { color: #70e8ef; text-style: bold; height: auto; }
    #tagline { color: #8faac7; margin-bottom: 1; }
    #question { border: tall #2399cb; background: #0b1b2e; color: #f3fbff; }
    #actions { height: auto; margin: 1 0; }
    Button { margin-right: 1; }
    #run { background: #15a59a; color: #041018; text-style: bold; }
    #open-pdf, #open-folder { display: none; }
    #status { color: #f0c674; height: auto; }
    #progress { margin: 1 0; }
    #events { height: 1fr; min-height: 12; border: round #173c5a; background: #081522; }
    .hint { color: #7793b0; }
    """
    BINDINGS = [("ctrl+o", "open_pdf", "Open report"), ("ctrl+r", "focus_question", "New research")]

    def __init__(self, settings: Settings, initial_question: str | None = None) -> None:
        super().__init__()
        self.settings, self.initial_question, self.report_folder = (
            settings,
            initial_question or "",
            None,
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="shell"):
            yield Static(LOGO, id="brand")
            yield Label("Citation-grounded research, built for scrutiny.", id="tagline")
            yield Input(
                placeholder="What would you like to research? (enter only the question)",
                value=self.initial_question,
                id="question",
            )
            with Horizontal(id="actions"):
                yield Button("Research", id="run", variant="success")
                yield Button("Open PDF", id="open-pdf")
                yield Button("Open folder", id="open-folder")
            yield Label("Ready. Enter a question and press Enter.", id="status")
            yield ProgressBar(total=7, show_eta=False, id="progress")
            with VerticalScroll():
                yield RichLog(id="events", highlight=True, markup=True, wrap=True)
            yield Label(
                "Enter: research · Ctrl+O: open latest report · Ctrl+R: new question",
                classes="hint",
            )
        yield Footer()

    @on(Input.Submitted, "#question")
    @on(Button.Pressed, "#run")
    def start_research(self) -> None:
        question = self.query_one("#question", Input).value.strip()
        # Be forgiving when a user pastes the shell command into the TUI field.
        if question.lower().startswith("deeplens research "):
            question = question[len("deeplens research ") :].strip().strip('"')
            self.query_one("#question", Input).value = question
        if not question:
            self.query_one("#status", Label).update("Ask a specific question to begin.")
        elif not self.settings.tavily_api_key:
            self.query_one("#status", Label).update("TAVILY_API_KEY is required for live research.")
        else:
            self.query_one("#run", Button).disabled = True
            self.query_one("#progress", ProgressBar).update(progress=0)
            self.run_research(question)

    @work(exclusive=True)
    async def run_research(self, question: str) -> None:
        log = self.query_one("#events", RichLog)
        progress = self.query_one("#progress", ProgressBar)
        status = self.query_one("#status", Label)
        stages = {
            "run_started": 1,
            "planner_completed": 2,
            "researcher_started": 3,
            "researcher_completed": 4,
            "source_found": 5,
            "run_completed": 6,
        }

        def event(item: object) -> None:
            name, data = getattr(item, "name", "event"), getattr(item, "data", {})
            log.write(f"[bold cyan]◆ {name.replace('_', ' ').title()}[/] [dim]{data}[/]")
            status.update(f"{name.replace('_', ' ').title()}…")
            progress.update(progress=stages.get(name, 3))

        extractor = (
            FirecrawlExtractor(self.settings)
            if self.settings.firecrawl_api_key
            else HttpxPageExtractor(self.settings)
        )
        try:
            engine = ResearchEngine(
                self.settings, TavilySearchProvider(self.settings), extractor, event_sink=event
            )
            artifact = await engine.run(question)
            self.report_folder = export_run(artifact, self.settings.output_dir)
            progress.update(progress=7)
            status.update(
                f"Complete — {len(artifact.sources)} sources, {len(artifact.evidence)} evidence records."
            )
            self.query_one("#open-pdf", Button).display = True
            self.query_one("#open-folder", Button).display = True
        except Exception as error:
            status.update(f"Research stopped: {error}")
            log.write(f"[bold red]× {error}[/]")
        finally:
            self.query_one("#run", Button).disabled = False

    @on(Button.Pressed, "#open-pdf")
    def open_pdf(self) -> None:
        if self.report_folder:
            webbrowser.open((self.report_folder / "report.pdf").resolve().as_uri())

    @on(Button.Pressed, "#open-folder")
    def open_folder(self) -> None:
        if self.report_folder:
            os.startfile(self.report_folder)  # type: ignore[attr-defined]

    def action_open_pdf(self) -> None:
        self.open_pdf()

    def action_focus_question(self) -> None:
        self.query_one("#question", Input).focus()
