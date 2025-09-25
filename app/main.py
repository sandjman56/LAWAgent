from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.routers import health, issue_spotter, witness_finder

app = FastAPI(title="LAWAgent")

origins = ["http://localhost:8000", "http://127.0.0.1:8000"]
if settings.allowed_origins:
    origins.extend([o.strip() for o in settings.allowed_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(issue_spotter.router, prefix="/api/issue-spotter", tags=["Issue Spotter"])
app.include_router(witness_finder.router, prefix="/api/witness_finder", tags=["Witness Finder"])
app.include_router(health.router, prefix="/api/health", tags=["Health"])
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")


@app.get("/witness_finder", include_in_schema=False)
async def witness_finder_page() -> FileResponse:
    return FileResponse("app/static/witness-finder.html")
