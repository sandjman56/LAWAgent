from __future__ import annotations

from typing import Iterable, List


DEFAULT_CHUNK_SIZE = 1800
DEFAULT_CHUNK_OVERLAP = 200


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_document(
    pages: Iterable[tuple[int, str]],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[dict]:
    """Chunk document text on page boundaries and paragraphs."""

    chunks: List[dict] = []
    chunk_index = 0

    for page_number, page_text in pages:
        normalized_paragraphs = [para.strip() for para in page_text.split("\n\n") if para.strip()]
        if not normalized_paragraphs:
            normalized_paragraphs = [""]

        current_text = ""
        current_start_page = page_number

        def flush_chunk(text: str) -> None:
            nonlocal chunk_index, current_start_page
            if not text:
                return
            cleaned = text.strip()
            if not cleaned:
                return
            chunks.append(
                {
                    "index": chunk_index,
                    "text": cleaned,
                    "token_count": estimate_tokens(cleaned),
                    "page_start": current_start_page,
                    "page_end": page_number,
                }
            )
            chunk_index += 1
            current_start_page = page_number

        for paragraph in normalized_paragraphs:
            if not current_text:
                candidate = paragraph
            else:
                candidate = current_text + "\n\n" + paragraph

            if len(candidate) <= chunk_size:
                current_text = candidate
                continue

            if current_text:
                flush_chunk(current_text)
                if overlap > 0:
                    overlap_text = current_text[-overlap:]
                    current_text = (overlap_text + "\n\n" + paragraph).strip()
                else:
                    current_text = paragraph
            else:
                for start in range(0, len(paragraph), chunk_size):
                    slice_text = paragraph[start : start + chunk_size]
                    flush_chunk(slice_text)
                current_text = ""

        if current_text:
            flush_chunk(current_text)
            current_text = ""

    return chunks
