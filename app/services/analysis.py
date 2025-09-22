from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

import httpx
from fastapi.concurrency import run_in_threadpool
from sqlmodel import select

from ..config import get_settings
from ..models import Analysis, AnalysisStatus, Chunk, Upload, UploadStatus, session_scope


logger = logging.getLogger("lawagent.analysis")

LLMCallable = Callable[[str, int, Optional[str], Optional[str], Optional[int]], Dict[str, Any]]


def _stub_llm_call(
    chunk_text: str,
    chunk_index: int,
    prompt: Optional[str],
    model: Optional[str],
    max_tokens: Optional[int],
) -> Dict[str, Any]:
    preview = chunk_text[:280].strip().replace("\n", " ")
    severity_scale = ["low", "medium", "high"]
    severity = severity_scale[chunk_index % len(severity_scale)]
    return {
        "summary": preview or "No substantive text detected in this section.",
        "issues": [
            {
                "title": f"Potential issue {chunk_index + 1}",
                "severity": severity,
                "evidence_excerpt": preview[:200],
                "citations": [],
            }
        ],
    }


async def _call_openai(
    api_key: str,
    chunk_text: str,
    chunk_index: int,
    prompt: Optional[str],
    model: Optional[str],
    max_tokens: Optional[int],
) -> Dict[str, Any]:
    model_name = model or "gpt-4o-mini"
    system_prompt = prompt or "You are a legal issue spotter. Respond with JSON containing `summary` and `issues` array."
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": chunk_text},
    ]
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return json.loads(content)
    return content


def get_llm_callable() -> LLMCallable:
    settings = get_settings()
    if settings.llm_provider and settings.llm_provider.lower() == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY must be set when LLM_PROVIDER=openai")

        def openai_wrapper(
            chunk_text: str,
            chunk_index: int,
            prompt: Optional[str],
            model: Optional[str],
            max_tokens: Optional[int],
        ) -> Dict[str, Any]:
            return asyncio.run(
                _call_openai(
                    settings.openai_api_key,
                    chunk_text,
                    chunk_index,
                    prompt,
                    model,
                    max_tokens,
                )
            )

        return openai_wrapper

    return _stub_llm_call


async def run_issue_spotter(
    analysis_id: UUID,
    upload_id: UUID,
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> None:
    llm_callable = get_llm_callable()

    with session_scope() as session:
        analysis = session.get(Analysis, analysis_id)
        upload = session.get(Upload, upload_id)
        if not analysis or not upload:
            logger.error("analysis or upload missing", extra={"analysis_id": str(analysis_id), "upload_id": str(upload_id)})
            return
        upload.status = UploadStatus.analyzing
        upload.updated_at = datetime.utcnow()
        session.add(upload)
        analysis.status = AnalysisStatus.running
        analysis.updated_at = datetime.utcnow()
        analysis.result_json = {"progress": {"completed_chunks": 0, "total_chunks": 0}}
        session.add(analysis)

        chunk_rows = session.exec(select(Chunk).where(Chunk.upload_id == upload_id).order_by(Chunk.index)).all()
        total_chunks = len(chunk_rows)
        analysis.result_json = {"progress": {"completed_chunks": 0, "total_chunks": total_chunks}}
        session.add(analysis)

    completed = 0
    collected_summaries: List[str] = []
    collected_issues: List[Dict[str, Any]] = []

    for chunk in chunk_rows:
        try:
            chunk_result = await run_in_threadpool(llm_callable, chunk.text, chunk.index, prompt, model, max_tokens)
        except Exception as exc:  # pragma: no cover - runtime safety
            logger.exception("LLM call failed", extra={"analysis_id": str(analysis_id), "chunk_index": chunk.index})
            with session_scope() as session:
                analysis = session.get(Analysis, analysis_id)
                if analysis:
                    analysis.status = AnalysisStatus.error
                    analysis.error = str(exc)
                    analysis.updated_at = datetime.utcnow()
                    session.add(analysis)
                upload = session.get(Upload, upload_id)
                if upload:
                    upload.status = UploadStatus.ready
                    upload.updated_at = datetime.utcnow()
                    session.add(upload)
            return

        summary = chunk_result.get("summary")
        issues = chunk_result.get("issues", [])
        if summary:
            collected_summaries.append(summary)
        for issue in issues:
            issue.setdefault("page_range", [chunk.page_start, chunk.page_end])
            issue.setdefault("severity", "medium")
            issue.setdefault("title", f"Chunk {chunk.index} insight")
            issue.setdefault("evidence_excerpt", chunk.text[:200])
            issue.setdefault("citations", [])
            collected_issues.append(issue)

        completed += 1
        with session_scope() as session:
            analysis = session.get(Analysis, analysis_id)
            if analysis and analysis.status == AnalysisStatus.running:
                analysis.result_json = {"progress": {"completed_chunks": completed, "total_chunks": total_chunks}}
                analysis.updated_at = datetime.utcnow()
                session.add(analysis)

    document_summary = "\n\n".join(collected_summaries) if collected_summaries else "No significant findings were generated."
    metadata = {
        "num_chunks": total_chunks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    final_payload = {
        "document_summary": document_summary,
        "issues": collected_issues,
        "metadata": metadata,
    }

    with session_scope() as session:
        analysis = session.get(Analysis, analysis_id)
        upload = session.get(Upload, upload_id)
        if analysis:
            analysis.status = AnalysisStatus.done
            analysis.result_json = final_payload
            analysis.error = None
            analysis.updated_at = datetime.utcnow()
            session.add(analysis)
        if upload:
            upload.status = UploadStatus.done
            upload.updated_at = datetime.utcnow()
            session.add(upload)
