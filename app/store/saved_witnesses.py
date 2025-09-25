from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List, Tuple

from app.models.schemas import Candidate

_DATA_DIR = Path("data")
_DATA_FILE = _DATA_DIR / "saved_witnesses.json"
_LOCK = asyncio.Lock()


def _ensure_storage() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _DATA_FILE.exists():
        _DATA_FILE.write_text("[]", encoding="utf-8")


async def load_saved() -> List[Candidate]:
    async with _LOCK:
        _ensure_storage()
        try:
            raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = []

        candidates: List[Candidate] = []
        for item in raw:
            if isinstance(item, dict):
                try:
                    candidates.append(Candidate.model_validate(item))
                except Exception:  # pragma: no cover - defensive against corrupt data
                    continue
        return candidates


async def save_candidate(candidate: Candidate) -> Tuple[str, bool]:
    async with _LOCK:
        _ensure_storage()
        try:
            raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = []

        candidate_dict = candidate.model_dump(mode="json", exclude_none=True)

        for existing in raw:
            if not isinstance(existing, dict):
                continue
            if existing.get("id") == candidate.id or (
                existing.get("name") == candidate.name
                and existing.get("organization") == candidate.organization
            ):
                return existing.get("id", candidate.id), True

        raw.append(candidate_dict)
        _DATA_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        return candidate.id, False


async def delete_candidate(candidate_id: str) -> bool:
    async with _LOCK:
        _ensure_storage()
        try:
            raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = []

        updated = []
        removed = False
        for item in raw:
            if not isinstance(item, dict):
                continue
            if item.get("id") == candidate_id:
                removed = True
                continue
            updated.append(item)

        if removed:
            _DATA_FILE.write_text(json.dumps(updated, indent=2), encoding="utf-8")

        return removed
