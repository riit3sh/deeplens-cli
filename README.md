# DeepLens

DeepLens is a terminal-native AI research pipeline for producing inspectable, citation-grounded reports. It autonomously generates dynamic perspectives, browses the web, extracts factual evidence, and synthesizes final reports in Markdown and PDF formats.

```text
CLI → Dynamic LLM Planner → Parallel Perspective Researchers → Source Curator
    → Evidence Extraction → Contradiction Analysis
    → Writer → Report Assembly (Markdown + PDF + JSON)
```

## Installation

DeepLens requires Python 3.11+. Install it globally from PyPI:

```bash
pip install deeplens-cli
```

## Setup & Configuration

DeepLens includes a built-in interactive configuration tool. Simply run:

```bash
deeplens config
```

This will instantly generate a `.env` template in your current folder and open it in your default text editor (like Notepad). You can configure your API keys here:
- **Tavily API Key (Required):** Used for live web search and document retrieval.
- **OpenAI API Key (Required):** Used for the LLM researcher and writer nodes.
- **OpenAI Base URL (Optional):** Highly recommended! Point this to providers like DeepInfra (e.g., `https://api.deepinfra.com/v1/openai`) to use cheap, open-source models!
- **DeepLens Model (Optional):** Define your specific model string (e.g., `meta-llama/Meta-Llama-3-8B-Instruct`).
- **Firecrawl API Key (Optional):** Without it, DeepLens falls back to its built-in HTTP extractor.

## Usage

To instantly launch the interactive terminal UI (TUI), just type:

```bash
deeplens
```

Alternatively, pass your query directly:

```bash
deeplens research "Should India significantly expand nuclear power by 2040?" --max-perspectives 4
```

For scripts or CI pipelines, disable the TUI:

```bash
deeplens research "..." --non-interactive --output reports
```

Each run creates an isolated artifact directory like `reports/<slug>-<timestamp>/` containing:
- `report.md` (Formatted Markdown report with citations)
- `report.pdf` (Rendered PDF version)
- `sources.json` (Curated bibliography)
- `evidence.json` (Raw factual extractions)
- `run.json` (System traces and timings)

## Advanced Features

- **Dynamic Perspective Generation:** The LLM Planner analyzes your exact intent (e.g., "controversies", "feasibility") and dynamically scopes the research angles.
- **Aggressive Data Sanitization:** The pipeline actively filters out SEO spam, Windows file paths, UI elements, and irrelevant metadata from web documents before extraction.
- **Robust Citation Engine:** The Writer intelligently maps extracted evidence back to the exact URL sources, gracefully handling broken citations or unlisted references.
- **Fault-Tolerant Parallelism:** Background tasks are wrapped in exception handlers—if one web page or perspective crashes, the rest of the report continues assembling successfully.

## Development

To work on DeepLens locally:

```bash
git clone https://github.com/riit3sh/deeplens-cli.git
cd deeplens-cli
python -m pip install -e ".[dev]"
```

Run tests and linters:
```bash
python -m pytest
python -m ruff check .
```

Licensed under [MIT](LICENSE).
