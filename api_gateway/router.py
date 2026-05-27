"""Router with flexible path matching — exact, prefix, and regex."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Pattern


class MatchMode(Enum):
    EXACT = "exact"
    PREFIX = "prefix"
    REGEX = "regex"


@dataclass
class Request:
    """Minimal request representation used throughout the library."""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    query_params: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    """Minimal response representation."""

    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None

    def json(self) -> dict[str, Any]:
        if isinstance(self.body, dict):
            return self.body
        return {"data": self.body}


Handler = Callable[[Request], Response]


@dataclass
class Route:
    """A single route definition."""

    path: str
    handler: Handler
    methods: list[str] | None = None
    match_mode: MatchMode = MatchMode.EXACT
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _compiled_pattern: Pattern[str] | None = field(default=None, repr=False, init=False)

    def __post_init__(self) -> None:
        if self.methods is not None:
            self.methods = [m.upper() for m in self.methods]
        if self.match_mode == MatchMode.REGEX:
            self._compiled_pattern = re.compile(self.path)

    def matches(self, request: Request) -> bool:
        """Return True if this route matches the incoming request."""
        # Method filter
        if self.methods is not None and request.method.upper() not in self.methods:
            return False

        if self.match_mode == MatchMode.EXACT:
            return request.path == self.path
        elif self.match_mode == MatchMode.PREFIX:
            return request.path.startswith(self.path)
        elif self.match_mode == MatchMode.REGEX:
            assert self._compiled_pattern is not None
            return self._compiled_pattern.search(request.path) is not None
        return False


class Router:
    """Collects routes and dispatches requests to the first matching handler."""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add_route(self, route: Route) -> None:
        self._routes.append(route)

    def route(
        self,
        path: str,
        methods: list[str] | None = None,
        match_mode: MatchMode = MatchMode.EXACT,
        name: str | None = None,
    ) -> Callable[[Handler], Handler]:
        """Decorator-style route registration."""

        def decorator(handler: Handler) -> Handler:
            self.add_route(Route(path=path, handler=handler, methods=methods, match_mode=match_mode, name=name))
            return handler

        return decorator

    def resolve(self, request: Request) -> tuple[Route | None, dict[str, Any]]:
        """Find the first matching route. Returns (route, match_info)."""
        for route in self._routes:
            if route.matches(request):
                match_info: dict[str, Any] = {"route_name": route.name}
                if route.match_mode == MatchMode.REGEX and route._compiled_pattern:
                    m = route._compiled_pattern.search(request.path)
                    if m:
                        match_info["regex_groups"] = m.groups()
                        match_info["regex_groupdict"] = m.groupdict()
                return route, match_info
        return None, {}

    @property
    def routes(self) -> list[Route]:
        return list(self._routes)
