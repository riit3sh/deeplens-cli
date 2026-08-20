from deeplens.curation import score_source
from deeplens.models import Evidence, Source, SourceDecision
from deeplens.providers import _article_text
from deeplens.research import find_contradictions


def test_html_extraction_excludes_navigation_and_keeps_article() -> None:
    html = "<header>Skip to main content</header><nav>Open navigation menu</nav><article><p>This is a detailed factual article sentence with useful evidence for the research question.</p></article><footer>Privacy policy</footer>"
    assert "Skip" not in _article_text(html)
    assert "detailed factual article" in _article_text(html)


def test_social_video_sources_are_rejected() -> None:
    source = Source(
        url="https://youtube.com/watch?v=x",
        title="Video",
        domain="youtube.com",
        content="India nuclear evidence " * 30,
        word_count=90,
    )
    assert score_source(source, "India nuclear power", "Benefits").decision == SourceDecision.REJECT


def test_contradiction_does_not_flag_unrelated_negative_claims() -> None:
    left = Evidence(
        claim="Nuclear capacity may increase by 20 percent under the proposal.",
        passage="x",
        source_id="a",
        source_url="https://a",
        perspective="policy",
        relevance_score=1,
    )
    right = Evidence(
        claim="Land acquisition is not complete for several proposed sites.",
        passage="x",
        source_id="b",
        source_url="https://b",
        perspective="policy",
        relevance_score=1,
    )
    assert find_contradictions([left, right]) == []
