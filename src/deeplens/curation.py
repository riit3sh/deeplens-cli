"""Explicit, inspectable source curation rather than opaque prompt filtering."""

from __future__ import annotations

from urllib.parse import urlparse

from .models import Source, SourceDecision, SourceQuality

HIGH_AUTHORITY_SUFFIXES = (".gov", ".edu", ".int")
HIGH_AUTHORITY_DOMAINS = {"iea.org", "worldbank.org", "ipcc.ch", "nature.com", "science.org"}
LOW_EVIDENCE_DOMAINS = {"youtube.com", "www.youtube.com", "facebook.com", "www.facebook.com"}


def deduplicate_results(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        canonical = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
        if canonical not in seen:
            seen.add(canonical)
            unique.append(url)
    return unique


def score_source(source: Source, question: str, perspective: str) -> SourceQuality:
    haystack = f"{source.title} {source.content[:4000]}".lower()
    terms = {
        word.lower().strip(".,?!:;()")
        for word in (question + " " + perspective).split()
        if len(word) > 3
    }
    relevance = min(1.0, sum(term in haystack for term in terms) / max(3, len(terms) * 0.5))
    domain = source.domain.lower()
    if domain in LOW_EVIDENCE_DOMAINS:
        return SourceQuality(
            relevance=relevance,
            authority=0.1,
            freshness=0.5,
            directness=0.0,
            decision=SourceDecision.REJECT,
            reason="Social/video platform content is not accepted as primary research evidence.",
        )
    sales_markers = ("request free sample", "get instant access", "market analysis & forecast")
    if sum(marker in haystack for marker in sales_markers) >= 2:
        return SourceQuality(
            relevance=relevance,
            authority=0.15,
            freshness=0.5,
            directness=0.1,
            decision=SourceDecision.REJECT,
            reason="Commercial report landing page, not a citable primary analysis.",
        )
    authority = (
        0.85
        if domain.endswith(HIGH_AUTHORITY_SUFFIXES) or domain in HIGH_AUTHORITY_DOMAINS
        else 0.55
    )
    freshness = 0.7 if source.published_at else 0.5
    directness = min(1.0, source.word_count / 800) if source.content else 0.2
    average = relevance * 0.45 + authority * 0.25 + freshness * 0.1 + directness * 0.2
    if average >= 0.62:
        decision, reason = (
            SourceDecision.KEEP,
            f"Weighted score {average:.2f}; sufficiently relevant and usable.",
        )
    elif average >= 0.45:
        decision, reason = (
            SourceDecision.UNCERTAIN,
            f"Weighted score {average:.2f}; retain only if corroborated.",
        )
    else:
        decision, reason = (
            SourceDecision.REJECT,
            f"Weighted score {average:.2f}; weak relevance or usable content.",
        )
    return SourceQuality(
        relevance=relevance,
        authority=authority,
        freshness=freshness,
        directness=directness,
        decision=decision,
        reason=reason,
    )
