from __future__ import annotations

import json
import logging
import os
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

logger = logging.getLogger("lawagent.openai")

_API_KEY = os.getenv("OPENAI_API_KEY")
_CHAT_MODEL = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
_EMBED_MODEL = "text-embedding-3-large"
_CLIENT: AsyncOpenAI | None = AsyncOpenAI(api_key=_API_KEY) if _API_KEY else None

logger.info("OpenAI chat model set to %s", _CHAT_MODEL)

_SYSTEM_PROMPT = (
    "You are a legal research assistant compiling potential expert witnesses from noisy web results. "
    "Produce STRICT JSON: "
    "[{name, title, organization, sector, years_experience, location, summary, skills[], emails[], links[], "
    "sources:[{url, snippet}], confidence:low|medium|high, match_strength: 0..100}] "
    "Deduplicate people. Do not include text outside JSON."
)


def _build_messages(web_hits: List[Dict[str, Any]], user_context: Dict[str, Any]) -> List[Dict[str, str]]:
    payload = {
        "user_context": user_context,
        "web_hits": web_hits,
    }
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _parse_candidates(content: str) -> List[Dict[str, Any]] | None:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return parsed
    return None


async def summarize_to_candidates(
    web_hits: List[Dict[str, Any]], user_context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    if not _CLIENT or not _API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    messages = _build_messages(web_hits, user_context)

    for attempt in range(2):
        try:
            response = await _CLIENT.chat.completions.create(
                model=_CHAT_MODEL,
                messages=messages,
                temperature=0.1,
                timeout=40,
            )
        except AuthenticationError as exc:  # pragma: no cover - network
            logger.error("OpenAI authentication failed: %s", exc)
            raise ValueError("OpenAI authentication failed. Check OPENAI_API_KEY.") from exc
        except RateLimitError as exc:  # pragma: no cover - network
            logger.warning("OpenAI rate limit reached: %s", exc)
            raise ValueError("OpenAI rate limit reached. Try again shortly.") from exc
        except (APIConnectionError, APIStatusError, BadRequestError, OpenAIError) as exc:  # pragma: no cover - network
            logger.error("OpenAI error while summarizing candidates: %s", exc)
            raise ValueError("Unable to summarize candidates from OpenAI.") from exc

        content = response.choices[0].message.content if response.choices else ""
        if not content:
            continue

        parsed = _parse_candidates(content)
        if parsed is not None:
            return parsed

        messages.append(
            {
                "role": "system",
                "content": "The previous response was invalid JSON. Respond with JSON only.",
            }
        )

    raise ValueError("OpenAI did not return valid candidate JSON.")


async def embed_texts(texts: List[str]) -> np.ndarray:
    if not _CLIENT or not _API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    if not texts:
        return np.zeros((0, 0))

    try:
        result = await _CLIENT.embeddings.create(model=_EMBED_MODEL, input=texts, timeout=40)
    except AuthenticationError as exc:  # pragma: no cover - network
        logger.error("OpenAI authentication failed for embeddings: %s", exc)
        raise ValueError("OpenAI authentication failed. Check OPENAI_API_KEY.") from exc
    except RateLimitError as exc:  # pragma: no cover - network
        logger.warning("OpenAI embedding rate limit reached: %s", exc)
        raise ValueError("OpenAI rate limit reached while computing embeddings.") from exc
    except (APIConnectionError, APIStatusError, BadRequestError, OpenAIError) as exc:  # pragma: no cover - network
        logger.error("OpenAI error while computing embeddings: %s", exc)
        raise ValueError("Unable to compute embeddings.") from exc

    embeddings = [item.embedding for item in result.data]
    if not embeddings:
        return np.zeros((0, 0))

    return np.asarray(embeddings, dtype=float)
