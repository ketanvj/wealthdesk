"""
WealthDesk -- Session 16: FastAPI Backend (US-16)
==================================================

What you build this session
  Wrap the WealthDesk LangGraph agent in a FastAPI HTTP API so the web
  frontend (frontend/index.html) can call it over REST.

Architecture
  ┌─────────────────┐    REST/JSON     ┌─────────────────┐    SSE/MCP    ┌──────────────┐
  │  Browser / app  │ ──────────────►  │  FastAPI :8000  │ ─────────────►│  MCP :8001   │
  │  (index.html)   │ ◄──────────────  │  (this file)    │ ◄─────────────│  mcp_server  │
  └─────────────────┘                  └─────────────────┘               └──────────────┘

Start order
  1. python mcp_server.py          # starts MCP SSE server on :8001
  2. uvicorn main:app --reload     # starts FastAPI on :8000
  3. open http://localhost:8000    # frontend served automatically

Endpoints to implement
  POST /chat          — send a message, get a response
  GET  /health        — liveness check
  GET  /              — serves frontend/index.html (done for you at the bottom)

Your tasks: TODO 4, 5, 6, 7 below.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from wealthdesk.agent import build_graph

# ---------------------------------------------------------------------------
# TODO 4: Build the graph once at startup using FastAPI's lifespan
# ---------------------------------------------------------------------------
# Use @asynccontextmanager to define a lifespan function that:
#   - Creates the graph with MemorySaver checkpointer before yield
#   - Stores it in _graph (global)
#   - Prints "[WealthDesk API] Graph ready."
#
# Hint: look at the lifespan pattern in the FastAPI docs or the solution.

_graph = None


# TODO 4: define the lifespan function here
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     global _graph
#     ...
#     yield
#     ...


# TODO 4: pass lifespan= to FastAPI constructor
app = FastAPI(title="WealthDesk API", version="1.0.0")  # add lifespan=lifespan

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# TODO 5: Define request and response Pydantic models
# ---------------------------------------------------------------------------
# ChatRequest fields:  message (str), thread_id (str, default "default")
# ChatResponse fields: response, specialist, blocked_reason, compliance_status
#                      (all str)


class ChatRequest(BaseModel):
    pass  # TODO: add fields


class ChatResponse(BaseModel):
    pass  # TODO: add fields


# ---------------------------------------------------------------------------
# TODO 6: Implement the /chat endpoint
# ---------------------------------------------------------------------------
# - Validate that message is not empty (raise HTTPException 400 if it is)
# - Call _graph.invoke() with a blank initial state and the thread_id
# - Return a ChatResponse with response, specialist, blocked_reason,
#   compliance_status pulled from the result dict


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # TODO: implement
    raise NotImplementedError("Implement the /chat endpoint")


# ---------------------------------------------------------------------------
# TODO 7: Implement the /health endpoint
# ---------------------------------------------------------------------------
# Return {"status": "ok", "graph": "ready"} when _graph is not None,
# {"status": "ok", "graph": "not initialized"} otherwise.


@app.get("/health")
def health():
    # TODO: implement
    raise NotImplementedError("Implement the /health endpoint")


# ---------------------------------------------------------------------------
# Serve the web frontend (done for you — don't change)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
