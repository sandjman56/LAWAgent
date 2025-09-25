from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np

from app.services.openai_client import embed_texts


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    if vec_a.size == 0 or vec_b.size == 0:
        return 0.0
    if vec_a.ndim > 1:
        vec_a = vec_a.reshape(-1)
    if vec_b.ndim > 1:
        vec_b = vec_b.reshape(-1)
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def rescale_to_100(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    scaled = (value + 1.0) / 2.0 * 100.0
    return max(0.0, min(100.0, scaled))


def _candidate_text(candidate: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("name", "title", "organization", "sector", "location"):
        value = candidate.get(key)
        if value:
            parts.append(str(value))
    summary = candidate.get("summary")
    if summary:
        parts.append(str(summary))
    skills = candidate.get("skills") or []
    if skills:
        parts.append(", ".join(str(skill) for skill in skills))
    return ". ".join(parts)


async def score_candidates(query_text: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not candidates:
        return []

    candidate_texts = [_candidate_text(candidate) for candidate in candidates]
    embeddings = await embed_texts([query_text, *candidate_texts])
    if embeddings.size == 0:
        for candidate in candidates:
            candidate.setdefault("similarity_score", 0)
        return candidates

    query_vector = embeddings[0]
    candidate_vectors = embeddings[1:]

    for candidate, vector in zip(candidates, candidate_vectors):
        embed_score = rescale_to_100(cosine_similarity(query_vector, vector))
        llm_score = candidate.get("match_strength")
        if llm_score is not None:
            try:
                llm_score_val = max(0.0, min(100.0, float(llm_score)))
            except (TypeError, ValueError):
                llm_score_val = embed_score
            final_score = (embed_score + llm_score_val) / 2.0
        else:
            final_score = embed_score
        candidate["similarity_score"] = int(round(final_score))

    candidates.sort(key=lambda item: item.get("similarity_score", 0), reverse=True)
    return candidates
