"""Comprehensive tests for api-gateway."""

import re
import time

import pytest

from api_gateway.gateway import Gateway, GatewayConfig
from api_gateway.middleware import (
    AuthMiddleware,
    CORSMiddleware,
    LoggingMiddleware,
    MiddlewareChain,
    RateLimitMiddleware,
)
from api_gateway.ratelimit import (
    FixedWindowLimiter,
    RateLimitResult,
    SlidingWindowLimiter,
    TokenBucketLimiter,
)
from api_gateway.router import MatchMode, Request, Response, Route, Router
from api_gateway.transform import ApplyTo, RequestTransformer, TransformRule


# ── Helpers ──────────────────────────────────────────────────────────


def _req(method: str = "GET", path: str = "/", **kw: object) -> Request:
    return Request(method=method, path=path, **kw)  # type: ignore[arg-type]


def _ok(body: object = "ok") -> Response:
    return Response(status=200, body=body)


# ── Router tests ─────────────────────────────────────────────────────


class TestRouter:
    def test_exact_match(self) -> None:
        r = Router()
        r.add_route(Route(path="/hello", handler=lambda r: _ok("hello")))
        route, info = r.resolve(_req(path="/hello"))
        assert route is not None

    def test_exact_no_match(self) -> None:
        r = Router()
        r.add_route(Route(path="/hello", handler=lambda r: _ok()))
        route, _ = r.resolve(_req(path="/other"))
        assert route is None

    def test_prefix_match(self) -> None:
        r = Router()
        r.add_route(Route(path="/api", handler=lambda r: _ok(), match_mode=MatchMode.PREFIX))
        route, _ = r.resolve(_req(path="/api/users/123"))
        assert route is not None

    def test_prefix_no_match(self) -> None:
        r = Router()
        r.add_route(Route(path="/api", handler=lambda r: _ok(), match_mode=MatchMode.PREFIX))
        route, _ = r.resolve(_req(path="/other"))
        assert route is None

    def test_regex_match(self) -> None:
        r = Router()
        r.add_route(Route(path=r"/users/(?P<id>\d+)", handler=lambda r: _ok(), match_mode=MatchMode.REGEX))
        route, info = r.resolve(_req(path="/users/42"))
        assert route is not None
        assert info.get("regex_groupdict", {}).get("id") == "42"

    def test_regex_no_match(self) -> None:
        r = Router()
        r.add_route(Route(path=r"/users/\d+", handler=lambda r: _ok(), match_mode=MatchMode.REGEX))
        route, _ = r.resolve(_req(path="/users/abc"))
        assert route is None

    def test_method_filter(self) -> None:
        r = Router()
        r.add_route(Route(path="/data", handler=lambda r: _ok(), methods=["POST"]))
        route, _ = r.resolve(_req("GET", "/data"))
        assert route is None
        route, _ = r.resolve(_req("POST", "/data"))
        assert route is not None

    def test_decorator_registration(self) -> None:
        r = Router()

        @r.route("/ping")
        def ping(req: Request) -> Response:
            return _ok("pong")

        assert len(r.routes) == 1
        route, _ = r.resolve(_req(path="/ping"))
        assert route is not None

    def test_first_match_wins(self) -> None:
        r = Router()
        r.add_route(Route(path="/a", handler=lambda r: _ok("first"), match_mode=MatchMode.PREFIX))
        r.add_route(Route(path="/a/b", handler=lambda r: _ok("second")))
        route, _ = r.resolve(_req(path="/a/b"))
        assert route is not None
        # prefix /a matches first
        resp = route.handler(_req())
        assert resp.body == "first"


# ── Middleware tests ──────────────────────────────────────────────────


class TestMiddlewareChain:
    def test_empty_chain(self) -> None:
        chain = MiddlewareChain()
        wrapped = chain.build(lambda r: _ok())
        resp = wrapped(_req())
        assert resp.status == 200

    def test_single_middleware(self) -> None:
        class AddHeader:
            def process(self, request, call_next):
                resp = call_next(request)
                resp.headers["X-Test"] = "yes"
                return resp

        chain = MiddlewareChain()
        chain.add(AddHeader())
        wrapped = chain.build(lambda r: _ok())
        resp = wrapped(_req())
        assert resp.headers["X-Test"] == "yes"

    def test_middleware_order(self) -> None:
        order: list[str] = []

        class M1:
            def process(self, request, call_next):
                order.append("m1-before")
                resp = call_next(request)
                order.append("m1-after")
                return resp

        class M2:
            def process(self, request, call_next):
                order.append("m2-before")
                resp = call_next(request)
                order.append("m2-after")
                return resp

        chain = MiddlewareChain()
        chain.add(M1()).add(M2())
        wrapped = chain.build(lambda r: _ok())
        wrapped(_req())
        assert order == ["m1-before", "m2-before", "m2-after", "m1-after"]


