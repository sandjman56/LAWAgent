from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

from fastapi import UploadFile
from pypdf import PdfReader

from app.config import settings


class ExtractionError(ValueError):
    """Raised when a file cannot be processed."""


def _guard_file_size(data: bytes) -> None:
    max_bytes = settings.max_file_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ExtractionError(f"File exceeds the {settings.max_file_mb} MB limit.")


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > settings.max_pages:
        raise ExtractionError(
            f"PDF has {len(reader.pages)} pages; the limit is {settings.max_pages}."
        )
    text_segments = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(segment.strip() for segment in text_segments if segment)


def _extract_docx(data: bytes) -> str:
    try:  # pragma: no cover - import side effect
        import docx  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError(
            "DOCX support is unavailable because python-docx is not installed."
        ) from exc

    document = docx.Document(io.BytesIO(data))  # type: ignore[attr-defined]
    paragraphs = [para.text.strip() for para in document.paragraphs if para.text]
    return "\n".join(paragraphs)


def _extract_doc(data: bytes) -> str:
    try:  # pragma: no cover - optional dependency
        import textract  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError(
            "DOC files require textract, which is not installed in this environment."
        ) from exc

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".doc") as temp_file:
        temp_file.write(data)
        temp_file.flush()
        text = textract.process(temp_file.name)  # type: ignore[attr-defined]
    return text.decode("utf-8", errors="ignore")


async def extract_text_from_file(file: UploadFile) -> str:
    filename = file.filename or "uploaded_file"
    extension = Path(filename).suffix.lower()

    file_bytes = await file.read()
    if not file_bytes:
        raise ExtractionError("The uploaded file is empty.")

    _guard_file_size(file_bytes)

    extractor_lookup: dict[str, Callable[[bytes], str]] = {
        ".pdf": _extract_pdf,
        ".docx": _extract_docx,
        ".doc": _extract_doc,
    }

    extractor = extractor_lookup.get(extension)
    if extractor is None:
        allowed = ", ".join(extractor_lookup.keys())
        raise ExtractionError(f"Unsupported file type '{extension}'. Allowed types: {allowed}.")

    text = extractor(file_bytes)
    if not text.strip():
        raise ExtractionError("No readable text found in the document.")

    return text
