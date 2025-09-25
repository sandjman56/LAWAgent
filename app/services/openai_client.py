from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import numpy as np
from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    OpenAIError,
    RateLimitError,
)

from app.config import settings

logger = logging.getLogger("lawagent.openai")

_chat_client = AsyncOpenAI(api_key=settings.openai_api_key)
_embed_model = settings.openai_embeddings_model

_SYSTEM_PROMPT = (
    "You are a legal research assistant compiling potential expert witnesses. "
    "Extract people with relevant expertise and produce strictly valid JSON in the schema provided. "
    "Deduplicate names. Include a sources array citing the URLs used."
)

_SCHEMA_INSTRUCTIONS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "title": {"type": "string"},
            "organization": {"type": "string"},
            "sector": {"type": "string"},
            "years_experience": {"type": "number"},
            "location": {"type": "string"},
            "summary": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "emails": {"type": "array", "items": {"type": "string"}},
            "links": {"type": "array", "items": {"type": "string"}},
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "snippet": {"type": "string"},
                    },
                    "required": ["url"],
                },
            },
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "match_strength": {"type": "number"},
        },
        "required": ["name", "summary", "sources"],
    },
}


def _build_messages(web_hits: List[Dict[str, Any]], user_context: Dict[str, Any]) -> List[Dict[str, str]]:
    payload = {
        "user_query": user_context,
        "web_hits": web_hits,
        "instructions": {
            "task": "Transform the web hits into expert witness candidate profiles.",
            "requirements": [
                "Estimate years_experience when unspecified; prefer conservative estimates.",
                "Return confidence as low, medium, or high.",
                "Include canonical profile links in links when available.",
                "Provide match_strength as an integer 0-100 indicating relevance.",
            ],
        },
        "output_schema": _SCHEMA_INSTRUCTIONS,
    }
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]


def _extract_json(content: str) -> List[Dict[str, Any]] | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(data, list):
            return data

    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
        if isinstance(data, list):
            return data
    return None


async def summarize_to_candidates(
    web_hits: List[Dict[str, Any]], user_context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    messages = _build_messages(web_hits, user_context)

    for attempt in range(2):
        try:
            completion = await _chat_client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                temperature=0.2,
                timeout=30,
            )
        except AuthenticationError as exc:  # pragma: no cover - network
            logger.exception("OpenAI authentication failed.")
            raise ValueError("OpenAI authentication failed. Check OPENAI_API_KEY.") from exc
        except RateLimitError as exc:  # pragma: no cover - network
            logger.warning("OpenAI rate limit hit: %s", exc)
            raise ValueError("OpenAI rate limit reached. Try again shortly.") from exc
        except (APIConnectionError, APIStatusError, BadRequestError, OpenAIError) as exc:  # pragma: no cover - network
            logger.exception("OpenAI error while summarizing candidates: %s", exc)
            raise ValueError("Unable to summarize candidates from OpenAI.") from exc

        content = completion.choices[0].message.content if completion.choices else ""
        if not content:
            continue

        parsed = _extract_json(content)
        if parsed is not None:
            return parsed

        messages.append(
            {
                "role": "system",
                "content": "The previous output was invalid JSON. Respond with JSON only, no prose.",
            }
        )

    logger.error("Failed to obtain valid JSON candidate list from OpenAI.")
    return []


async def embed_texts(texts: List[str]) -> np.ndarray:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    if not texts:
        return np.zeros((0, 0))

    try:
        result = await _chat_client.embeddings.create(model=_embed_model, input=texts, timeout=30)
    except AuthenticationError as exc:  # pragma: no cover - network
        logger.exception("OpenAI authentication failed for embeddings.")
        raise ValueError("OpenAI authentication failed. Check OPENAI_API_KEY.") from exc
    except RateLimitError as exc:  # pragma: no cover - network
        logger.warning("OpenAI embedding rate limit hit: %s", exc)
        raise ValueError("OpenAI rate limit reached while computing embeddings.") from exc
    except (APIConnectionError, APIStatusError, BadRequestError, OpenAIError) as exc:  # pragma: no cover - network
        logger.exception("OpenAI error while embedding texts: %s", exc)
        raise ValueError("Unable to compute embeddings.") from exc

    vectors = [item.embedding for item in result.data]
    if not vectors:
        return np.zeros((0, 0))

    array = np.array(vectors, dtype=float)
    return array
