from __future__ import annotations

import math
from typing import List

import numpy as np

from app.models.schemas import Candidate
from app.services.openai_client import embed_texts


def cosine_sim_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if a.size == 0 or b.size == 0:
        return np.zeros((a.shape[0] if a.ndim > 1 else 0, b.shape[0]))

    if a.ndim == 1:
        a = a.reshape(1, -1)
    if b.ndim == 1:
        b = b.reshape(1, -1)

    a_norm = np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = np.linalg.norm(b, axis=1, keepdims=True)
    a_norm[a_norm == 0] = 1
    b_norm[b_norm == 0] = 1

    normalized_a = a / a_norm
    normalized_b = b / b_norm

    return normalized_a @ normalized_b.T


def rescale_to_100(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    # cosine similarity is in [-1, 1]; rescale to [0, 100]
    scaled = (value + 1.0) / 2.0 * 100.0
    return max(0.0, min(100.0, scaled))


def _candidate_text(candidate: Candidate) -> str:
    parts: List[str] = [candidate.name]
    for attr in (candidate.title, candidate.organization, candidate.sector, candidate.location):
        if attr:
            parts.append(attr)
    if candidate.summary:
        parts.append(candidate.summary)
    if candidate.skills:
        parts.append(", ".join(candidate.skills))
    return ". ".join(parts)


async def score_candidates(query_text: str, candidates: List[Candidate]) -> List[Candidate]:
    if not candidates:
        return []

    candidate_texts = [_candidate_text(candidate) for candidate in candidates]
    embeddings = await embed_texts([query_text, *candidate_texts])
    if embeddings.size == 0:
        return candidates

    query_vec = embeddings[0]
    candidate_matrix = embeddings[1:]
    similarities = cosine_sim_matrix(query_vec, candidate_matrix).flatten()

    for candidate, sim in zip(candidates, similarities):
        embedding_score = rescale_to_100(float(sim))
        llm_score = candidate.match_strength
        if llm_score is not None:
            llm_score = max(0.0, min(100.0, float(llm_score)))
            combined = (embedding_score + llm_score) / 2.0
        else:
            combined = embedding_score
        candidate.similarity_score = int(round(combined))

    candidates.sort(key=lambda c: c.similarity_score, reverse=True)
    return candidates
