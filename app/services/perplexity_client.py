from __future__ import annotations

import logging
import os
from typing import Dict, List

import httpx

logger = logging.getLogger("lawagent.perplexity")


class PerplexityAPIError(RuntimeError):
    """Raised when Perplexity API requests fail."""


_BASE_URL = "https://api.perplexity.ai"
_SEARCH_PATH = "/search"
_API_KEY = os.getenv("PERPLEXITY_API_KEY")
_MODEL = os.getenv("PERPLEXITY_MODEL") or "llama-3.1-sonar-large-128k-online"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0, read=20.0, write=10.0)

logger.info("Perplexity model set to %s", _MODEL)


async def search_web(query: str, limit: int = 12) -> List[Dict[str, str]]:
    if not _API_KEY:
        raise PerplexityAPIError("PERPLEXITY_API_KEY is not configured.")

    headers = {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _MODEL,
        "query": query,
        "top_k": max(3, min(limit, 25)),
        "search_mode": "concise",
        "return_images": False,
        "return_related_questions": False,
        "return_citations": True,
    }

    try:
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
            response = await client.post(_SEARCH_PATH, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:  # pragma: no cover - network
        body = exc.response.text if exc.response is not None else ""
        logger.error("Perplexity returned %s: %s", exc.response.status_code if exc.response else "?", body)
        raise PerplexityAPIError("Perplexity search failed with an HTTP error.") from exc
    except httpx.RequestError as exc:  # pragma: no cover - network
        logger.error("Error communicating with Perplexity: %s", exc)
        raise PerplexityAPIError("Unable to reach Perplexity search service.") from exc

    payload = response.json()
    results: List[Dict[str, str]] = []
    items = []
    if isinstance(payload, dict):
        for key in ("data", "results", "output"):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break

    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        url = str(
            item.get("url")
            or item.get("source")
            or item.get("link")
            or item.get("citation")
            or ""
        ).strip()
        snippet = str(
            item.get("snippet")
            or item.get("text")
            or item.get("summary")
            or item.get("content")
            or ""
        ).strip()
        if not url:
            continue
        results.append({"title": title, "url": url, "snippet": snippet})

    return results
