from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    OpenAIError,
    RateLimitError,
)

from app.config import settings

logger = logging.getLogger("lawagent.followup")

_MODEL = settings.openai_model
_client = AsyncOpenAI(api_key=settings.openai_api_key)

_SYSTEM_PROMPT = (
    "You are LAWAgent's conversational follow-up assistant. "
    "Use the supplied issue spotter analysis, operator instructions, document excerpts, and conversation "
    "history to answer questions clearly, empathetically, and with practical legal insight. "
    "Reference the context when useful and keep replies conversational."
)


async def answer_followup(
    question: str,
    context: str,
    instruction: str | None = None,
    document: str | None = None,
    history: Sequence[Mapping[str, str] | object] | None = None,
) -> str:
    clean_question = (question or "").strip()
    clean_context = (context or "").strip()
    clean_instruction = (instruction or "").strip()
    clean_document = (document or "").strip()

    if not clean_question:
        raise ValueError("Follow-up question is required.")
    if not clean_context:
        raise ValueError("Analysis context is required for follow-up answers.")

    sanitized_history: list[dict[str, str]] = []
    if history:
        for entry in history:
            role_value = ""
            content_value = ""
            if isinstance(entry, Mapping):
                role_value = str(entry.get("role", ""))
                content_value = str(entry.get("content", ""))
            else:  # pragma: no cover - defensive
                role_value = str(getattr(entry, "role", ""))
                content_value = str(getattr(entry, "content", ""))

            role = role_value.strip().lower()
            content = content_value.strip()
            if not content:
                continue
            if role not in {"assistant", "user", "system"}:
                role = "assistant" if role == "lawagent" else "user"
            if role == "system":
                role = "assistant"
            sanitized_history.append({"role": role, "content": content})

    if sanitized_history:
        sanitized_history = sanitized_history[-12:]

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                "Issue Spotter analysis context (summary, findings, citations, raw JSON):\n"
                f"{clean_context}"
            ),
        },
    ]

    if clean_instruction:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Operator instructions and preferences provided for the analysis:\n"
                    f"{clean_instruction}"
                ),
            }
        )

    if clean_document:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Original document text or description supplied with the analysis:\n"
                    f"{clean_document}"
                ),
            }
        )

    messages.extend(sanitized_history)

    user_prompt = (
        "Using the analysis, instructions, and document context above, answer this follow-up question "
        "in a conversational tone. Reference relevant insights when helpful and clarify next steps:\n"
        f"{clean_question}"
    )
    messages.append({"role": "user", "content": user_prompt})

    try:
        completion = await _client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            temperature=0.45,
            timeout=45,
        )
    except AuthenticationError as exc:  # pragma: no cover - network error handling
        logger.exception("Authentication failed during follow-up call.")
        raise ValueError("Authentication with the AI provider failed. Check your API key.") from exc
    except RateLimitError as exc:  # pragma: no cover - network error handling
        logger.exception("Rate limit hit while requesting follow-up answer.")
        raise ValueError("Rate limit reached. Please wait a moment and try again.") from exc
    except APIConnectionError as exc:  # pragma: no cover - network error handling
        logger.exception("Network error while requesting follow-up answer.")
        raise ValueError("Network error: unable to reach the AI service.") from exc
    except APIStatusError as exc:  # pragma: no cover - network error handling
        status = getattr(exc, "status_code", None)
        logger.exception("OpenAI returned an error status for follow-up (status=%s).", status)
        if status and 500 <= status < 600:
            raise ValueError("AI provider encountered a server error. Try again later.") from exc
        raise ValueError("AI request failed. Verify the model and inputs.") from exc
    except BadRequestError as exc:  # pragma: no cover - network error handling
        logger.exception("Bad request while requesting follow-up answer.")
        raise ValueError("The follow-up request was invalid or too large.") from exc
    except OpenAIError as exc:  # pragma: no cover - network error handling
        logger.exception("Unexpected OpenAI error during follow-up answer.")
        raise ValueError("The AI service is temporarily unavailable. Try again later.") from exc

    content = completion.choices[0].message.content if completion.choices else ""
    answer = (content or "").strip()
    if not answer:
        raise ValueError("The AI did not return a follow-up answer.")

    return answer
