"""Research pipeline roles. Web content is treated as untrusted data, never instructions."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .config import Settings
from .curation import deduplicate_results, score_source
from .models import (
    Contradiction,
    Evidence,
    Gap,
    Perspective,
    ResearchPacket,
    RunArtifact,
    RunEvent,
    Source,
    SourceDecision,
    VerificationResult,
)
from .providers import PageExtractor, SearchProvider

EventSink = Callable[[RunEvent], None]


class ResearchState(TypedDict, total=False):
    query: str
    perspectives: list[Perspective]
    sources: list[Source]
    evidence: list[Evidence]
    packets: list[ResearchPacket]
    contradictions: list[Contradiction]
    gaps: list[Gap]


async def plan_perspectives(query: str, max_perspectives: int, llm) -> list[Perspective]:
    """A dynamic structured LLM planner that tailors perspectives to the query."""
    from pydantic import BaseModel
    
    class PerspectiveList(BaseModel):
        perspectives: list[Perspective]

    system_prompt = (
        "You are an expert research planner.\n"
        f"Your job is to generate exactly {max_perspectives} dynamic, highly specific research perspectives tailored to the following query.\n"
        "Each perspective must explore a unique angle of the query (e.g., economics, safety, policies, technological viability, cultural impact, etc. depending on the context).\n"
        "You MUST constrain all perspectives to the specific intent and modifiers of the user's query. If the query asks for 'controversies', 'failures', or 'criticisms', EVERY perspective must investigate a different angle of that specific negative constraint (e.g., lawsuits, ethical debates, governance). DO NOT generate generic background or product-feature perspectives unless explicitly asked.\n"
        "For each perspective, provide 1 to 3 search queries that will yield high-quality evidence.\n"
        "DO NOT use generic hardcoded perspectives."
    )
    user_prompt = f"Query: {query}"
    
    try:
        result = await llm.complete(
            system=system_prompt,
            prompt=user_prompt,
            response_model=PerspectiveList
        )
        return result.perspectives[:max_perspectives]
    except Exception as e:
        print(f"Planner LLM failed: {e}. Falling back to heuristic planner.")
        lenses = [
            ("Benefits and demand", "Assess expected benefits, demand, and claimed outcomes."),
            ("Economics and feasibility", "Assess costs, timelines, financing, and implementation constraints."),
            ("Safety and environmental impacts", "Assess safety, waste, emissions, and environmental trade-offs."),
            ("Policy and alternatives", "Compare policy options, equity implications, and credible alternatives."),
            ("Evidence quality and uncertainty", "Identify assumptions, dated evidence, and unresolved questions."),
        ]
        return [
            Perspective(name=name, objective=objective, queries=[f"{query} {name}"])
            for name, objective in lenses[:max_perspectives]
        ]


async def synthesize_report(artifact: RunArtifact, llm) -> tuple[str, str]:
    """Dynamically write the executive summary and conclusion based on findings."""
    from pydantic import BaseModel, Field
    
    class Synthesis(BaseModel):
        executive_summary: str
        conclusion: str = Field(
            ...,
            min_length=20,
            description="STRICTLY REQUIRED: A 2-3 sentence concluding paragraph that directly answers the user's question, synthesizing the findings and acknowledging contradictions."
        )
        
    system_prompt = (
        "You are an expert research synthesizer.\n"
        "Your task is to write a concise Executive Summary and Conclusion based on the gathered evidence.\n"
        "The Conclusion field is STRICTLY REQUIRED. You MUST write a 2-3 sentence concluding paragraph that directly answers the user's original question by synthesizing the extracted evidence, acknowledging any contradictions.\n"
        "DO NOT invent new facts. ONLY use the provided findings."
    )
    
    findings_text = "\n".join([
        f"Perspective: {packet.perspective}\n" + "\n".join(f"- {f}" for f in packet.findings)
        for packet in artifact.packets
    ])
    
    user_prompt = f"User Question: {artifact.query}\n\nFindings:\n{findings_text}"
    
    try:
        result = await llm.complete(
            system=system_prompt,
            prompt=user_prompt,
            response_model=Synthesis
        )
        return result.executive_summary, result.conclusion
    except Exception as e:
        print(f"Synthesizer LLM failed: {e}")
        return ("", "")


def _passages(source: Source, question: str) -> list[str]:
    terms = {w.lower() for w in question.split() if len(w) > 3}
    sentences = re.split(r"(?<=[.!?])\s+", source.content)
    boilerplate = {
        "skip to main content",
        "open navigation",
        "privacy policy",
        "sign in",
        "cookie",
        "request free sample",
        "get instant access",
        "market analysis & forecast",
    }
    
    def is_spam(sentence: str) -> bool:
        urls = len(re.findall(r'https?://', sentence))
        exts = len(re.findall(r'\b(?:pdf|docx|xlsx|pptx)\b', sentence, re.IGNORECASE))
        courses = len(re.findall(r'\b[A-Z]{2,4}\s*\d{3,4}\b', sentence))
        dates = len(re.findall(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b', sentence))
        return (urls + exts + courses + dates) >= 2

    valid_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence.split()) < 10:
            continue
        if any(item in sentence.lower() for item in boilerplate):
            continue
        if is_spam(sentence):
            continue
        valid_sentences.append(sentence)
        
    ranked = sorted(
        valid_sentences,
        key=lambda sentence: sum(term in sentence.lower() for term in terms),
        reverse=True,
    )
    return [sentence for sentence in ranked[:5] if len(sentence) >= 40]


async def extract_evidence(passages: list[str], query: str, perspective_name: str, llm) -> list[str]:
    from pydantic import BaseModel
    
    class EvidenceList(BaseModel):
        claims: list[str]
        
    if not passages:
        return []
        
    system_prompt = (
        "You are a strict academic evidence extractor.\n"
        "You must evaluate the actual meaning of the text. If the user asks for 'controversies', the text MUST contain an allegation, scandal, or dispute. DO NOT extract course descriptions, directory listings, or codes of conduct unless they are explicitly part of a cited controversy. If the text is benign boilerplate, return an empty list.\n"
        "You MUST only extract complete, grammatically correct sentences that contain a definitive factual claim or finding. DO NOT extract rhetorical questions, section headers, fragmented clauses, or table of contents entries. If a claim is not a complete sentence, you must ignore it.\n"
        "Extract ONLY the substantive factual claims directly answering the query."
    )
    
    user_prompt = f"Query: {query}\nPerspective: {perspective_name}\n\nPassages:\n" + "\n".join(f"- {p}" for p in passages)
    
    try:
        result = await llm.complete(
            system=system_prompt,
            prompt=user_prompt,
            response_model=EvidenceList
        )
        return result.claims
    except Exception as e:
        print(f"Extractor LLM failed: {e}")
        return passages[:2]

class ResearchEngine:
    def __init__(
        self,
        settings: Settings,
        search: SearchProvider,
        extractor: PageExtractor,
        event_sink: EventSink | None = None,
    ) -> None:
        self.settings, self.search, self.extractor, self.event_sink = (
            settings,
            search,
            extractor,
            event_sink,
        )

    def _event(self, name: str, **data: object) -> None:
        if self.event_sink:
            self.event_sink(RunEvent(name=name, data=data))

    async def _research_perspective(
        self, query: str, perspective: Perspective, llm
    ) -> tuple[list[Source], list[Evidence], ResearchPacket]:
        self._event("researcher_started", perspective=perspective.name)
        results = await asyncio.gather(
            *(
                self.search.search(q, limit=self.settings.max_sources_per_perspective)
                for q in perspective.queries
            ),
            return_exceptions=True,
        )
        search_results = [
            item for group in results if not isinstance(group, Exception) for item in group
        ]
        unique = deduplicate_results([item.url for item in search_results])[
            : self.settings.max_sources_per_perspective
        ]
        selected = {item.url: item for item in search_results}
        fetched = await asyncio.gather(
            *(self.extractor.extract(selected[url]) for url in unique), return_exceptions=True
        )
        sources: list[Source] = []
        evidence: list[Evidence] = []
        for item in fetched:
            if isinstance(item, Exception):
                self._event("source_failed", perspective=perspective.name, error=str(item))
                continue
            item.quality = score_source(item, query, perspective.name)
            sources.append(item)
            self._event("source_found", perspective=perspective.name, source_id=item.id)
            if item.quality.decision == SourceDecision.REJECT:
                continue
                
            raw_passages = _passages(item, query)
            extracted_claims = await extract_evidence(raw_passages, query, perspective.name, llm)
            
            from pydantic import ValidationError
            for claim in extracted_claims:
                try:
                    evidence.append(
                        Evidence(
                            claim=claim,
                            passage=claim,
                            source_id=item.id,
                            source_url=item.url,
                            perspective=perspective.name,
                            relevance_score=item.quality.relevance,
                            confidence=item.quality.authority,
                        )
                    )
                except ValidationError as e:
                    self._event("evidence_rejected", reason=str(e))
                    continue
        packet = ResearchPacket(
            perspective=perspective.name,
            findings=[e.claim for e in evidence[:5]],
            evidence_ids=[e.id for e in evidence],
            source_ids=[s.id for s in sources],
            uncertainties=["No accepted evidence retrieved."] if not evidence else [],
        )
        self._event(
            "researcher_completed",
            perspective=perspective.name,
            sources=len(sources),
            evidence=len(evidence),
        )
        return sources, evidence, packet

    async def run(self, query: str) -> RunArtifact:
        from .llm import OpenAILLM, StructuredLLM
        llm = OpenAILLM(self.settings)

        started, started_tick = datetime.now(UTC), perf_counter()
        artifact = RunArtifact(
            query=query,
            started_at=started,
            llm_info={"planner": "heuristic", "writer": "deterministic", "analyzer": "llm"},
        )

        def collect(event: RunEvent) -> None:
            artifact.events.append(event)
            if original_sink:
                original_sink(event)

        original_sink, self.event_sink = self.event_sink, collect
        try:
            collect(RunEvent(name="run_started"))
            artifact.perspectives = await plan_perspectives(query, self.settings.max_perspectives, llm)
            collect(
                RunEvent(
                    name="planner_completed", data={"perspectives": len(artifact.perspectives)}
                )
            )
            tasks = [
                self._research_perspective(query, perspective, llm)
                for perspective in artifact.perspectives
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    self._event("perspective_crashed", error=str(res))
                    continue
                sources, evidence, packet = res
                
                known_urls = {source.url.rstrip("/") for source in artifact.sources}
                kept_sources = []
                for source in sources:
                    canonical_url = source.url.rstrip("/")
                    if canonical_url not in known_urls:
                        known_urls.add(canonical_url)
                        kept_sources.append(source)
                kept_ids = {source.id for source in kept_sources}
                artifact.sources.extend(kept_sources)
                artifact.evidence.extend(item for item in evidence if item.source_id in kept_ids)
                packet.evidence_ids = [
                    item.id for item in artifact.evidence if item.perspective == packet.perspective
                ]
                packet.source_ids = [source.id for source in kept_sources]
                packet.findings = [
                    item.claim for item in artifact.evidence if item.id in packet.evidence_ids
                ][:5]
                artifact.packets.append(packet)
            
            artifact.contradictions = await find_contradictions(artifact.evidence, llm)
            artifact.gaps = find_gaps(artifact.perspectives, artifact.packets, artifact.evidence)
            
            # Synthesize report components dynamically
            exec_summary, conclusion = await synthesize_report(artifact, llm)
            artifact.executive_summary = exec_summary
            artifact.conclusion = conclusion

            artifact.completed_at = datetime.now(UTC)
            artifact.timings_seconds["total"] = round(perf_counter() - started_tick, 3)
            collect(
                RunEvent(
                    name="run_completed",
                    data={"sources": len(artifact.sources), "evidence": len(artifact.evidence)},
                )
            )
            return artifact
        finally:
            self.event_sink = original_sink

    def build_langgraph(self) -> StateGraph[ResearchState]:
        """Expose the workflow topology for API users; run() uses the same concurrent worker semantics."""
        graph: StateGraph[ResearchState] = StateGraph(ResearchState)
        
        async def plan_node(state):
            from .llm import OpenAILLM
            llm = OpenAILLM(self.settings)
            perspectives = await plan_perspectives(state["query"], self.settings.max_perspectives, llm)
            return {"perspectives": perspectives}
            
        graph.add_node(
            "plan",
            plan_node,
        )
        graph.add_node("research", lambda state: state)
        graph.add_edge(START, "plan")
        graph.add_conditional_edges(
            "plan",
            lambda state: [
                Send("research", {"query": state["query"], "perspective": p})
                for p in state["perspectives"]
            ],
        )
        graph.add_edge("research", END)
        return graph


async def find_contradictions(evidence: list[Evidence], llm) -> list[Contradiction]:
    """Report only direct negation of the same proposition using strict logical gates via LLM."""
    from pydantic import BaseModel
    
    class ContradictionList(BaseModel):
        contradictions: list[Contradiction]

    found: list[Contradiction] = []
    
    # We batch pairs to avoid too many LLM calls. For simplicity, we can do it pairwise.
    # But since it's an LLM, we can send a list of claims and ask it to find strict contradictions.
    if len(evidence) < 2:
        return []
        
    system_prompt = (
        "You are a strict logical contradiction analyzer.\n"
        "A contradiction ONLY exists if Claim A and Claim B cannot both be true simultaneously. "
        "If Claim A is true, Claim B must mathematically or factually be false.\n\n"
        "Does Claim A explicitly disprove Claim B? If no, return an empty list.\n\n"
        "EXAMPLES:\n"
        "Example 1 (Not a contradiction):\n"
        "Claim A says EVs reduce emissions. Claim B says EVs require grid power.\n"
        "Result: None (empty list)\n\n"
        "Example 2 (Not a contradiction):\n"
        "Claim A says adoption is at 5%. Claim B says adoption will reach 20% by 2030.\n"
        "Result: None (empty list)\n\n"
        "Example 3 (Actual contradiction):\n"
        "Claim A says the EV market share in India is currently 2%. Claim B says the EV market share in India is currently 15%.\n"
        "Result: Output the Contradiction Pydantic model.\n\n"
        "DO NOT flag statements that agree with each other or discuss different metrics."
    )
    
    # We will format all claims and ask the LLM to identify pairs
    claims_text = "\n".join([f"ID: {e.id} | Source: {e.source_id} | Claim: {e.claim}" for e in evidence])
    user_prompt = f"Analyze the following claims and extract ONLY strict factual contradictions between them. Use the exact Source and Claim text provided.\n\n{claims_text}"
    
    try:
        result = await llm.complete(
            system=system_prompt,
            prompt=user_prompt,
            response_model=ContradictionList
        )
        # Verify the LLM didn't hallucinate source IDs that don't exist
        valid_source_ids = {e.source_id for e in evidence}
        for c in result.contradictions:
            if c.source_a in valid_source_ids and c.source_b in valid_source_ids:
                found.append(c)
    except Exception as e:
        print(f"Contradiction LLM failed: {e}")
        
    return found


def find_gaps(
    perspectives: list[Perspective], packets: list[ResearchPacket], evidence: list[Evidence]
) -> list[Gap]:
    packets_by_name = {packet.perspective: packet for packet in packets}
    gaps = [
        Gap(
            question=f"What evidence addresses {perspective.name}?",
            reason="No accepted evidence was retrieved.",
            related_perspective=perspective.name,
        )
        for perspective in perspectives
        if not packets_by_name.get(perspective.name)
        or not packets_by_name[perspective.name].evidence_ids
    ]
    by_claim_source = {item.source_id for item in evidence}
    if len(by_claim_source) < 2 and evidence:
        gaps.append(
            Gap(
                question="Can the central findings be independently corroborated?",
                reason="Evidence comes from fewer than two sources.",
            )
        )
    return gaps


def verify_report(markdown: str, artifact: RunArtifact) -> VerificationResult:
    issues = []
    for source in artifact.sources:
        if source.quality and source.quality.decision == SourceDecision.KEEP:
            citation = f"[{artifact.sources.index(source) + 1}]"
            if citation not in markdown:
                from .models import VerificationIssue

                issues.append(
                    VerificationIssue(
                        statement=source.title, reason="Accepted source lacks a report citation."
                    )
                )
    return VerificationResult(verdict="REVISE" if issues else "PASS", issues=issues)
