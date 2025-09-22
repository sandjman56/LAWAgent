from __future__ import annotations

import json
import re
from typing import Any, Dict

from openai import AsyncOpenAI, OpenAIError

from app.config import settings

_MODEL = "gpt-4o-mini"
_MAX_CHARS = 60000

_client = AsyncOpenAI(api_key=settings.openai_api_key)

_STYLE_HINTS = {
    "Concise bullets": "Respond with tight bullet points focused on the most material issues.",
    "Detailed memo": "Provide a structured memo-style response with headings and paragraphs.",
    "Checklist with citations": "Return a checklist summarizing issues and include citations for each item.",
}


def _build_prompt(text: str, instructions: str, style: str | None) -> list[Dict[str, Any]]:
    style_hint = _STYLE_HINTS.get(style or "", "")
    guidance = f"Style guidance: {style_hint}" if style_hint else ""

    user_prompt = f"""
You are LAWAgent, an expert legal assistant that spots issues in complex documents.
Analyze the provided material and follow the operator instructions.
Return a well-structured JSON object with the keys summary, findings, and citations.
Findings should be an array of objects with the keys issue, risk, suggestion, and optional span {{page, start, end}}.
Citations should be an array of objects with page and snippet fields.

Operator Instructions:
{instructions.strip()}
{guidance}

Document:
""".strip()

    document_chunk = text.strip()

    return [
        {
            "role": "system",
            "content": (
                "You are LAWAgent, a meticulous legal analyst. Keep responses factual, "
                "concise, and highlight material risks."
            ),
        },
        {"role": "user", "content": f"{user_prompt}\n{document_chunk}"},
    ]


def _coerce_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_findings(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        span = item.get("span") if isinstance(item.get("span"), dict) else None
        normalized.append(
            {
                "issue": _coerce_string(item.get("issue")),
                "risk": _coerce_string(item.get("risk")),
                "suggestion": _coerce_string(item.get("suggestion")),
                "span": span,
            }
        )
    return normalized


def _coerce_citations(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "page": item.get("page"),
                "snippet": _coerce_string(item.get("snippet")),
            }
        )
    return normalized


def _extract_json_payload(content: str) -> Dict[str, Any] | None:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None
    return None


async def analyze_text(
    text: str,
    instructions: str,
    style: str | None = None,
    return_json: bool = True,
) -> Dict[str, Any]:
    material = text.strip()
    if not material:
        raise ValueError("No text found to analyze.")

    truncated = False
    if len(material) > _MAX_CHARS:
        material = material[:_MAX_CHARS]
        truncated = True

    messages = _build_prompt(material, instructions, style)

    try:
        completion = await _client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            temperature=0.2,
        )
    except OpenAIError as exc:  # pragma: no cover - network error handling
        raise ValueError("The AI service is temporarily unavailable. Please try again later.") from exc

    content = completion.choices[0].message.content if completion.choices else ""
    content = content or ""

    payload = _extract_json_payload(content)

    summary = ""
    findings: list[Dict[str, Any]] = []
    citations: list[Dict[str, Any]] = []

    if payload:
        summary = _coerce_string(payload.get("summary") or payload.get("Summary"))
        findings = _coerce_findings(payload.get("findings") or payload.get("Findings"))
        citations = _coerce_citations(payload.get("citations") or payload.get("Citations"))
    else:
        summary = content.strip()

    if truncated:
        notice = " Input truncated for analysis due to size limitations."
        summary = f"{summary}{notice}" if summary else notice.strip()

    result: Dict[str, Any] = {
        "summary": summary,
        "findings": findings,
        "citations": citations,
    }

    if return_json:
        result["raw_json"] = payload if payload is not None else {"unparsed": content.strip()}

    return result
