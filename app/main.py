from __future__ import annotations

import json
import logging
import os
import time
import re
from typing import Any, Dict, List, Tuple

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.routers import health, issue_spotter
from app.routers.witness_finder import router as witness_finder_router

app = FastAPI(title="LAWAgent")

logger = logging.getLogger("lawagent.ask_witness")

_API_KEY = os.getenv("PERPLEXITY_API_KEY")
_CLIENT: OpenAI | None = None
if _API_KEY:
    _CLIENT = OpenAI(api_key=_API_KEY, base_url="https://api.perplexity.ai")

_CACHE_TTL_SECONDS = 600
_REQUEST_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_RATE_LIMIT_WINDOW = 60.0
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_BUCKET: Dict[str, List[float]] = {}


class WitnessQuery(BaseModel):
    sector: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=1500)
    name: str | None = Field(default=None, max_length=200)

    @field_validator("sector", "description", "name", mode="before")
    @classmethod
    def _strip_and_cast(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("sector", "description", mode="after")
    @classmethod
    def _ensure_not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Field is required.")
        cleaned = "".join(ch if ch.isprintable() else " " for ch in value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            raise ValueError("Field is required.")
        return cleaned

    @field_validator("name", mode="after")
    @classmethod
    def _escape_optional(cls, value: str | None) -> str | None:
        if not value:
            return None
        cleaned = "".join(ch if ch.isprintable() else " " for ch in value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or None

origins = ["http://localhost:8000", "http://127.0.0.1:8000", "*"]
if settings.allowed_origins:
    origins.extend([o.strip() for o in settings.allowed_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(issue_spotter.router, prefix="/api/issue-spotter", tags=["Issue Spotter"])
app.include_router(witness_finder_router)
app.include_router(health.router, prefix="/api/health", tags=["Health"])
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")


@app.get("/witness_finder", include_in_schema=False)
async def witness_finder_page(request: Request):
    accept = request.headers.get("accept", "")
    wants_html = "text/html" in accept or "*/*" in accept
    if wants_html and "application/json" not in accept.split(",")[0]:
        return FileResponse("app/static/witness-finder.html")
    return JSONResponse({"service": "witness_finder", "hint": "Use /api/witness_finder/search for POST"})


def _call_perplexity(query: WitnessQuery) -> Dict[str, Any]:
    if not _CLIENT:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Perplexity API key is missing.")

    prompt = (
        "You are an AI legal research assistant who surfaces expert witness candidates. "
        "Summarize key findings clearly and list notable experts with reliable sources."
    )
    user_message = (
        f"Sector: {query.sector}\n"
        f"Description: {query.description}\n"
        f"Name hint: {query.name or 'None'}\n"
        "Provide concise summary followed by expert witness candidates and their supporting sources."
    )

    start = time.perf_counter()
    try:
        response = _CLIENT.chat.completions.create(
            model="sonar",
            max_tokens=500,
            temperature=0.7,
            similarity_filter=0,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message},
            ],
        )
    except Exception as exc:  # pragma: no cover - network failure
        elapsed = time.perf_counter() - start
        logger.error("Perplexity chat call failed after %.2fs: %s", elapsed, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to reach Perplexity API.") from exc

    elapsed = time.perf_counter() - start
    logger.info("Perplexity chat completed in %.2fs", elapsed)
    payload = response.model_dump()
    return payload


def _format_perplexity_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the Perplexity API payload into the contract required by the UI."""

    summary = ""
    results: List[Dict[str, Any]] = []
    citations_candidates: List[Any] = []

    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0] or {}
            message_block = first_choice.get("message") if isinstance(first_choice, dict) else None
            if isinstance(message_block, dict):
                summary = str(message_block.get("content") or "").strip()
                for key in ("citations", "references", "context", "sources"):
                    value = message_block.get(key)
                    if isinstance(value, list):
                        citations_candidates.extend(value)
            elif isinstance(first_choice, dict):
                summary = str(first_choice.get("content") or "").strip()

        if not summary:
            summary = str(payload.get("summary") or "").strip()

        for key in ("citations", "references", "context", "results", "data", "sources"):
            value = payload.get(key)
            if isinstance(value, list):
                citations_candidates.extend(value)

    seen_urls = set()
    for item in citations_candidates:
        if not isinstance(item, dict):
            continue

        url = str(
            item.get("url")
            or item.get("source")
            or item.get("link")
            or item.get("citation")
            or ""
        ).strip()
        if not url or url in seen_urls:
            continue

        title = str(
            item.get("title")
            or item.get("name")
            or item.get("headline")
            or url
        ).strip()
        snippet = str(
            item.get("snippet")
            or item.get("text")
            or item.get("summary")
            or item.get("description")
            or ""
        ).strip()

        result_entry: Dict[str, Any] = {"title": title or url, "url": url, "snippet": snippet}
        similarity = item.get("similarity") or item.get("score") or item.get("similarity_score")
        if isinstance(similarity, (int, float)):
            result_entry["similarity"] = float(similarity)

        results.append(result_entry)
        seen_urls.add(url)

    return {"summary": summary, "results": results}


def _cache_key(query: WitnessQuery) -> str:
    payload = query.model_dump()
    return json.dumps(payload, sort_keys=True)


def _rate_limited(identifier: str) -> bool:
    now = time.time()
    timestamps = _RATE_LIMIT_BUCKET.setdefault(identifier, [])
    timestamps[:] = [ts for ts in timestamps if now - ts < _RATE_LIMIT_WINDOW]
    if len(timestamps) >= _RATE_LIMIT_MAX:
        return True
    timestamps.append(now)
    return False


@app.post("/api/ask-witness")
async def ask_witness(query: WitnessQuery, request: Request) -> Dict[str, Any]:
    if _rate_limited((request.client.host if request.client else "anonymous")):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded. Try again shortly.")

    cache_key = _cache_key(query)
    cached = _REQUEST_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        logger.info("Returning cached witness results for key %s", cache_key)
        return cached[1]

    start_time = time.perf_counter()
    try:
        payload = _call_perplexity(query)
        formatted = _format_perplexity_response(payload)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        elapsed = time.perf_counter() - start_time
        logger.error("Unexpected error after %.2fs: %s", elapsed, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected server error.") from exc

    elapsed = time.perf_counter() - start_time
    logger.info("Witness search handled in %.2fs", elapsed)

    if not formatted.get("summary"):
        formatted["summary"] = ""
    formatted.setdefault("results", [])

    _REQUEST_CACHE[cache_key] = (now, formatted)
    return formatted