class TestCORSMiddleware:
    def test_options_preflight(self) -> None:
        cors = CORSMiddleware(allow_origins="https://example.com")
        chain = MiddlewareChain().add(cors).build(lambda r: _ok())
        resp = chain(_req("OPTIONS", "/anything"))
        assert resp.status == 204
        assert resp.headers["Access-Control-Allow-Origin"] == "https://example.com"

    def test_adds_cors_to_normal_response(self) -> None:
        cors = CORSMiddleware()
        chain = MiddlewareChain().add(cors).build(lambda r: _ok())
        resp = chain(_req("GET", "/anything"))
        assert "Access-Control-Allow-Origin" in resp.headers


class TestAuthMiddleware:
    def test_missing_key(self) -> None:
        auth = AuthMiddleware(valid_keys={"secret123"})
        chain = MiddlewareChain().add(auth).build(lambda r: _ok())
        resp = chain(_req())
        assert resp.status == 401

    def test_invalid_key(self) -> None:
        auth = AuthMiddleware(valid_keys={"secret123"})
        chain = MiddlewareChain().add(auth).build(lambda r: _ok())
        resp = chain(_req(headers={"X-API-Key": "wrong"}))
        assert resp.status == 403

    def test_valid_key(self) -> None:
        auth = AuthMiddleware(valid_keys={"secret123"})
        chain = MiddlewareChain().add(auth).build(lambda r: _ok())
        resp = chain(_req(headers={"X-API-Key": "secret123"}))
        assert resp.status == 200


class TestLoggingMiddleware:
    def test_logs_request(self) -> None:
        messages: list[str] = []
        log = LoggingMiddleware(logger=messages.append)
        chain = MiddlewareChain().add(log).build(lambda r: _ok())
        chain(_req("GET", "/test"))
        assert len(messages) == 1
        assert "GET" in messages[0]
        assert "/test" in messages[0]


# ── Rate limiter tests ───────────────────────────────────────────────


class TestTokenBucketLimiter:
    def test_allows_within_capacity(self) -> None:
        limiter = TokenBucketLimiter(rate=10.0, capacity=5)
        for _ in range(5):
            r = limiter.allow("key1")
            assert r.allowed

    def test_rejects_over_capacity(self) -> None:
        limiter = TokenBucketLimiter(rate=1.0, capacity=2)
        assert limiter.allow("key1").allowed
        assert limiter.allow("key1").allowed
        assert not limiter.allow("key1").allowed

    def test_refills_over_time(self) -> None:
        limiter = TokenBucketLimiter(rate=1000.0, capacity=1)
        assert limiter.allow("key1").allowed
        assert not limiter.allow("key1").allowed
        time.sleep(0.002)
        assert limiter.allow("key1").allowed

    def test_separate_keys(self) -> None:
        limiter = TokenBucketLimiter(rate=1.0, capacity=1)
        assert limiter.allow("a").allowed
        assert limiter.allow("b").allowed


class TestFixedWindowLimiter:
    def test_allows_within_limit(self) -> None:
        limiter = FixedWindowLimiter(limit=3, window_seconds=60)
        for _ in range(3):
            assert limiter.allow("key1").allowed

    def test_rejects_over_limit(self) -> None:
        limiter = FixedWindowLimiter(limit=2, window_seconds=60)
        limiter.allow("key1")
        limiter.allow("key1")
        assert not limiter.allow("key1").allowed

    def test_window_resets(self) -> None:
        limiter = FixedWindowLimiter(limit=1, window_seconds=0.05)
        assert limiter.allow("key1").allowed
        assert not limiter.allow("key1").allowed
        time.sleep(0.06)
        assert limiter.allow("key1").allowed


class TestSlidingWindowLimiter:
    def test_allows_within_limit(self) -> None:
        limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
        for _ in range(3):
            assert limiter.allow("key1").allowed

    def test_rejects_over_limit(self) -> None:
        limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
        limiter.allow("key1")
        limiter.allow("key1")
        assert not limiter.allow("key1").allowed

    def test_window_slides(self) -> None:
        limiter = SlidingWindowLimiter(limit=1, window_seconds=0.05)
        assert limiter.allow("key1").allowed
        assert not limiter.allow("key1").allowed
        time.sleep(0.06)
        assert limiter.allow("key1").allowed


class TestRateLimitMiddleware:
    def test_allows_under_limit(self) -> None:
        limiter = FixedWindowLimiter(limit=5, window_seconds=60)
        mw = RateLimitMiddleware(limiter)
        chain = MiddlewareChain().add(mw).build(lambda r: _ok())
        resp = chain(_req())
        assert resp.status == 200

    def test_rejects_over_limit(self) -> None:
        limiter = FixedWindowLimiter(limit=1, window_seconds=60)
        mw = RateLimitMiddleware(limiter)
        chain = MiddlewareChain().add(mw).build(lambda r: _ok())
        chain(_req())
        resp = chain(_req())
        assert resp.status == 429


