from __future__ import annotations

import logging

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
    "Use the supplied issue spotter analysis to answer questions clearly, "
    "empathetically, and with practical legal insight. Reference the context when useful."
)


async def answer_followup(question: str, context: str) -> str:
    clean_question = (question or "").strip()
    clean_context = (context or "").strip()

    if not clean_question:
        raise ValueError("Follow-up question is required.")
    if not clean_context:
        raise ValueError("Analysis context is required for follow-up answers.")

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Here is the prior issue spotter analysis for context:\n"
                f"{clean_context}\n\n"
                "Answer the user's follow-up question in a conversational, explanatory tone:\n"
                f"{clean_question}"
            ),
        },
    ]

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
