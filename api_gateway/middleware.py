"""Middleware chain for request/response processing."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from api_gateway.router import Request, Response


class Middleware(ABC):
    """Base class for all middleware."""

    @abstractmethod
    def process(self, request: Request, call_next: Any) -> Response:
        """Process a request. Call ``call_next(request)`` to continue the chain."""
        ...


class MiddlewareChain:
    """Ordered chain of middleware wrapping a final handler."""

    def __init__(self) -> None:
        self._middlewares: list[Middleware] = []

    def add(self, middleware: Middleware) -> "MiddlewareChain":
        self._middlewares.append(middleware)
        return self

    def build(self, handler: Any) -> Any:
        """Wrap *handler* with all middleware and return a single callable."""

        def wrapped(request: Request) -> Response:
            current = handler

            for mw in reversed(self._middlewares):
                prev = current

                def make_next(p: Any, m: Middleware) -> Any:
                    def nxt(req: Request) -> Response:
                        return m.process(req, p)

                    return nxt

                current = make_next(prev, mw)

            return current(request)

        return wrapped

    @property
    def middlewares(self) -> list[Middleware]:
        return list(self._middlewares)


# ── Built-in middleware ───────────────────────────────────────────────


class CORSMiddleware(Middleware):
    """Adds Cross-Origin Resource Sharing headers."""

    def __init__(
        self,
        allow_origins: str = "*",
        allow_methods: str = "GET, POST, PUT, DELETE, PATCH, OPTIONS",
        allow_headers: str = "Content-Type, Authorization, X-API-Key",
        max_age: int = 600,
    ) -> None:
        self.allow_origins = allow_origins
        self.allow_methods = allow_methods
        self.allow_headers = allow_headers
        self.max_age = max_age

    def process(self, request: Request, call_next: Any) -> Response:
        if request.method.upper() == "OPTIONS":
            return Response(
                status=204,
                headers={
                    "Access-Control-Allow-Origin": self.allow_origins,
                    "Access-Control-Allow-Methods": self.allow_methods,
                    "Access-Control-Allow-Headers": self.allow_headers,
                    "Access-Control-Max-Age": str(self.max_age),
                },
            )
        response = call_next(request)
        response.headers["Access-Control-Allow-Origin"] = self.allow_origins
        return response


class AuthMiddleware(Middleware):
    """Validates an API key in ``X-API-Key`` header."""

    def __init__(self, valid_keys: set[str] | None = None, header_name: str = "X-API-Key") -> None:
        self.valid_keys = valid_keys or set()
        self.header_name = header_name

    def process(self, request: Request, call_next: Any) -> Response:
        key = request.headers.get(self.header_name)
        if not key:
            return Response(status=401, body={"error": "Missing API key"})
        if key not in self.valid_keys:
            return Response(status=403, body={"error": "Invalid API key"})
        request.metadata["authenticated_key"] = key
        return call_next(request)


class LoggingMiddleware(Middleware):
    """Logs method, path, status and duration via a callback."""

    def __init__(self, logger: Any | None = None) -> None:
        self.logger = logger or print

    def process(self, request: Request, call_next: Any) -> Response:
        start = time.monotonic()
        response = call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        self.logger(f"{request.method} {request.path} → {response.status} ({elapsed_ms:.1f}ms)")
        return response


class RateLimitMiddleware(Middleware):
    """Enforces rate limiting before passing the request on."""

    def __init__(self, limiter: Any, key_func: Any | None = None) -> None:
        self.limiter = limiter
        self.key_func = key_func or (lambda req: req.headers.get("X-Forwarded-For", "default"))

    def process(self, request: Request, call_next: Any) -> Response:
        key = self.key_func(request)
        result = self.limiter.allow(key)
        if not result.allowed:
            return Response(
                status=429,
                headers={"Retry-After": str(result.retry_after or 60)},
                body={"error": "Rate limit exceeded"},
            )
        return call_next(request)
