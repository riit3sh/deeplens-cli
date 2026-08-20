# Architecture

DeepLens separates terminal presentation from `ResearchEngine`, so a future API or web frontend can invoke the same run. `Settings` centralizes budgets, timeouts, retry counts, output directory, and credential discovery. Network access is supplied through `SearchProvider` and `PageExtractor` protocols, making tests deterministic.

```text
ResearchEngine
  plan_perspectives() → 3–5 Perspective records
  asyncio.gather()   → independent searches and page extraction
  score_source()     → KEEP / REJECT / UNCERTAIN with components
  Evidence           → compact claim/passage/source mapping
  ResearchPacket     → per-perspective findings and uncertainty
  analysis           → contradictions and gaps
  export_run()       → Markdown, PDF, and JSON debugging artifact
```

The `build_langgraph()` method exposes the corresponding `Send` fan-out topology. The engine’s direct `asyncio.gather()` implementation supplies failure isolation: a failed page fetch becomes a `source_failed` event and does not fail other perspectives. Time measurements are captured from the actual run; no sequential estimate is fabricated.

Raw documents are capped at 80,000 characters before passage selection. Evidence and source IDs stay intact through compression and report citations.
