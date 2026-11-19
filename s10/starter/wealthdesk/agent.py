import os
import sqlite3
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from .config import CHECKPOINT_DB, MCP_SERVER_PATH
from .nodes import (
    call_documents_agent,
    call_rates_agent,
    classify,
    decline,
    escalate,
    route_supervisor,
)
from .state import WealthDeskState


# ---------------------------------------------------------------------------
# TODO 5 of 5 — implement build_graph()
# ---------------------------------------------------------------------------
# Wire the supervisor graph. Five nodes; one conditional edge from classify.
#
# Node names:
#   "classify"
#   "call_documents_agent [subgraph]"   ← the [subgraph] label appears in LangSmith
#   "call_rates_agent [subgraph]"
#   "escalate"
#   "decline"
#
# Conditional edges (explicit path map required for LangGraph Studio):
#   builder.add_conditional_edges("classify", route_supervisor, {
#       "call_documents_agent": "call_documents_agent [subgraph]",
#       "call_rates_agent":     "call_rates_agent [subgraph]",
#       "escalate":             "escalate",
#       "decline":              "decline",
#   })
#
# All specialist/terminal nodes → END:
#   builder.add_edge("call_documents_agent [subgraph]", END)
#   builder.add_edge("call_rates_agent [subgraph]",     END)
#   builder.add_edge("escalate",                        END)
#   builder.add_edge("decline",                         END)
#
# IMPORTANT: return builder.compile(checkpointer=checkpointer)
#   Not compile() — the supervisor IS stateful (it holds conversation history).
#   Specialist agents have no checkpointer; the supervisor has one.
# ---------------------------------------------------------------------------

def build_graph(checkpointer=None):
    # TODO 5: build StateGraph, add 5 nodes, wire conditional edges, compile
    raise NotImplementedError("TODO 5: implement build_graph()")


# Module-level graph for LangGraph Studio (compile with no checkpointer).
# Raises until TODO 5 is complete.
graph = build_graph()


def run() -> None:
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    g         = build_graph(checkpointer=SqliteSaver(conn))
    thread_id = str(uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    if not MCP_SERVER_PATH.exists():
        print(f"[WealthDesk] WARNING: MCP server not found at {MCP_SERVER_PATH}")
        print("  Complete Session 7 first.")

    tracing_on = os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
    project    = os.environ.get("LANGCHAIN_PROJECT", "batch1-wealthdesk")

    print("=" * 60)
    print("  WealthDesk | Bharat National Bank")
    print("  Architecture: Supervisor + Documents Agent + Rates Agent")
    print(f"  Tracing: {'LangSmith (' + project + ')' if tracing_on else 'off'}")
    print("  Type 'quit' to exit")
    print("=" * 60)
    print(f"  Session: {thread_id[:8]}...")
    print("=" * 60)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nWealthDesk: Session ended. Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "bye"}:
            print("\nWealthDesk: Thank you for choosing Bharat National Bank. Goodbye!")
            break

        result = g.invoke(
            {"customer_message": user_input, "response": "",
             "specialist": "", "retrieved_docs": []},
            config=config,
        )
        specialist = result.get("specialist", "?")
        docs       = result.get("retrieved_docs", [])

        print(f"\n[Route: {result.get('query_type','?')} → {specialist}]", end="")
        if docs:
            sources = {d.split("]\n")[0].lstrip("[") for d in docs if "]\n" in d}
            print(f"  [RAG: {len(docs)} chunk(s) from {', '.join(sorted(sources))}]", end="")
        print()
        print(f"\nWealthDesk: {result['response']}")


if __name__ == "__main__":
    run()
