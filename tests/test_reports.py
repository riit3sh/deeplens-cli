from datetime import UTC, datetime

from deeplens.models import (
    Evidence,
    ResearchPacket,
    RunArtifact,
    Source,
    SourceDecision,
    SourceQuality,
)
from deeplens.reports import export_run, render_markdown


def test_report_and_artifacts_export(tmp_path) -> None:
    source = Source(
        url="https://example.org",
        title="Example",
        domain="example.org",
        content="credible",
        word_count=1,
        quality=SourceQuality(
            relevance=0.9,
            authority=0.7,
            freshness=0.5,
            directness=0.6,
            decision=SourceDecision.KEEP,
            reason="ok",
        ),
    )
    evidence = Evidence(
        claim="A supported claim.",
        passage="A supported claim.",
        source_id=source.id,
        source_url=source.url,
        perspective="Policy",
        relevance_score=0.9,
    )
    artifact = RunArtifact(
        query="A question",
        started_at=datetime.now(UTC),
        sources=[source],
        evidence=[evidence],
        packets=[
            ResearchPacket(
                perspective="Policy",
                findings=[evidence.claim],
                evidence_ids=[evidence.id],
                source_ids=[source.id],
            )
        ],
    )
    assert "[1]" in render_markdown(artifact)
    output = export_run(artifact, tmp_path)
    assert (output / "report.pdf").exists()
    assert (output / "run.json").exists()
