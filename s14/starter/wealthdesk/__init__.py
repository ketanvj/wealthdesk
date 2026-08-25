"""
WealthDesk package -- Session 14: Security & Guardrails (LLM01 / OWASP ASI)
=============================================================================

This file runs automatically when Python imports the wealthdesk package.
"""
import os

os.environ.setdefault("HF_HUB_VERBOSITY", "error")

from dotenv import load_dotenv
load_dotenv()

if os.getenv("LANGSMITH_API_KEY") and os.getenv("LANGSMITH_TRACING", "").lower() == "true":
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ.setdefault("LANGCHAIN_API_KEY", os.getenv("LANGSMITH_API_KEY", ""))
    os.environ.setdefault("LANGCHAIN_PROJECT",  os.getenv("LANGSMITH_PROJECT", "batch1-wealthdesk"))

from .agent import build_graph, graph, run
from .state import WealthDeskState

__all__ = ["build_graph", "graph", "run", "WealthDeskState"]
