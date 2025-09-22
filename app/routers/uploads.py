from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.status import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
)
from sqlalchemy import func, delete
from sqlmodel import Session, select

from ..config import get_settings
from ..models import Chunk, Upload, UploadStatus, get_session
from ..schemas import ErrorResponse, UploadCreateResponse, UploadDeleteResponse, UploadStatusResponse
from ..services.pdf_extraction import get_pdf_page_count, process_upload
from ..utils.mime import is_pdf_magic, sanitize_filename


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


async def _write_upload_file(upload_path: Path, upload_file: UploadFile, max_bytes: int, limit_mb: int) -> int:
    size = 0
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(upload_path, "wb") as out_file:
        chunk = await upload_file.read(1024 * 1024)
        if not chunk:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
        if not is_pdf_magic(chunk):
            raise HTTPException(status_code=HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="File is not a valid PDF")
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(
                status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File is {size / (1024 * 1024):.1f} MB; limit is {limit_mb} MB",
            )
        await out_file.write(chunk)

        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(
                    status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File is {size / (1024 * 1024):.1f} MB; limit is {limit_mb} MB",
                )
            await out_file.write(chunk)

    return size


@router.post(
    "",
    response_model=UploadCreateResponse,
    status_code=HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
    },
)
async def create_upload(
    file: UploadFile = File(...),
    notes: Optional[str] = Form(default=None),
    case_id: Optional[str] = Form(default=None),
    session: Session = Depends(get_session),
):
    settings = get_settings()

    if file.content_type and file.content_type.lower() != "application/pdf":
        raise HTTPException(status_code=HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only application/pdf files are allowed")

    sanitized_name = sanitize_filename(file.filename or "upload.pdf")
    upload_record = Upload(filename=sanitized_name, size_bytes=0, notes=notes, case_id=case_id)
    upload_path = settings.data_dir / str(upload_record.id) / "original.pdf"

    try:
        size_bytes = await _write_upload_file(upload_path, file, settings.max_upload_bytes, settings.max_upload_mb)
    except HTTPException as exc:
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)
        if upload_path.parent.exists():
            shutil.rmtree(upload_path.parent, ignore_errors=True)
        raise exc
    finally:
        await file.close()

    try:
        page_count = await get_pdf_page_count(upload_path)
    except ValueError as exc:
        shutil.rmtree(upload_path.parent, ignore_errors=True)
        raise HTTPException(status_code=HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    if page_count > settings.max_pages:
        shutil.rmtree(upload_path.parent, ignore_errors=True)
        raise HTTPException(
            status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Document has {page_count} pages; limit is {settings.max_pages} pages",
        )

    upload_record.size_bytes = size_bytes
    upload_record.pages = page_count
    session.add(upload_record)
    session.commit()
    session.refresh(upload_record)

    asyncio.create_task(process_upload(upload_record.id))

    return UploadCreateResponse(
        upload_id=upload_record.id,
        filename=upload_record.filename,
        size_bytes=upload_record.size_bytes,
        pages=upload_record.pages,
        status=upload_record.status,
    )


@router.get("/{upload_id}/status", response_model=UploadStatusResponse, responses={404: {"model": ErrorResponse}})
async def upload_status(upload_id: UUID, session: Session = Depends(get_session)):
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Upload not found")

    chunk_count = session.exec(select(func.count(Chunk.id)).where(Chunk.upload_id == upload_id)).one()

    return UploadStatusResponse(
        upload_id=upload.id,
        filename=upload.filename,
        status=upload.status,
        pages=upload.pages,
        num_chunks=int(chunk_count or 0),
        size_bytes=upload.size_bytes,
        error=upload.error,
    )


@router.get(
    "/{upload_id}/download",
    response_class=FileResponse,
    responses={404: {"model": ErrorResponse}},
)
async def download_upload(upload_id: UUID):
    settings = get_settings()
    file_path = settings.data_dir / str(upload_id) / "original.pdf"
    if not file_path.exists():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="File not found")

    return FileResponse(path=file_path, filename=f"{upload_id}.pdf", media_type="application/pdf")


@router.delete(
    "/{upload_id}",
    response_model=UploadDeleteResponse,
    responses={404: {"model": ErrorResponse}},
)
async def delete_upload(upload_id: UUID, session: Session = Depends(get_session)):
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Upload not found")

    upload.status = UploadStatus.error
    upload.error = "deleted by user"
    upload.updated_at = datetime.utcnow()
    session.add(upload)
    session.exec(delete(Chunk).where(Chunk.upload_id == upload_id))
    session.commit()

    settings = get_settings()
    upload_dir = settings.data_dir / str(upload_id)
    if upload_dir.exists():
        await run_in_threadpool(shutil.rmtree, upload_dir, True)

    return UploadDeleteResponse(upload_id=upload_id, status="deleted")
