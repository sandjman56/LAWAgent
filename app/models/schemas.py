from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    industry: str
    description: str
    name: Optional[str] = None
    limit: Optional[int] = Field(default=8, ge=1, le=20)


class Source(BaseModel):
    url: str
    snippet: Optional[str] = None


class Candidate(BaseModel):
    id: str
    name: str
    title: str
    organization: str
    sector: str
    years_experience: int
    location: Optional[str] = None
    summary: str
    skills: List[str]
    emails: List[str]
    links: List[str]
    sources: List[Source]
    similarity_score: int
    confidence: Literal["low", "medium", "high"]


class SearchResponse(BaseModel):
    query: Dict[str, Any]
    candidates: List[Candidate]


class SaveRequest(BaseModel):
    candidate: Candidate


class SaveResponse(BaseModel):
    status: str
    id: str
