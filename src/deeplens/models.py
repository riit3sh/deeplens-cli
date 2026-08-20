"""Typed state exchanged between every stage of a research run."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class SourceDecision(StrEnum):
    KEEP = "keep"
    REJECT = "reject"
    UNCERTAIN = "uncertain"


class SourceQuality(BaseModel):
    relevance: float = Field(ge=0, le=1)
    authority: float = Field(ge=0, le=1)
    freshness: float = Field(ge=0, le=1)
    directness: float = Field(ge=0, le=1)
    decision: SourceDecision
    reason: str


class Source(BaseModel):
    id: str = Field(default_factory=lambda: new_id("src"))
    url: str
    title: str
    domain: str
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: str = ""
    word_count: int = 0
    source_type: str = "web"
    quality: SourceQuality | None = None


class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str = ""
    published_at: datetime | None = None


class Perspective(BaseModel):
    id: str = Field(default_factory=lambda: new_id("persp"))
    name: str
    objective: str
    queries: list[str] = Field(default_factory=list)


from pydantic import BaseModel, Field, field_validator
import re

class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ev"))
    claim: str
    passage: str
    source_id: str
    source_url: str
    perspective: str
    relevance_score: float = Field(ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator('claim')
    @classmethod
    def validate_claim(cls, v: str) -> str:
        v = v.strip()
        if v.endswith('?'):
            raise ValueError("Claim cannot be a rhetorical question.")
        if len(v.split()) < 6:
            raise ValueError("Claim is too short (under 6 words).")
        if not re.match(r'^[A-Z0-9]', v):
            raise ValueError("Claim must start with a capital letter or number.")
        if len(re.findall(r'[><|/]', v)) > 3:
            raise ValueError("Claim contains excessive UI/special characters.")
        return v


class ResearchPacket(BaseModel):
    perspective: str
    findings: list[str]
    evidence_ids: list[str]
    uncertainties: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class Contradiction(BaseModel):
    claim_a: str
    source_a: str
    claim_b: str
    source_b: str
    explanation: str
    severity: str = "low"


class Gap(BaseModel):
    question: str
    reason: str
    related_perspective: str | None = None


class VerificationIssue(BaseModel):
    statement: str
    reason: str
    severity: str = "warning"


class VerificationResult(BaseModel):
    verdict: str
    issues: list[VerificationIssue] = Field(default_factory=list)


class RunEvent(BaseModel):
    name: str
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)


class RunArtifact(BaseModel):
    query: str
    started_at: datetime
    completed_at: datetime | None = None
    executive_summary: str | None = None
    conclusion: str | None = None
    perspectives: list[Perspective] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    packets: list[ResearchPacket] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    events: list[RunEvent] = Field(default_factory=list)
    timings_seconds: dict[str, float] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    llm_info: dict[str, str] = Field(default_factory=dict)
