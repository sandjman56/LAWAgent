from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
from uuid import UUID

import aiofiles
from fastapi.concurrency import run_in_threadpool
from pdfminer.high_level import extract_text as pdfminer_extract_text
from pypdf import PdfReader
from sqlalchemy import delete
from sqlmodel import select

from ..config import get_settings
from ..models import Chunk, Upload, UploadStatus, session_scope
from ..utils.chunking import chunk_document
from ..utils.mime import ensure_pdf


logger = logging.getLogger("lawagent.pdf")


def _normalize_text(text: str) -> str:
    cleaned = text.replace("\r", "\n").replace("\xa0", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_page_with_pdfminer(path: Path, page_number: int) -> str:
    return pdfminer_extract_text(str(path), page_numbers=[page_number]) or ""


def _read_pdf(path: Path) -> Tuple[int, List[Tuple[int, str]]]:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # pragma: no cover - safety
            raise ValueError("PDF is encrypted and cannot be processed") from exc

    pages: List[Tuple[int, str]] = []
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:  # pragma: no cover - fallback
            text = ""
        if not text:
            text = _extract_page_with_pdfminer(path, index)
        normalized = _normalize_text(text)
        pages.append((index + 1, normalized))

    return len(reader.pages), pages


def _count_pages(path: Path) -> int:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # pragma: no cover - safety
            raise ValueError("PDF is encrypted and cannot be processed") from exc
    return len(reader.pages)


async def get_pdf_page_count(path: Path) -> int:
    if not await run_in_threadpool(ensure_pdf, path):
        raise ValueError("Uploaded file is not a valid PDF")

    return await run_in_threadpool(_count_pages, path)


async def process_upload(upload_id: UUID) -> None:
    settings = get_settings()
    upload_dir = settings.data_dir / str(upload_id)
    pdf_path = upload_dir / "original.pdf"
    text_path = upload_dir / "text.txt"

    with session_scope() as session:
        upload = session.get(Upload, upload_id)
        if not upload:
            logger.error("upload not found", extra={"upload_id": str(upload_id)})
            return
        upload.status = UploadStatus.extracting
        upload.updated_at = datetime.utcnow()
        session.add(upload)

    try:
        page_count, pages = await run_in_threadpool(_read_pdf, pdf_path)
        chunks = chunk_document(pages)
        combined_text_parts = [f"--- PAGE {page_number} ---\n\n{text}" for page_number, text in pages]
        combined_text = "\n\n".join(combined_text_parts)

        async with aiofiles.open(text_path, "w", encoding="utf-8") as file:
            await file.write(combined_text)

        with session_scope() as session:
            upload = session.get(Upload, upload_id)
            if not upload:
                return
            upload.pages = page_count
            upload.status = UploadStatus.ready
            upload.updated_at = datetime.utcnow()
            upload.error = None
            session.add(upload)

            session.exec(delete(Chunk).where(Chunk.upload_id == upload_id))
            for chunk in chunks:
                session.add(
                    Chunk(
                        upload_id=upload_id,
                        index=chunk["index"],
                        text=chunk["text"],
                        token_count=chunk["token_count"],
                        page_start=chunk["page_start"],
                        page_end=chunk["page_end"],
                    )
                )

    except Exception as exc:
        logger.exception("failed to process upload", extra={"upload_id": str(upload_id)})
        with session_scope() as session:
            upload = session.get(Upload, upload_id)
            if upload:
                upload.status = UploadStatus.error
                upload.error = str(exc)
                upload.updated_at = datetime.utcnow()
                session.add(upload)

        if pdf_path.exists():
            pdf_path.unlink(missing_ok=True)
        if text_path.exists():
            text_path.unlink(missing_ok=True)


async def summarize_upload(upload_id: UUID) -> tuple[int, int]:
    with session_scope() as session:
        upload = session.get(Upload, upload_id)
        if not upload:
            raise ValueError("Upload not found")
        chunk_ids = session.exec(select(Chunk.id).where(Chunk.upload_id == upload_id)).all()
        return upload.pages, len(chunk_ids)
