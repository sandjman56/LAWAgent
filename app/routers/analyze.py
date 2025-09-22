from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND
from sqlalchemy import func
from sqlmodel import Session, select

from ..models import Analysis, AnalysisStatus, Chunk, Upload, UploadStatus, get_session
from ..schemas import (
    AnalysisCreateRequest,
    AnalysisCreateResponse,
    AnalysisResultResponse,
    AnalysisStatusResponse,
    ErrorResponse,
)
from ..services.analysis import run_issue_spotter


router = APIRouter(prefix="/api/analyze", tags=["analysis"])


@router.post(
    "/{upload_id}",
    response_model=AnalysisCreateResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def start_analysis(
    upload_id: UUID,
    request: AnalysisCreateRequest,
    session: Session = Depends(get_session),
):
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Upload not found")
    if upload.status not in {UploadStatus.ready, UploadStatus.done}:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Upload is not ready for analysis")

    analysis = Analysis(upload_id=upload_id, status=AnalysisStatus.queued)
    session.add(analysis)
    session.commit()
    session.refresh(analysis)

    asyncio.create_task(
        run_issue_spotter(
            analysis_id=analysis.id,
            upload_id=upload_id,
            prompt=request.prompt,
            model=request.model,
            max_tokens=request.max_tokens,
        )
    )

    return AnalysisCreateResponse(analysis_id=analysis.id, status=analysis.status)


def _calculate_progress(analysis: Analysis, session: Session) -> dict[str, int]:
    if analysis.result_json and "progress" in analysis.result_json:
        progress = analysis.result_json["progress"]
        return {
            "completed_chunks": int(progress.get("completed_chunks", 0)),
            "total_chunks": int(progress.get("total_chunks", 0)),
        }

    total_chunks = session.exec(select(func.count(Chunk.id)).where(Chunk.upload_id == analysis.upload_id)).one()
    completed = total_chunks if analysis.status == AnalysisStatus.done else 0
    if analysis.status == AnalysisStatus.error:
        completed = 0
    return {"completed_chunks": int(completed or 0), "total_chunks": int(total_chunks or 0)}


@router.get(
    "/{analysis_id}/status",
    response_model=AnalysisStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def analysis_status(analysis_id: UUID, session: Session = Depends(get_session)):
    analysis = session.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Analysis not found")

    progress = _calculate_progress(analysis, session)
    error_message: Optional[str] = analysis.error

    return AnalysisStatusResponse(
        analysis_id=analysis.id,
        status=analysis.status,
        progress=progress,
        error=error_message,
    )


@router.get(
    "/{analysis_id}/result",
    response_model=AnalysisResultResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def analysis_result(analysis_id: UUID, session: Session = Depends(get_session)):
    analysis = session.get(Analysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Analysis not found")

    if analysis.status == AnalysisStatus.error:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=analysis.error or "Analysis failed")
    if analysis.status != AnalysisStatus.done:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Analysis not complete yet")
    if not analysis.result_json:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Analysis result unavailable")

    return AnalysisResultResponse(
        analysis_id=analysis.id,
        status=analysis.status,
        result=analysis.result_json,
    )
