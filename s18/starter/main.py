"""
WealthDesk S18 — Production Security Hardening
===============================================

Your tasks in this file:
  TODO 5: Wire the rate limiter to the /chat endpoint
  TODO 6: Wire the spend cap circuit breaker before graph.invoke()
  TODO 7: Expose /budget endpoint for monitoring

The middleware modules (TODO 2 and 3) are in middleware/rate_limiter.py
and middleware/spend_cap.py. Complete those first, then wire them here.

Start order (same as S16):
  1. python mcp_server.py
  2. uvicorn main:app --reload
  3. open http://localhost:8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded

from middleware.rate_limiter import limiter, rate_limit_handler, thread_key
from middleware.spend_cap import SpendCapTracker, estimate_tokens
from wealthdesk.agent import build_graph
from wealthdesk.config import settings

_graph = None
_spend = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph, _spend
    _graph = build_graph(checkpointer=MemorySaver())
    _spend = SpendCapTracker(
        hourly_budget=settings.hourly_token_budget,
        daily_budget=settings.daily_token_budget,
    )
    print("[WealthDesk S18] Graph and spend cap ready.")
    yield


app = FastAPI(title="WealthDesk S18 API", version="1.0.0", lifespan=lifespan)

# TODO 5a: register the rate limiter on app.state and add the exception handler
# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message:   str
    thread_id: str = "default"


class ChatResponse(BaseModel):
    response:          str
    specialist:        str
    blocked_reason:    str
    compliance_status: str


# TODO 5b: add @limiter.limit() decorators to the /chat endpoint
# @limiter.limit(settings.rate_limit_per_ip)
# @limiter.limit(settings.rate_limit_per_thread, key_func=thread_key)
@app.post("/chat", response_model=ChatResponse)
def chat(request: Request, req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    # Expose thread_id to thread_key() key function
    request.state.thread_id = req.thread_id

    # TODO 6: check spend cap before calling the graph
    # allowed, reason = _spend.check()
    # if not allowed:
    #     raise HTTPException(status_code=503, detail=f"Service unavailable: {reason}",
    #                         headers={"Retry-After": "3600"})

    result = _graph.invoke(
        {
            "customer_message":  req.message,
            "response":          "",
            "history":           [],
            "query_type":        "",
            "retrieved_docs":    [],
            "specialist":        "",
            "compliance_status": "",
            "blocked_reason":    "",
        },
        config={"configurable": {"thread_id": req.thread_id}},
    )

    # TODO 6: record token usage after the graph returns
    # tokens = estimate_tokens(req.message) + estimate_tokens(result.get("response", ""))
    # _spend.record(tokens)

    return ChatResponse(
        response=result.get("response", ""),
        specialist=result.get("specialist", ""),
        blocked_reason=result.get("blocked_reason", ""),
        compliance_status=result.get("compliance_status", ""),
    )


@app.get("/health")
def health():
    return {"status": "ok", "graph": "ready" if _graph else "not initialized"}


# TODO 7: Add a /budget endpoint
# @app.get("/budget")
# def budget():
#     status = _spend.status()
#     # add warnings when pct > 80
#     return status


app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
