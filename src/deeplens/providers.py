"""Small provider interfaces; all network dependencies are injectable."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .config import Settings
from .models import SearchResult, Source


def clean_academic_text(text: str) -> str:
    """Strictly strip TOCs, academic front-matter, and metadata."""
    import re
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        # Strip Table of Contents (e.g., "Introduction ............ 5")
        if re.search(r'\.{3,}\s*\d+$', line_stripped):
            continue
        # Strip Academic Front-matter
        if re.search(r'^(Received\s+\d+|Accepted\s+\d+|Available online\s+|Copyright\s+(©|\(c\)))', line_stripped, flags=re.IGNORECASE):
            continue
        # Author affiliations heuristic: Starts with University, Department, etc.
        if re.match(r'^(Department of|University of|Faculty of)', line_stripped, flags=re.IGNORECASE):
            continue
        # Strip breadcrumbs and share links
        if re.match(r'^(Back to\s+|Share this article|Share on\s+|Click to share)', line_stripped, flags=re.IGNORECASE):
            continue
            
        # Strip Wikipedia [edit] tags and common UI text
        line_stripped = re.sub(r'\[edit\]', '', line_stripped, flags=re.IGNORECASE)
        line_stripped = re.sub(r'\b(Copy link|Click here|Read more)\b', '', line_stripped, flags=re.IGNORECASE)
        
        # Strip local file paths and document extensions indicating metadata spam
        if re.search(r'[A-Za-z]:\\[^\\]+', line_stripped) or re.search(r'\.(docx|pdf)\b', line_stripped, flags=re.IGNORECASE):
            continue
            
        # Strip Figure/Table captions and Page X of Y artifacts
        if re.match(r'^(Table\s+[\d\-\.]+:?|Fig\.|Figure\s+[\d\-\.]+:?|Page\s+\d+\s+of\s+\d+)', line_stripped, flags=re.IGNORECASE):
            continue
        
        # Remove bullet points (e.g. •, -, *) at the start of a line
        line_stripped = re.sub(r'^[\u2022\-\*]\s*', '', line_stripped)
        # Strip shortlinks and media links, stopping at whitespace so we don't drop letters
        line_stripped = re.sub(r'(?:https?://)?(?:pic\.twitter\.com|t\.co|bit\.ly|tinyurl\.com)/\S+', '', line_stripped)
        line_stripped = line_stripped.strip()
        
        if not line_stripped:
            continue
        cleaned_lines.append(line_stripped)
    return "\n".join(cleaned_lines)

def _complete_text(text: str, limit: int = 80_000) -> str:
    """Bound content without cutting a word or sentence halfway through."""
    text = clean_academic_text(text)
    text = "".join(
        character for character in text if character.isprintable() or character.isspace()
    )
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    boundary = max(text.rfind(mark, 0, limit) for mark in ".!?")
    return text[: boundary + 1 if boundary > limit // 2 else limit].strip()


import re
import fitz
import trafilatura

def _article_text(html: str | bytes) -> str:
    extracted = trafilatura.extract(
        html,
        include_links=False,
        include_images=False,
        include_tables=False,
        no_fallback=False
    )
    if not extracted:
        return ""
    # Strip wikipedia-style citations like [1] or [1]: 221
    clean_text = re.sub(r'\[\d+\](:\s*\d+)?', '', extracted)
    return _complete_text(clean_text)


class SearchProvider(Protocol):
    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]: ...


class PageExtractor(Protocol):
    async def extract(self, result: SearchResult) -> Source: ...


class TavilySearchProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.tavily_api_key:
            raise ValueError("TAVILY_API_KEY is required for live web research.")
        self._key, self._client, self._own_client = settings.tavily_api_key, client, client is None
        self._timeout = settings.request_timeout_seconds

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self._key,
                    "query": query,
                    "max_results": limit,
                    "search_depth": "advanced",
                },
            )
            response.raise_for_status()
            return [
                SearchResult(
                    url=item["url"],
                    title=item.get("title", item["url"]),
                    snippet=item.get("content", ""),
                )
                for item in response.json().get("results", [])
            ]
        finally:
            if self._own_client:
                await client.aclose()


class HttpxPageExtractor:
    """Conservative fallback extractor for public HTML pages and PDFs."""

    def __init__(self, settings: Settings) -> None:
        self._timeout, self._retries = settings.request_timeout_seconds, settings.retry_count

    async def extract(self, result: SearchResult) -> Source:
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, follow_redirects=True
                ) as client:
                    response = await client.get(
                        result.url, headers={"User-Agent": "DeepLens/0.1 research client"}
                    )
                    response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                
                # Check for PDF
                if "pdf" in content_type or "octet-stream" in content_type or result.url.lower().endswith(".pdf"):
                    try:
                        doc = fitz.open(stream=response.content, filetype="pdf")
                        text_blocks = [page.get_text() for page in doc]
                        raw_content = "\n".join(text_blocks)
                        # Strip citations
                        clean_content = re.sub(r'\[\d+\](:\s*\d+)?', '', raw_content)
                        content = _complete_text(clean_content)
                    except Exception as e:
                        raise RuntimeError(f"PDF extraction failed: {e}")
                else:
                    content = _article_text(response.content)
                    
                if (
                    not content
                    or sum(char.isalpha() for char in content) / max(1, len(content)) < 0.35
                ):
                    raise RuntimeError("Page did not yield readable article text.")
                return Source(
                    url=result.url,
                    title=result.title,
                    domain=urlparse(result.url).netloc,
                    content=content,
                    word_count=len(content.split()),
                    published_at=result.published_at,
                )
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"Could not fetch {result.url}: {last_error}")


class FirecrawlExtractor:
    def __init__(self, settings: Settings) -> None:
        if not settings.firecrawl_api_key:
            raise ValueError("FIRECRAWL_API_KEY is required for Firecrawl extraction.")
        self._key, self._timeout = settings.firecrawl_api_key, settings.request_timeout_seconds

    async def extract(self, result: SearchResult) -> Source:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {self._key}"},
                json={"url": result.url, "formats": ["markdown"]},
            )
            response.raise_for_status()
        data = response.json().get("data", {})
        content = data.get("markdown", "")
        metadata = data.get("metadata", {})
        published = metadata.get("publishedTime")
        return Source(
            url=result.url,
            title=metadata.get("title") or result.title,
            domain=urlparse(result.url).netloc,
            content=_complete_text(content),
            word_count=len(content.split()),
            published_at=datetime.fromisoformat(published) if published else result.published_at,
        )


class StaticSearchProvider:
    """Offline provider used by examples and tests."""

    def __init__(self, results: dict[str, list[SearchResult]]) -> None:
        self.results = results

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        return self.results.get(query, [])[:limit]
