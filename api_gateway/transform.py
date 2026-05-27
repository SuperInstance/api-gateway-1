"""Request/response transformation — header and body modification."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from api_gateway.router import Request, Response


class ApplyTo(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    BOTH = "both"


@dataclass
class TransformRule:
    """A single transformation rule."""

    name: str
    apply_to: ApplyTo = ApplyTo.REQUEST
    transform: Callable[[dict[str, str]], dict[str, str]] | None = None
    body_transform: Callable[[Any], Any] | None = None


class RequestTransformer:
    """Applies a sequence of transform rules to requests and responses."""

    def __init__(self) -> None:
        self._rules: list[TransformRule] = []

    def add_rule(self, rule: TransformRule) -> "RequestTransformer":
        self._rules.append(rule)
        return self

    def add_header_rule(
        self,
        name: str,
        header_transform: Callable[[dict[str, str]], dict[str, str]],
        apply_to: ApplyTo = ApplyTo.REQUEST,
    ) -> "RequestTransformer":
        self.add_rule(TransformRule(name=name, apply_to=apply_to, transform=header_transform))
        return self

    def add_body_rule(
        self,
        name: str,
        body_transform: Callable[[Any], Any],
        apply_to: ApplyTo = ApplyTo.REQUEST,
    ) -> "RequestTransformer":
        self.add_rule(TransformRule(name=name, apply_to=apply_to, body_transform=body_transform))
        return self

    def apply_to_request(self, request: Request) -> Request:
        for rule in self._rules:
            if rule.apply_to in (ApplyTo.REQUEST, ApplyTo.BOTH):
                if rule.transform:
                    request.headers = rule.transform(request.headers)
                if rule.body_transform and request.body is not None:
                    request.body = rule.body_transform(request.body)
        return request

    def apply_to_response(self, response: Response) -> Response:
        for rule in self._rules:
            if rule.apply_to in (ApplyTo.RESPONSE, ApplyTo.BOTH):
                if rule.transform:
                    response.headers = rule.transform(response.headers)
                if rule.body_transform and response.body is not None:
                    response.body = rule.body_transform(response.body)
        return response

    @property
    def rules(self) -> list[TransformRule]:
        return list(self._rules)
