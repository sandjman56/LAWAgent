from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlmodel import SQLModel

from .config import get_settings
from .models import get_engine
from .routers import analyze, uploads
from .utils.security import AuthMiddleware, RequestIDMiddleware, configure_logging


configure_logging()
settings = get_settings()
limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])

app = FastAPI(title="Legal Issue Spotter API", default_response_class=ORJSONResponse)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(settings.frontend_origin)],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_limiter_to_request(request: Request, call_next: Callable):  # type: ignore[override]
    request.state.limiter = limiter
    request.state.view_rate_limit = True
    response = await call_next(request)
    return response


@app.on_event("startup")
async def on_startup() -> None:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)


app.include_router(uploads.router)
app.include_router(analyze.router)
