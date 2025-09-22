from fastapi import APIRouter
from openai import AsyncOpenAI

from app.config import settings

router = APIRouter()


@router.get("/ai")
async def ai_health():
    if not settings.openai_api_key:
        return {"ok": False, "reason": "missing key"}

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0,
        )
    except Exception as exc:  # pragma: no cover - network error handling
        return {"ok": False, "reason": str(exc)}

    return {
        "ok": True,
        "model": settings.openai_model,
        "usage": getattr(response, "usage", None),
    }
