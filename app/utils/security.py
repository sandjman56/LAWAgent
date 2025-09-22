from __future__ import annotations

import logging
from typing import Iterable
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_401_UNAUTHORIZED

from ..config import get_settings


logger = logging.getLogger("lawagent.security")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every request for traceable logs."""

    def __init__(self, app, header_name: str = "X-Request-ID") -> None:  # type: ignore[override]
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = request.headers.get(self.header_name, str(uuid4()))
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers[self.header_name] = request_id
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """Simple bearer token authentication middleware."""

    def __init__(self, app, exempt_paths: Iterable[str] | None = None) -> None:  # type: ignore[override]
        super().__init__(app)
        self.settings = get_settings()
        self.exempt_paths = set(exempt_paths or {"/openapi.json", "/docs", "/docs/oauth2-redirect"})

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        if request.method == "OPTIONS" or request.url.path.startswith("/public") or request.url.path in self.exempt_paths:
            return await call_next(request)

        header = request.headers.get("Authorization")
        if not header or not header.lower().startswith("bearer "):
            logger.warning("missing bearer token", extra={"path": request.url.path, "request_id": getattr(request.state, "request_id", None)})
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

        token = header.split(" ", 1)[1].strip()
        if token != self.settings.auth_token:
            logger.warning("invalid bearer token", extra={"path": request.url.path, "request_id": getattr(request.state, "request_id", None)})
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")

        return await call_next(request)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s message=%(message)s",
    )

    class RequestIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
            if not hasattr(record, "request_id"):
                record.request_id = "-"
            return True

    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdFilter())
