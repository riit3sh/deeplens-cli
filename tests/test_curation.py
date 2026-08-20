from deeplens.curation import deduplicate_results, score_source
from deeplens.models import Source, SourceDecision


def test_deduplicates_tracking_and_trailing_slashes() -> None:
    assert deduplicate_results(["https://EXAMPLE.org/a/", "https://example.org/a?tracking=1"]) == [
        "https://EXAMPLE.org/a/"
    ]


def test_curation_is_explicit() -> None:
    source = Source(
        url="https://energy.gov/x",
        title="Nuclear power in India",
        domain="energy.gov",
        content="India nuclear power costs policy " * 100,
        word_count=600,
    )
    quality = score_source(
        source, "Should India expand nuclear power?", "Economics and feasibility"
    )
    assert quality.decision in SourceDecision
    assert 0 <= quality.relevance <= 1

def test_clean_academic_text_strips_toc() -> None:
    from deeplens.providers import clean_academic_text
    
    mock_string = (
        "Received 12 January 2023\n"
        "Table of Contents...... 5\n"
        "Chapter 1: Introduction ........ 6\n"
        "This is the actual substantive factual claim.\n"
        "University of Research Department\n"
        "Available online 15 March 2024"
    )
    
    cleaned = clean_academic_text(mock_string)
    assert "Table of Contents" not in cleaned
    assert "Chapter 1" not in cleaned
    assert "Received" not in cleaned
    assert "University of Research" not in cleaned
    assert "Available online" not in cleaned
    assert "This is the actual substantive factual claim." in cleaned

def test_clean_academic_text_strips_shortlinks_and_bullets_safely() -> None:
    from deeplens.providers import clean_academic_text
    
    mock_string = "• https://t.co/abc1234 Anthropic is a company"
    cleaned = clean_academic_text(mock_string)
    
    # Assert that it strips the bullet and link, but does NOT strip 'A' from 'Anthropic'
    assert cleaned == "Anthropic is a company"

