# api-gateway-1 — Pure-Python API Gateway

**Routing, middleware, rate limiting, and request transformation. Zero external dependencies beyond pytest.**

## What This Gives You

- **Router** — pattern-based URL routing with parameter extraction
- **Middleware chain** — composable request/response processing pipeline
- **Rate limiting** — token bucket, sliding window, and fixed window algorithms
- **Request transformation** — modify requests and responses with configurable rules
- **Pure Python** — built with dataclasses and type hints, no framework dependency

## Quick Start

```bash
pip install api-gateway
```

```python
from api_gateway import Gateway, Router, Route, Middleware, RateLimiter

# Set up routing
router = Router()
router.add(Route(path="/v1/chat", handler=chat_handler))
router.add(Route(path="/v1/models", handler=models_handler))

# Add middleware
gateway = Gateway(router=router)
gateway.use(Middleware(rate_limit=RateLimiter(max_requests=100, window_seconds=60)))
gateway.use(Middleware(transform=RequestTransformer(add_header={"X-Fleet": "cocapn"})))

# Process a request
response = gateway.handle(request)
```

## API Reference

### `Gateway(router, middleware=None)` — `handle(request) → response`
### `Router` — `add(route)`, `match(path) → Route`
### `Route(path, handler, methods=None)`
### `Middleware(chain)` — Composable request/response processor
### `RateLimiter` / `TokenBucketLimiter` / `SlidingWindowLimiter` / `FixedWindowLimiter`
### `RequestTransformer(rules)` — `TransformRule(field, action, value)`

## How It Fits

The gateway backing [cocapn-sdk](https://github.com/SuperInstance/cocapn-sdk) and [cocapn-py](https://github.com/SuperInstance/cocapn-py) — the "one API key, any model" endpoint runs through this.

- **[cocapn-sdk](https://github.com/SuperInstance/cocapn-sdk)** — Node.js SDK (talks to this gateway)
- **[Claude-PRISM-CF](https://github.com/SuperInstance/Claude-PRISM-CF)** — Edge routing optimization
- **[cache-layer-optimizer](https://github.com/SuperInstance/cache-layer-optimizer)** — Response caching

## Testing

```bash
pip install pytest
pytest tests/
```

## Installation

```bash
pip install api-gateway
```

Python 3.10+. MIT license.

## Documentation

📚 [OpenConstruct Docs](https://github.com/SuperInstance/openconstruct-docs)
