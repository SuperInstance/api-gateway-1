# api-gateway

A pure-Python API gateway library with **routing**, **middleware**, **rate limiting**, and **request transformation**.

Built with dataclasses and type hints. Zero external dependencies beyond `pytest` for testing.

Part of the [Cocapn fleet](https://github.com/Lucineer/the-fleet).

---

## Installation

```bash
pip install api-gateway
```

Or from source:

```bash
git clone https://github.com/SuperInstance/api-gateway-1.git
cd api-gateway-1
pip install -e ".[dev]"
```

## Quick Start

```python
from api_gateway import (
    Gateway,
    Route,
    Request,
    Response,
    AuthMiddleware,
    CORSMiddleware,
    FixedWindowLimiter,
    RateLimitMiddleware,
    RequestTransformer,
    ApplyTo,
)

# Create the gateway
gw = Gateway()

# Add routes
@gw.router.route("/ping")
def ping(req: Request) -> Response:
    return Response(status=200, body={"message": "pong"})

@gw.router.route("/users", methods=["GET"])
def list_users(req: Request) -> Response:
    return Response(status=200, body={"users": ["alice", "bob"]})

# Prefix matching for API versions
@gw.router.route("/api/v1", match_mode=MatchMode.PREFIX)
def v1_proxy(req: Request) -> Response:
    return Response(status=200, body={"proxied": req.path})

# Add middleware
gw.use(CORSMiddleware(allow_origins="https://myapp.com"))
gw.use(AuthMiddleware(valid_keys={"sk-secret-123"}))
gw.use(RateLimitMiddleware(FixedWindowLimiter(limit=100, window_seconds=60)))

# Add response transformer
transformer = RequestTransformer()
transformer.add_header_rule(
    "server-header",
    lambda h: {**h, "Server": "MyGateway/1.0"},
    apply_to=ApplyTo.RESPONSE,
)
gw.set_transformer(transformer)

# Handle a request
from api_gateway.router import Request
req = Request(method="GET", path="/ping", headers={"X-API-Key": "sk-secret-123"})
response = gw.handle(req)
print(response.status)   # 200
print(response.body)     # {"message": "pong"}
```

## Components

### Router

Three matching modes — **exact**, **prefix**, and **regex** — with optional HTTP method filtering.

```python
from api_gateway.router import Router, Route, MatchMode

router = Router()

# Exact match
router.add_route(Route(path="/health", handler=lambda r: Response(body="ok")))

# Prefix match — catches /api/anything
router.add_route(Route(path="/api", handler=proxy_handler, match_mode=MatchMode.PREFIX))

# Regex match with named groups
router.add_route(
    Route(path=r"/users/(?P<id>\d+)", handler=user_handler, match_mode=MatchMode.REGEX)
)

# Method filter
router.add_route(Route(path="/data", handler=post_handler, methods=["POST"]))
```

### Middleware

Chain middleware in order — each wraps the next. Built-in middleware includes:

| Middleware | Purpose |
|---|---|
| `CORSMiddleware` | CORS headers and preflight handling |
| `AuthMiddleware` | API key validation |
| `LoggingMiddleware` | Request logging with timing |
| `RateLimitMiddleware` | Enforce rate limits |

```python
from api_gateway.middleware import MiddlewareChain, CORSMiddleware, AuthMiddleware

chain = MiddlewareChain()
chain.add(CORSMiddleware())
chain.add(AuthMiddleware(valid_keys={"key1", "key2"}))

# Or via the gateway:
gw.use(CORSMiddleware())
gw.use(AuthMiddleware(valid_keys={"key1"}))
```

Write custom middleware by implementing the `Middleware` protocol:

```python
from api_gateway.middleware import Middleware
from api_gateway.router import Request, Response

class TimingMiddleware(Middleware):
    def process(self, request, call_next):
        import time
        start = time.monotonic()
        response = call_next(request)
        elapsed = (time.monotonic() - start) * 1000
        response.headers["X-Response-Time"] = f"{elapsed:.1f}ms"
        return response
```

### Rate Limiting

Three algorithms, all in-memory:

- **TokenBucketLimiter** — smooth rate with burst allowance
- **FixedWindowLimiter** — simple counter per time window
- **SlidingWindowLimiter** — log-based precise sliding window

```python
from api_gateway.ratelimit import TokenBucketLimiter, FixedWindowLimiter, SlidingWindowLimiter

# 10 requests/second, burst of 20
limiter = TokenBucketLimiter(rate=10.0, capacity=20)

# 100 requests per 60-second window
limiter = FixedWindowLimiter(limit=100, window_seconds=60)

# Precise sliding window
limiter = SlidingWindowLimiter(limit=100, window_seconds=60)

result = limiter.allow("client-ip-1.2.3.4")
print(result.allowed)      # True/False
print(result.remaining)    # requests left
print(result.retry_after)  # seconds until next allowed (if rejected)
```

### Request Transformer

Modify headers and bodies on requests, responses, or both:

```python
from api_gateway.transform import RequestTransformer, ApplyTo

t = RequestTransformer()

# Add a header to all requests
t.add_header_rule("forwarded-for", lambda h: {**h, "X-Forwarded-For": "10.0.0.1"})

# Wrap response bodies
t.add_body_rule("envelope", lambda b: {"data": b, "version": "v1"}, apply_to=ApplyTo.RESPONSE)

# Apply to both
t.add_header_rule("trace", lambda h: {**h, "X-Trace-Id": "abc"}, apply_to=ApplyTo.BOTH)

gw.set_transformer(t)
```

## Running Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## License

MIT
