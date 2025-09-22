from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.analysis import analyze_text
from app.utils.extract import extract_text_from_file

router = APIRouter()


class TextReq(BaseModel):
    text: str
    instructions: str
    style: str | None = None
    return_json: bool = True


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    instructions: str = Form(...),
    style: str | None = Form(None),
    return_json: bool = Form(True),
):
    if not instructions.strip():
        raise HTTPException(status_code=400, detail="Instructions are required.")

    try:
        text = await extract_text_from_file(file)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return await analyze_text(text, instructions, style, return_json)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Unable to analyze the document.") from exc


@router.post("/text")
async def from_text(req: TextReq):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Provide text to analyze or upload a file.")
    if not req.instructions.strip():
        raise HTTPException(status_code=400, detail="Instructions are required.")

    try:
        return await analyze_text(req.text, req.instructions, req.style, req.return_json)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Unable to analyze the text.") from exc
