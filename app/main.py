from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import health, issue_spotter
from app.routers.witness_finder import router as witness_finder_router

app = FastAPI(title="LAWAgent")

origins = ["http://localhost:8000", "http://127.0.0.1:8000", "*"]
if settings.allowed_origins:
    origins.extend([o.strip() for o in settings.allowed_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(issue_spotter.router, prefix="/api/issue-spotter", tags=["Issue Spotter"])
app.include_router(witness_finder_router)
app.include_router(health.router, prefix="/api/health", tags=["Health"])
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")


@app.get("/witness_finder", include_in_schema=False)
async def witness_finder_page(request: Request):
    accept = request.headers.get("accept", "")
    wants_html = "text/html" in accept or "*/*" in accept
    if wants_html and "application/json" not in accept.split(",")[0]:
        return FileResponse("app/static/witness-finder.html")
    return JSONResponse({"service": "witness_finder", "hint": "Use /api/witness_finder/search for POST"})
