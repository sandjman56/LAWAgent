from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from typing import Iterator, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, String, Text
from sqlmodel import Field, Relationship, SQLModel, Session, create_engine

from .config import get_settings


class UploadStatus(str, Enum):
    uploaded = "uploaded"
    extracting = "extracting"
    ready = "ready"
    analyzing = "analyzing"
    done = "done"
    error = "error"


class AnalysisStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class Upload(SQLModel, table=True):
    __tablename__ = "uploads"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    filename: str
    size_bytes: int
    pages: int = 0
    notes: Optional[str] = None
    case_id: Optional[str] = Field(default=None, index=True)
    status: UploadStatus = Field(default=UploadStatus.uploaded, sa_column=Column(String, index=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    error: Optional[str] = None

    chunks: list["Chunk"] = Relationship(back_populates="upload")
    analyses: list["Analysis"] = Relationship(back_populates="upload")


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    upload_id: UUID = Field(foreign_key="uploads.id", index=True, nullable=False)
    index: int = Field(index=True)
    text: str = Field(sa_column=Column(Text, nullable=False))
    token_count: int
    page_start: int = Field(default=0)
    page_end: int = Field(default=0)

    upload: Optional[Upload] = Relationship(back_populates="chunks")


class Analysis(SQLModel, table=True):
    __tablename__ = "analyses"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    upload_id: UUID = Field(foreign_key="uploads.id", index=True, nullable=False)
    status: AnalysisStatus = Field(default=AnalysisStatus.queued, sa_column=Column(String, index=True))
    result_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    upload: Optional[Upload] = Relationship(back_populates="analyses")


def _create_engine():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, echo=False, connect_args=connect_args)


def get_engine():
    global _ENGINE
    try:
        return _ENGINE
    except NameError:
        _ENGINE = _create_engine()
        return _ENGINE


_ENGINE = get_engine()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(_ENGINE)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session
