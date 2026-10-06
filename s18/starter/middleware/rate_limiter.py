"""
S18 — Rate Limiting Middleware
==============================

TODO 2: Implement rate limiting with slowapi.

Why rate limit?
  Without limits, a single user (or a bot) can hammer the /chat endpoint
  continuously, exhausting your Groq token budget in minutes and making
  the service unavailable for everyone else.

  Two dimensions:
    Per-IP:     30 req/min  — stops scripted abuse from one machine
    Per-thread: 10 req/min  — limits a single chat session's throughput

Your tasks:
  TODO 2a: Create a Limiter instance using get_remote_address as key_func.
  TODO 2b: Implement thread_key() — extract thread_id from request.state
           (set by the route handler before the key_func is called).
  TODO 2c: Implement rate_limit_handler() — return a structured JSON 429
           response with a Retry-After header instead of slowapi's plain text.

Usage in main.py (done for you in the starter):
  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

  @app.post("/chat")
  @limiter.limit("30/minute")
  @limiter.limit("10/minute", key_func=thread_key)
  def chat(request: Request, req: ChatRequest): ...

Hint: see slowapi docs or solution/middleware/rate_limiter.py.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# TODO 2a: create the limiter
# limiter = Limiter(key_func=get_remote_address)
limiter = None  # replace with Limiter(...)


def thread_key(request: Request) -> str:
    """TODO 2b: return a key that rate-limits per thread_id.

    The thread_id is stored in request.state.thread_id by the route handler.
    Fall back to IP address if not set.

    Hint:
      thread_id = getattr(request.state, "thread_id", None)
      return f"thread:{thread_id}" if thread_id else get_remote_address(request)
    """
    # TODO: implement
    return get_remote_address(request)  # placeholder — replace with thread logic


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """TODO 2c: return a structured JSON 429 with Retry-After header.

    Hint:
      retry_after = getattr(exc, "retry_after", 60)
      return JSONResponse(
          status_code=429,
          content={"error": "rate_limit_exceeded", "detail": "...", "retry_after": retry_after},
          headers={"Retry-After": str(retry_after)},
      )
    """
    # TODO: implement
    return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded"})
