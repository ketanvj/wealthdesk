import os
import sqlite3
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from .config import CHECKPOINT_DB, MCP_SERVER_PATH
from .nodes import (
    blocked,
    call_compliance_agent,
    call_documents_agent,
    call_rates_agent,
    classify,
    decline,
    escalate,
    guard,
    route_guard,
    route_supervisor,
)
from .state import WealthDeskState


def build_graph(checkpointer=None):
    builder = StateGraph(WealthDeskState)

    # S14 TODO: add the guard and blocked nodes here, then set "guard" as
    # the entry point and wire add_conditional_edges("guard", route_guard, {...}).
    # The rest of the graph is already provided below.

    builder.add_node("guard",                 guard)
    builder.add_node("blocked",               blocked)
    builder.add_node("classify",              classify)
    builder.add_node("call_documents_agent",  call_documents_agent)
    builder.add_node("call_rates_agent",      call_rates_agent)
    builder.add_node("call_compliance_agent", call_compliance_agent)
    builder.add_node("escalate",              escalate)
    builder.add_node("decline",               decline)

    builder.set_entry_point("guard")

    # TODO: add_conditional_edges for "guard" → {"classify": ..., "blocked": ...}
    builder.add_conditional_edges("guard", route_guard, {
        "classify": "classify",
        "blocked":  "blocked",
    })
    builder.add_edge("blocked", END)

    builder.add_conditional_edges("classify", route_supervisor, {
        "call_documents_agent": "call_documents_agent",
        "call_rates_agent":     "call_rates_agent",
        "escalate":             "escalate",
        "decline":              "decline",
    })

    builder.add_edge("call_documents_agent",  "call_compliance_agent")
    builder.add_edge("call_rates_agent",      "call_compliance_agent")
    builder.add_edge("call_compliance_agent", END)

    builder.add_edge("escalate", END)
    builder.add_edge("decline",  END)

    return builder.compile(checkpointer=checkpointer)


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
    print("  Architecture: Guard → Supervisor → [Documents|Rates] → Compliance")
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
            {
                "customer_message":  user_input,
                "response":          "",
                "specialist":        "",
                "retrieved_docs":    [],
                "compliance_status": "",
                "blocked_reason":    "",
            },
            config=config,
        )

        blocked_r = result.get("blocked_reason", "")
        if blocked_r:
            print(f"\n[Guard: BLOCKED ({blocked_r})]")
        else:
            specialist = result.get("specialist", "?")
            compliance = result.get("compliance_status", "")
            docs       = result.get("retrieved_docs", [])
            print(f"\n[Route: {result.get('query_type','?')} → {specialist}]", end="")
            if docs:
                sources = {d.split("]\n")[0].lstrip("[") for d in docs if "]\n" in d}
                print(f"  [RAG: {len(docs)} chunk(s) from {', '.join(sorted(sources))}]", end="")
            if compliance:
                print(f"  [Compliance: {compliance}]", end="")
            print()
        print(f"\nWealthDesk: {result['response']}")


if __name__ == "__main__":
    run()
