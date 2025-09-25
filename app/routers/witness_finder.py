from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from app.models.schemas import (
    Candidate,
    DeleteResponse,
    QueryInfo,
    SaveRequest,
    SaveResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.openai_client import summarize_to_candidates
from app.services.perplexity_client import PerplexityError, search_web
from app.services.ranking import score_candidates
from app.store import saved_witnesses

logger = logging.getLogger("lawagent.witness_finder")

router = APIRouter()


def _normalize_candidate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    normalized = dict(payload)
    if "match_strength" not in normalized:
        for key in ("matchStrength", "match_score", "score", "relevance"):
            if key in normalized:
                normalized["match_strength"] = normalized[key]
                break

    if "years_experience" not in normalized:
        for key in ("yearsExperience", "experience_years", "experience"):
            if key in normalized:
                normalized["years_experience"] = normalized[key]
                break

    if "sources" in normalized and isinstance(normalized["sources"], list):
        normalized["sources"] = [item for item in normalized["sources"] if isinstance(item, dict)]

    return normalized


@router.post("/search", response_model=SearchResponse)
async def search_candidates(request: SearchRequest) -> SearchResponse:
    limit = request.limit or 8
    query = QueryInfo(industry=request.industry, description=request.description, name=request.name)

    search_terms = f"{request.industry} expert witness {request.description}"
    if request.name:
        search_terms = f"{search_terms} {request.name}"

    try:
        hits = await search_web(search_terms, limit=min(20, max(limit * 2, 10)))
    except PerplexityError as exc:
        logger.warning("Perplexity search failed: %s", exc)
        return SearchResponse(query=query, candidates=[])

    if not hits:
        return SearchResponse(query=query, candidates=[])

    user_context = request.model_dump(exclude_none=True)
    try:
        candidate_payloads = await summarize_to_candidates(hits, user_context)
    except ValueError as exc:
        logger.warning("OpenAI summarization failed: %s", exc)
        return SearchResponse(query=query, candidates=[])

    candidates: List[Candidate] = []
    for payload in candidate_payloads:
        normalized = _normalize_candidate_payload(payload)
        if not normalized.get("name"):
            continue
        try:
            candidate = Candidate.model_validate(normalized)
        except Exception as exc:  # pragma: no cover - defensive against schema drift
            logger.debug("Skipping candidate due to validation error: %s", exc)
            continue
        candidates.append(candidate)

    if not candidates:
        return SearchResponse(query=query, candidates=[])

    query_text = f"{request.industry}. {request.description}. Name hint: {request.name or 'None'}"
    try:
        ranked = await score_candidates(query_text, candidates)
    except ValueError as exc:
        logger.warning("Embedding scoring failed: %s", exc)
        ranked = candidates
    top_candidates = ranked[:limit]

    return SearchResponse(query=query, candidates=top_candidates)


@router.post("/save", response_model=SaveResponse)
async def save_candidate(request: SaveRequest) -> SaveResponse:
    candidate = request.candidate
    candidate_id, duplicate = await saved_witnesses.save_candidate(candidate)
    status = "duplicate" if duplicate else "ok"
    return SaveResponse(status=status, id=candidate_id)


@router.get("/saved", response_model=List[Candidate])
async def get_saved_candidates() -> List[Candidate]:
    return await saved_witnesses.load_saved()


@router.delete("/saved/{candidate_id}", response_model=DeleteResponse)
async def delete_candidate(candidate_id: str) -> DeleteResponse:
    removed = await saved_witnesses.delete_candidate(candidate_id)
    return DeleteResponse(status="ok" if removed else "not_found")
