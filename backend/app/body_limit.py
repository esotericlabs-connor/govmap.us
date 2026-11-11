"""Reject oversized HTTP request bodies before any route buffers them.

Every public route except ``POST /api/report`` is a bodiless GET, and a report
is a few KiB of JSON. The report model's Pydantic ``max_length`` limits apply
only after FastAPI has read the whole body into memory, so without this cap a
client could stream an arbitrarily large body into the API process (which also
hosts the pipeline scheduler).
"""

from __future__ import annotations

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST_BODY_BYTES = 64 * 1024
_TOO_LARGE = "request body too large"


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None  # the ASGI server rejects malformed lengths itself
    return None


class BodySizeLimitMiddleware:
    """Pure ASGI middleware: a declared ``Content-Length`` over the cap is
    refused before the app runs; an undeclared (chunked) body is counted as it
    streams and refused the moment it crosses the cap. FastAPI re-raises
    ``HTTPException`` from body reading, so the streamed case is a clean 413."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            response = JSONResponse({"detail": _TOO_LARGE}, status_code=413)
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status_code=413, detail=_TOO_LARGE)
            return message

        await self.app(scope, limited_receive, send)
