# DeepLens

DeepLens is a terminal-native research pipeline for producing inspectable, citation-grounded reports. It is intentionally a small set of deterministic stages and narrowly scoped roles—not a collection of autonomous agents.

```text
CLI → Planner → parallel perspective researchers → source curator
    → normalized evidence → research packets → contradiction/gap analysis
    → writer → verifier → Markdown + PDF + JSON artifacts
```

## Install

Python 3.11+ is required. With uv:

```bash
uv tool install deeplens
```

For development:

```bash
git clone https://github.com/your-org/deeplens
cd deeplens
uv sync --extra dev
copy .env.example .env  # on Windows; populate only the keys you use
uv run deeplens --help
```

`TAVILY_API_KEY` is required for live search. `FIRECRAWL_API_KEY` is optional; without it DeepLens uses its conservative HTTP extractor. `OPENAI_*` and `DEEPLENS_MODEL` are reserved for the provider-agnostic structured-LLM extension point; the initial deterministic planner/writer work without them.

## Usage

```bash
deeplens research "Should India significantly expand nuclear power by 2040?" --max-perspectives 4
deeplens research "..." --non-interactive --output reports
deeplens config
```

The default command opens the interactive research cockpit. It includes a focused question field,
live stage log, progress bar, and **Open PDF** / **Open folder** actions when a run completes.
Use `--non-interactive` for scripts. Firecrawl is optional: with only `TAVILY_API_KEY` configured,
DeepLens uses its cleaned HTTP extractor and removes navigation, headers, footers, forms, and common
site chrome before sentence-safe evidence extraction.

Each run creates `reports/<slug>-<timestamp>/` containing `report.md`, `report.pdf`, `sources.json`, `evidence.json`, and `run.json`. The JSON artifact includes sources, evidence, events, errors, timings, and model information. Credentials are never recorded.

## Design notes

- Parallelism is used only for independent perspective research and per-query fetching; all aggregation is explicit.
- Raw web pages are untrusted content. They are extracted as data, bounded in size, and never treated as instructions.
- Curation has transparent relevance/authority/freshness/directness components. The writer consumes evidence records, not raw pages.
- A rule-based verifier checks whether accepted sources appear in the report. A future LLM verifier can implement the same typed contract.

## Development

```bash
python -m pytest
python -m ruff check .
python -m build
```

Live integration testing is deliberately opt-in and should use configured accounts only:

```bash
python -m pytest -m integration
```

## Limitations

This first release does not claim factual accuracy, does not bypass paywalls, and cannot make weak web evidence strong. It uses a deterministic planner and report composer by default so local runs are reproducible; an OpenAI-compatible structured-output adapter is the next extension. The included Textual view is an optional progress surface; `--non-interactive` is appropriate for scripts and CI.

## PyPI release

1. Update the version in `pyproject.toml` and `src/deeplens/__init__.py`.
2. Run tests, Ruff, and `python -m build` from a clean checkout.
3. Inspect `dist/` with `twine check dist/*`.
4. Upload first to TestPyPI, smoke-test `pip install`, then publish with a PyPI trusted publisher or `twine upload dist/*`.

Licensed under [MIT](LICENSE).