# ── Transformer tests ────────────────────────────────────────────────


class TestRequestTransformer:
    def test_header_transform(self) -> None:
        t = RequestTransformer()
        t.add_header_rule("add-xff", lambda h: {**h, "X-Forwarded-For": "1.2.3.4"})
        req = _req(headers={"Host": "example.com"})
        req = t.apply_to_request(req)
        assert req.headers["X-Forwarded-For"] == "1.2.3.4"

    def test_body_transform(self) -> None:
        t = RequestTransformer()
        t.add_body_rule("wrap", lambda b: {"wrapped": b})
        req = _req(body={"msg": "hi"})
        req = t.apply_to_request(req)
        assert req.body == {"wrapped": {"msg": "hi"}}

    def test_response_transform(self) -> None:
        t = RequestTransformer()
        t.add_header_rule(
            "server-header",
            lambda h: {**h, "Server": "Gateway/1.0"},
            apply_to=ApplyTo.RESPONSE,
        )
        resp = _ok()
        resp = t.apply_to_response(resp)
        assert resp.headers["Server"] == "Gateway/1.0"

    def test_both_transform(self) -> None:
        t = RequestTransformer()
        t.add_header_rule(
            "trace",
            lambda h: {**h, "X-Trace": "on"},
            apply_to=ApplyTo.BOTH,
        )
        req = _req()
        req = t.apply_to_request(req)
        assert req.headers["X-Trace"] == "on"
        resp = Response()
        resp = t.apply_to_response(resp)
        assert resp.headers["X-Trace"] == "on"


# ── Gateway integration tests ────────────────────────────────────────


class TestGateway:
    def _make_gateway(self) -> Gateway:
        gw = Gateway()

        @gw.router.route("/ping")
        def ping(req: Request) -> Response:
            return _ok("pong")

        @gw.router.route("/users", methods=["GET"])
        def list_users(req: Request) -> Response:
            return _ok({"users": []})

        @gw.router.route("/api", match_mode=MatchMode.PREFIX)
        def api_catchall(req: Request) -> Response:
            return _ok({"path": req.path})

        return gw

    def test_basic_routing(self) -> None:
        gw = self._make_gateway()
        resp = gw.handle(_req("GET", "/ping"))
        assert resp.status == 200
        assert resp.body == "pong"

    def test_404(self) -> None:
        gw = self._make_gateway()
        resp = gw.handle(_req("GET", "/nonexistent"))
        assert resp.status == 404

    def test_method_filtered(self) -> None:
        gw = self._make_gateway()
        resp = gw.handle(_req("DELETE", "/users"))
        assert resp.status == 404  # no DELETE route

    def test_prefix_routing(self) -> None:
        gw = self._make_gateway()
        resp = gw.handle(_req("GET", "/api/v2/things"))
        assert resp.status == 200
        assert resp.body["path"] == "/api/v2/things"

    def test_trailing_slash_strip(self) -> None:
        gw = Gateway()
        gw.router.add_route(Route(path="/hello", handler=lambda r: _ok("hi")))
        resp = gw.handle(_req("GET", "/hello/"))
        assert resp.status == 200

    def test_middleware_integration(self) -> None:
        gw = Gateway()
        gw.use(AuthMiddleware(valid_keys={"key1"}))
        gw.router.add_route(Route(path="/secret", handler=lambda r: _ok("data")))
        resp = gw.handle(_req("GET", "/secret", headers={"X-API-Key": "key1"}))
        assert resp.status == 200
        resp = gw.handle(_req("GET", "/secret"))
        assert resp.status == 401

    def test_transformer_integration(self) -> None:
        t = RequestTransformer()
        t.add_header_rule("server", lambda h: {**h, "Server": "GW"}, apply_to=ApplyTo.RESPONSE)
        gw = Gateway()
        gw.set_transformer(t)
        gw.router.add_route(Route(path="/t", handler=lambda r: _ok()))
        resp = gw.handle(_req("GET", "/t"))
        assert resp.headers.get("Server") == "GW"

    def test_custom_not_found(self) -> None:
        gw = Gateway()
        gw.set_not_found_handler(lambda r: Response(status=444, body={"custom": True}))
        resp = gw.handle(_req("GET", "/nope"))
        assert resp.status == 444

    def test_case_insensitive(self) -> None:
        cfg = GatewayConfig(case_insensitive_matching=True)
        gw = Gateway(config=cfg)
        gw.router.add_route(Route(path="/hello", handler=lambda r: _ok()))
        resp = gw.handle(_req("GET", "/HELLO"))
        assert resp.status == 200

    def test_default_content_type(self) -> None:
        gw = Gateway()
        gw.router.add_route(Route(path="/data", handler=lambda r: _ok({"x": 1})))
        resp = gw.handle(_req("GET", "/data"))
        assert resp.headers["Content-Type"] == "application/json"
