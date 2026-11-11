"""Correlation IDs: accept a well-formed X-Request-ID or generate one; echo it back."""

import re
import uuid
from contextvars import ContextVar

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_VALID = re.compile(r"^[A-Za-z0-9\-_.]{8,64}$")


def get_correlation_id() -> str | None:
    return _correlation_id.get()


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = None
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                incoming = value.decode("latin-1")
        cid = incoming if incoming and _VALID.match(incoming) else uuid.uuid4().hex
        token = _correlation_id.set(cid)
        structlog.contextvars.bind_contextvars(correlation_id=cid)

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", cid.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            _correlation_id.reset(token)
            structlog.contextvars.unbind_contextvars("correlation_id")
