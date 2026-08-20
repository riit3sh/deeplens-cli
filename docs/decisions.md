# Design decisions

## Why LangGraph

The workflow has explicit fan-out, shared structured state, and an eventual verification loop. LangGraph makes this topology visible through a graph and `Send` map-reduce dispatch. Business logic remains in ordinary Python functions to keep it independently testable.

## Why a few roles

Planner, concurrent researchers, curator, analysis, writer, and verifier map to actual transformations of state. There are no fictitious agents that merely rename a prompt.

## Why deterministic first

Live LLM output is costly and variable. The initial planner, extraction, scoring, compression, and report rendering are deterministic and covered by offline tests. A provider-agnostic OpenAI-compatible LLM adapter can replace planning/writing while preserving Pydantic contracts.

## Why source curation precedes synthesis

Writers should not receive every page. Explicit scoring allows a run artifact to explain what was retained and why, while evidence records retain source IDs and URLs for every claim.
