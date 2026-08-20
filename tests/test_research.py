import asyncio

from deeplens.config import Settings
from deeplens.models import SearchResult, Source
from deeplens.providers import StaticSearchProvider
from deeplens.research import ResearchEngine


class StubExtractor:
    async def extract(self, result: SearchResult) -> Source:
        await asyncio.sleep(0.01)
        text = "Nuclear power in India has evidence on costs, policy, and safety. " * 20
        return Source(
            url=result.url,
            title=result.title,
            domain="example.org",
            content=text,
            word_count=len(text.split()),
        )


async def test_research_runs_perspectives_concurrently() -> None:
    question = "Should India significantly expand nuclear power by 2040?"
    queries = {
        f"{question} {lens}": [SearchResult(url=f"https://example.org/{i}", title=f"Source {i}")]
        for i, lens in enumerate(
            [
                "Benefits and demand",
                "Economics and feasibility",
                "Safety and environmental impacts",
                "Policy and alternatives",
            ]
        )
    }
    engine = ResearchEngine(
        Settings(max_perspectives=4), StaticSearchProvider(queries), StubExtractor()
    )
    artifact = await engine.run(question)
    assert len(artifact.perspectives) == 4
    assert artifact.evidence
    assert artifact.completed_at is not None

async def test_find_contradictions_rejects_complementary_statements() -> None:
    from deeplens.models import Evidence, Contradiction
    from deeplens.research import find_contradictions
    
    class MockLLM:
        async def complete(self, *, system: str, prompt: str, response_model):
            # Assert that the system prompt defines strict logic
            assert "A contradiction ONLY exists if Claim A and Claim B cannot both be true simultaneously" in system
            assert "Example 1 (Not a contradiction):" in system
            # Mock LLM returning empty list because statements are complementary
            return response_model(contradictions=[])
            
    evidence = [
        Evidence(
            id="e1",
            claim="EVs have no tailpipe emissions.",
            passage="EVs have no tailpipe emissions.",
            source_id="s1",
            source_url="http://x",
            perspective="Env",
            relevance_score=1.0,
            confidence=1.0
        ),
        Evidence(
            id="e2",
            claim="EVs reduce nitrogen oxide by 17%.",
            passage="EVs reduce nitrogen oxide by 17%.",
            source_id="s2",
            source_url="http://y",
            perspective="Env",
            relevance_score=1.0,
            confidence=1.0
        )
    ]
    
    contradictions = await find_contradictions(evidence, MockLLM())
    assert len(contradictions) == 0

