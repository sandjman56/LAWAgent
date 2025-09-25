from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.models.schemas import Candidate, SaveRequest, SaveResponse, SearchRequest, SearchResponse
from app.services.openai_client import summarize_to_candidates
from app.services.perplexity_client import PerplexityAPIError, search_web
from app.services.ranking import score_candidates
from app.store import saved_witnesses

logger = logging.getLogger("lawagent.witness_finder")

router = APIRouter(prefix="/api/witness_finder", tags=["witness_finder"])


def _normalize_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(candidate)
    normalized.setdefault("id", str(uuid.uuid4()))
    normalized["title"] = str(normalized.get("title") or "")
    normalized["organization"] = str(normalized.get("organization") or "")
    normalized["sector"] = str(normalized.get("sector") or "")
    try:
        normalized["years_experience"] = int(float(normalized.get("years_experience", 0) or 0))
    except (TypeError, ValueError):
        normalized["years_experience"] = 0
    normalized["summary"] = str(normalized.get("summary") or "")

    def _clean_list(values: Any) -> List[str]:
        if not values:
            return []
        if isinstance(values, str):
            values = [values]
        if isinstance(values, (list, tuple, set)):
            return [str(item).strip() for item in values if str(item).strip()]
        return []

    normalized["skills"] = _clean_list(normalized.get("skills"))
    normalized["emails"] = _clean_list(normalized.get("emails"))
    normalized["links"] = _clean_list(normalized.get("links"))

    sources: List[Dict[str, Any]] = []
    for source in normalized.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or source.get("link") or "").strip()
        if not url:
            continue
        snippet = source.get("snippet") or source.get("summary") or ""
        sources.append({"url": url, "snippet": str(snippet) if snippet is not None else None})
    normalized["sources"] = sources
    try:
        normalized["similarity_score"] = int(normalized.get("similarity_score", 0) or 0)
    except (TypeError, ValueError):
        normalized["similarity_score"] = 0
    confidence = str(normalized.get("confidence") or "low").lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    normalized["confidence"] = confidence
    return normalized


@router.get("", include_in_schema=False)
async def witness_finder_hint() -> Dict[str, str]:
    return {"service": "witness_finder", "hint": "Use /api/witness_finder/search for POST"}


@router.post("/search", response_model=SearchResponse)
async def search_candidates(request: SearchRequest) -> SearchResponse:
    limit = request.limit or 8
    query_payload = request.model_dump()

    search_terms = f"{request.industry} expert witness {request.description}".strip()
    if request.name:
        search_terms = f"{search_terms} {request.name}".strip()

    try:
        web_hits = await search_web(search_terms, limit=min(25, max(limit * 2, 12)))
    except PerplexityAPIError as exc:
        logger.warning("Perplexity search failed: %s", exc)
        query_payload["warning"] = "Web search provider unavailable. Results may be empty."
        return SearchResponse(query=query_payload, candidates=[])

    if not web_hits:
        query_payload["warning"] = "No web results returned for this query."
        return SearchResponse(query=query_payload, candidates=[])

    user_context = {key: value for key, value in query_payload.items() if value not in (None, "")}

    try:
        candidate_payloads = await summarize_to_candidates(web_hits, user_context)
    except ValueError as exc:
        logger.warning("OpenAI summarization failed: %s", exc)
        query_payload["warning"] = "Summarization service unavailable."
        return SearchResponse(query=query_payload, candidates=[])

    normalized_candidates: List[Dict[str, Any]] = []
    for payload in candidate_payloads:
        if not isinstance(payload, dict):
            continue
        if not payload.get("name"):
            continue
        normalized = _normalize_candidate(payload)
        normalized_candidates.append(normalized)

    if not normalized_candidates:
        return SearchResponse(query=query_payload, candidates=[])

    query_text = f"{request.industry}. {request.description}. Name hint: {request.name or 'None'}"
    try:
        ranked_candidates = await score_candidates(query_text, normalized_candidates)
    except ValueError as exc:
        logger.warning("Embedding ranking failed: %s", exc)
        ranked_candidates = normalized_candidates

    top_ranked = ranked_candidates[:limit]
    candidates = []
    for item in top_ranked:
        try:
            candidates.append(Candidate.model_validate(item))
        except Exception as exc:  # pragma: no cover - defensive validation
            logger.debug("Skipping candidate due to validation error: %s", exc)

    return SearchResponse(query=query_payload, candidates=candidates)


@router.post("/save", response_model=SaveResponse)
async def save_candidate(request: SaveRequest) -> SaveResponse:
    candidate = request.candidate.model_dump(mode="json")

    saved = await run_in_threadpool(saved_witnesses.load_saved)
    existing_id = None
    for item in saved:
        if not isinstance(item, dict):
            continue
        if item.get("id") == candidate.get("id") or (
            item.get("name") == candidate.get("name")
            and item.get("organization") == candidate.get("organization")
        ):
            existing_id = item.get("id")
            break

    if existing_id:
        return SaveResponse(status="duplicate", id=str(existing_id))

    candidate_id = await run_in_threadpool(saved_witnesses.save_candidate, candidate)
    return SaveResponse(status="ok", id=str(candidate_id))


@router.get("/saved", response_model=List[Candidate])
async def get_saved_candidates() -> List[Candidate]:
    saved = await run_in_threadpool(saved_witnesses.load_saved)
    candidates: List[Candidate] = []
    for item in saved:
        try:
            candidates.append(Candidate.model_validate(item))
        except Exception as exc:  # pragma: no cover - defensive validation
            logger.debug("Skipping invalid saved candidate: %s", exc)
    return candidates


@router.delete("/saved/{candidate_id}")
async def delete_candidate(candidate_id: str) -> Dict[str, str]:
    removed = await run_in_threadpool(saved_witnesses.delete_candidate, candidate_id)
    if not removed:
        return {"status": "not_found"}
    return {"status": "ok"}
