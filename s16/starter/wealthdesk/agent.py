"""
WealthDesk S16 agent — identical graph to S15, no CLI entry point.
The FastAPI app in main.py owns the process lifecycle.
"""
from langgraph.graph import END, StateGraph

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

    builder.add_node("guard",                 guard)
    builder.add_node("blocked",               blocked)
    builder.add_node("classify",              classify)
    builder.add_node("call_documents_agent",  call_documents_agent)
    builder.add_node("call_rates_agent",      call_rates_agent)
    builder.add_node("call_compliance_agent", call_compliance_agent)
    builder.add_node("escalate",              escalate)
    builder.add_node("decline",               decline)

    builder.set_entry_point("guard")
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


# Module-level graph for LangGraph Studio (MCP server must be running first)
graph = build_graph()
