from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.services.followup import answer_followup

router = APIRouter()


class FollowupMessage(BaseModel):
    role: str = Field(...)
    content: str = Field(...)

    @field_validator("role", "content", mode="before")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return str(value).strip()


class FollowupRequest(BaseModel):
    question: str = Field(...)
    context: str = Field(...)
    instruction: str | None = Field(default=None)
    document: str | None = Field(default=None)
    history: list[FollowupMessage] = Field(default_factory=list)

    @field_validator("question", "context", "instruction", "document", mode="before")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = str(value).strip()
        return text


class FollowupResponse(BaseModel):
    answer: str


@router.post("", response_model=FollowupResponse)
async def create_followup(request: FollowupRequest) -> FollowupResponse:
    question = (request.question or "").strip()
    context = (request.context or "").strip()
    instruction = (request.instruction or "").strip()
    document = (request.document or "").strip()
    history = [
        {"role": (message.role or "").strip(), "content": (message.content or "").strip()}
        for message in request.history
    ]

    if not question:
        raise HTTPException(status_code=400, detail="Follow-up question is required.")
    if not context:
        raise HTTPException(status_code=400, detail="Analysis context is required.")

    try:
        answer = await answer_followup(
            question=question,
            context=context,
            instruction=instruction,
            document=document,
            history=history,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Unable to generate a follow-up answer.") from exc

    return FollowupResponse(answer=answer)
