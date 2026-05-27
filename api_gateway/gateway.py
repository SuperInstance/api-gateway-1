"""Gateway — orchestrates routing, middleware, and request transformation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api_gateway.middleware import Middleware, MiddlewareChain
from api_gateway.ratelimit import RateLimiter
from api_gateway.router import Request, Response, Router
from api_gateway.transform import RequestTransformer


@dataclass
class GatewayConfig:
    """Gateway-level configuration."""

    name: str = "api-gateway"
    default_content_type: str = "application/json"
    strip_trailing_slash: bool = True
    case_insensitive_matching: bool = False


class Gateway:
    """Top-level API gateway.

    Combines a :class:`Router`, a :class:`MiddlewareChain`, and an optional
    :class:`RequestTransformer` to process requests end-to-end.
    """

    def __init__(self, config: GatewayConfig | None = None) -> None:
        self.config = config or GatewayConfig()
        self.router = Router()
        self.middleware_chain = MiddlewareChain()
        self.transformer: RequestTransformer | None = None
        self._not_found_handler: Any = None

    def set_not_found_handler(self, handler: Any) -> None:
        self._not_found_handler = handler

    def use(self, middleware: Middleware) -> "Gateway":
        self.middleware_chain.add(middleware)
        return self

    def set_transformer(self, transformer: RequestTransformer) -> "Gateway":
        self.transformer = transformer
        return self

    def handle(self, request: Request) -> Response:
        """Process a request through the full pipeline."""
        # Normalise path
        path = request.path
        if self.config.strip_trailing_slash and len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        if self.config.case_insensitive_matching:
            path = path.lower()
        request.path = path

        # Request transforms
        if self.transformer:
            request = self.transformer.apply_to_request(request)

        # Route resolution
        route, match_info = self.router.resolve(request)
        if route is None:
            if self._not_found_handler:
                handler = self._not_found_handler
            else:
                return Response(status=404, body={"error": "Not found", "path": request.path})
        else:
            request.metadata["match_info"] = match_info
            handler = route.handler

        # Build middleware-wrapped handler
        wrapped = self.middleware_chain.build(handler)
        response = wrapped(request)

        # Response transforms
        if self.transformer:
            response = self.transformer.apply_to_response(response)

        # Ensure default content-type
        if "Content-Type" not in response.headers and self.config.default_content_type:
            response.headers["Content-Type"] = self.config.default_content_type

        return response
