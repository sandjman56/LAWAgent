from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    url: str
    snippet: str = ""

    @field_validator("url", mode="before")
    @classmethod
    def _strip_url(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("snippet", mode="before")
    @classmethod
    def _strip_snippet(cls, value: str) -> str:
        return (value or "").strip()


class Candidate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    title: str | None = None
    organization: str | None = None
    sector: str | None = None
    years_experience: int | None = None
    location: str | None = None
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    similarity_score: int = 0
    confidence: Literal["low", "medium", "high"] = "low"
    match_strength: float | None = Field(default=None, exclude=True)

    @field_validator("name", "title", "organization", "sector", "location", "summary", mode="before")
    @classmethod
    def _strip_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("skills", "emails", "links", mode="before")
    @classmethod
    def _ensure_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @field_validator("similarity_score", mode="after")
    @classmethod
    def _clamp_similarity(cls, value: int) -> int:
        return max(0, min(100, int(value)))

    @field_validator("years_experience", mode="before")
    @classmethod
    def _coerce_years(cls, value):
        if value in (None, "", "unknown"):
            return None
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return None
        return max(0, min(80, number))


class SearchRequest(BaseModel):
    industry: str = Field(..., min_length=2)
    description: str = Field(..., min_length=4)
    name: str | None = None
    limit: int | None = Field(default=8, ge=1, le=20)

    @field_validator("industry", "description", "name", mode="before")
    @classmethod
    def _strip_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class QueryInfo(BaseModel):
    industry: str
    description: str
    name: str | None = None


class SearchResponse(BaseModel):
    query: QueryInfo
    candidates: list[Candidate]


class SaveRequest(BaseModel):
    candidate: Candidate


class SaveResponse(BaseModel):
    status: Literal["ok", "duplicate"]
    id: str


class DeleteResponse(BaseModel):
    status: Literal["ok", "not_found"]
