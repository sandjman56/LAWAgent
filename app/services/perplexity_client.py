from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from app.config import settings

logger = logging.getLogger("lawagent.perplexity")


class PerplexityError(RuntimeError):
    """Raised when Perplexity API requests fail."""


_CONFIG: Dict[str, Any] = {
    "base_url": "https://api.perplexity.ai",
    "search_path": "/search",
    "default_model": settings.perplexity_model,
    "timeout": httpx.Timeout(15.0, connect=10.0, read=15.0, write=10.0),
    "max_results": 20,
}


def _build_headers() -> Dict[str, str]:
    if not settings.perplexity_api_key:
        raise PerplexityError("PERPLEXITY_API_KEY is not configured.")
    return {
        "Authorization": f"Bearer {settings.perplexity_api_key}",
        "Content-Type": "application/json",
    }


def _normalize_hit(item: Dict[str, Any]) -> Dict[str, Any]:
    title = (item.get("title") or item.get("name") or "").strip()
    url = (item.get("url") or item.get("source") or item.get("link") or "").strip()
    snippet = (
        item.get("snippet")
        or item.get("text")
        or item.get("summary")
        or item.get("content")
        or ""
    ).strip()

    metadata = item.get("metadata") or item.get("details") or {}
    persons: List[str] = []
    for key in ("person", "people", "names", "authors"):
        value = metadata.get(key) if isinstance(metadata, dict) else None
        if not value:
            value = item.get(key)
        if isinstance(value, str) and value.strip():
            persons.extend([p.strip() for p in value.split(",") if p.strip()])
        elif isinstance(value, (list, tuple)):
            persons.extend(str(v).strip() for v in value if str(v).strip())

    organization = None
    for key in ("organization", "org", "affiliation", "company"):
        value = (metadata.get(key) if isinstance(metadata, dict) else None) or item.get(key)
        if isinstance(value, str) and value.strip():
            organization = value.strip()
            break

    location = None
    for key in ("location", "city", "region", "country"):
        value = (metadata.get(key) if isinstance(metadata, dict) else None) or item.get(key)
        if isinstance(value, str) and value.strip():
            location = value.strip()
            break

    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "persons": persons,
        "organization": organization,
        "location": location,
        "raw": item,
    }


async def search_web(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Call Perplexity's search endpoint and normalize the results."""

    headers = _build_headers()
    payload = {
        "model": _CONFIG["default_model"],
        "query": query,
        "top_k": max(3, min(limit, _CONFIG["max_results"])),
        "search_mode": "concise",
        "include_titles": True,
    }

    url = f"{_CONFIG['base_url']}{_CONFIG['search_path']}"
    try:
        async with httpx.AsyncClient(timeout=_CONFIG["timeout"]) as client:
            response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:  # pragma: no cover - network
        logger.exception("Perplexity returned an error: %s", exc.response.text)
        raise PerplexityError("Perplexity search failed with an error status.") from exc
    except httpx.RequestError as exc:  # pragma: no cover - network
        logger.exception("Error communicating with Perplexity: %s", exc)
        raise PerplexityError("Unable to reach Perplexity. Check your network connection.") from exc

    data = response.json()

    raw_results: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            raw_results = data["data"]
        elif isinstance(data.get("results"), list):
            raw_results = data["results"]
        elif isinstance(data.get("output"), list):
            raw_results = data["output"]

    normalized = [_normalize_hit(item) for item in raw_results[:limit]]
    return normalized
