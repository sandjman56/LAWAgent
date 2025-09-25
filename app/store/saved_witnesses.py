from __future__ import annotations

import json
import uuid
from pathlib import Path
from threading import Lock
from typing import Dict, List

_DATA_DIR = Path("data")
_DATA_FILE = _DATA_DIR / "saved_witnesses.json"
_LOCK = Lock()


def _ensure_storage() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _DATA_FILE.exists():
        _DATA_FILE.write_text("[]", encoding="utf-8")


def _read() -> List[Dict]:
    try:
        return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _write(data: List[Dict]) -> None:
    _DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_saved() -> List[Dict]:
    with _LOCK:
        _ensure_storage()
        raw = _read()
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def save_candidate(candidate: Dict) -> str:
    with _LOCK:
        _ensure_storage()
        data = _read()
        if not isinstance(data, list):
            data = []

        candidate_copy = dict(candidate)
        candidate_id = candidate_copy.get("id") or str(uuid.uuid4())
        candidate_copy["id"] = candidate_id

        for existing in data:
            if not isinstance(existing, dict):
                continue
            if existing.get("id") == candidate_id or (
                existing.get("name") == candidate_copy.get("name")
                and existing.get("organization") == candidate_copy.get("organization")
            ):
                return existing.get("id", candidate_id)

        data.append(candidate_copy)
        _write(data)
        return candidate_id


def delete_candidate(candidate_id: str) -> bool:
    with _LOCK:
        _ensure_storage()
        data = _read()
        if not isinstance(data, list):
            data = []

        updated: List[Dict] = []
        removed = False
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("id") == candidate_id:
                removed = True
                continue
            updated.append(item)

        if removed:
            _write(updated)
        return removed
