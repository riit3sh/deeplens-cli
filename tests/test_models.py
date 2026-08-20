from deeplens.models import Evidence, Source


def test_source_has_traceable_defaults() -> None:
    source = Source(url="https://example.org/a", title="A", domain="example.org")
    evidence = Evidence(
        claim="Claim",
        passage="A useful passage",
        source_id=source.id,
        source_url=source.url,
        perspective="economics",
        relevance_score=0.5,
    )
    assert source.id.startswith("src_")
    assert evidence.source_id == source.id
