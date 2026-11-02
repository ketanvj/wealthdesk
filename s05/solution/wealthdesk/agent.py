import sqlite3
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from .config import CHECKPOINT_DB
from .nodes import classify, decline, escalate, respond, retrieve_docs, route_query
from .state import WealthDeskState


def build_graph(checkpointer=None):
    builder = StateGraph(WealthDeskState)

    builder.add_node("classify",      classify)
    builder.add_node("retrieve_docs", retrieve_docs)
    builder.add_node("respond",       respond)
    builder.add_node("escalate",      escalate)
    builder.add_node("decline",       decline)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", route_query, {
        "retrieve_docs": "retrieve_docs",
        "escalate":      "escalate",
        "decline":       "decline",
    })

    builder.add_edge("retrieve_docs", "respond")
    builder.add_edge("respond",       END)
    builder.add_edge("escalate",      END)
    builder.add_edge("decline",       END)

    return builder.compile(checkpointer=checkpointer)


graph = build_graph()


def run() -> None:
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    _graph    = build_graph(checkpointer=SqliteSaver(conn))
    thread_id = str(uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    print("=" * 55)
    print("  WealthDesk | Bharat National Bank")
    print("  Type 'quit' to exit")
    print("=" * 55)
    print(f"  Session: {thread_id[:8]}...")
    print("=" * 55)

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

        result = _graph.invoke(
            {"customer_message": user_input, "response": ""},
            config=config,
        )
        route = result.get("query_type", "?")
        docs  = result.get("retrieved_docs", [])
        print(f"\n[Routed: {route}]", end="")
        if docs:
            sources = {d.split("]\n")[0].lstrip("[") for d in docs if "]\n" in d}
            print(f"  [Retrieved {len(docs)} chunk(s) from: {', '.join(sorted(sources))}]")
        else:
            print()
        print(f"\nWealthDesk: {result['response']}")


if __name__ == "__main__":
    run()
