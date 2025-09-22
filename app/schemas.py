from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .models import AnalysisStatus, UploadStatus


class UploadBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    size_bytes: int
    pages: int
    status: UploadStatus
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None
    case_id: Optional[str] = None
    error: Optional[str] = None


class UploadCreateResponse(BaseModel):
    upload_id: UUID
    filename: str
    size_bytes: int
    pages: int
    status: UploadStatus


class UploadStatusResponse(BaseModel):
    upload_id: UUID
    filename: str
    status: UploadStatus
    pages: int
    num_chunks: int
    size_bytes: int
    error: Optional[str] = None


class UploadDeleteResponse(BaseModel):
    upload_id: UUID
    status: Literal["deleted"]


class AnalysisCreateRequest(BaseModel):
    prompt: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None


class AnalysisCreateResponse(BaseModel):
    analysis_id: UUID
    status: AnalysisStatus


class AnalysisStatusResponse(BaseModel):
    analysis_id: UUID
    status: AnalysisStatus
    progress: dict[str, int]
    error: Optional[str] = None


class AnalysisResultResponse(BaseModel):
    analysis_id: UUID
    status: AnalysisStatus
    result: dict


class ErrorResponse(BaseModel):
    detail: str
