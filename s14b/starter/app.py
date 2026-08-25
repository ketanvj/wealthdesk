"""
app.py
------
Streamlit chat UI for WealthDesk — Bharat National Bank's AI wealth assistant.

Session 14: Security and Guardrails.

Architecture:
  - Guard node (NEW) runs before every query — blocks injection and PII
  - Supervisor classifies clean queries
  - Documents / Rates specialists handle them
  - Compliance Agent checks every draft response
  - Human-in-the-Loop: operator must approve compliance-revised responses

Run:
    streamlit run app.py   (from inside s14/solution/)
"""
import sys
from pathlib import Path
from uuid import uuid4

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

from wealthdesk.agent import build_graph  # noqa: E402


# ---------------------------------------------------------------------------
# Helper functions (pure, testable -- no Streamlit calls)
# ---------------------------------------------------------------------------

def build_input_state(message: str) -> dict:
    """Return the initial state dict for graph.invoke()."""
    return {
        "customer_message":  message,
        "response":          "",
        "specialist":        "",
        "retrieved_docs":    [],
        "compliance_status": "",
        "blocked_reason":    "",
    }


def get_thread_config(thread_id: str) -> dict:
    """Return the LangGraph thread config dict."""
    return {"configurable": {"thread_id": thread_id}}


def compliance_badge(status: str) -> str:
    """Return a short human-readable badge for the compliance status."""
    if status == "PASS":
        return "✅ Compliant"
    if status == "REVISED":
        return "⚠️ Revised"
    if status.startswith("FAIL"):
        return "❌ Violation"
    return ""


def guard_badge(blocked_reason: str) -> str:
    """Return a guard status badge."""
    if blocked_reason == "pii":
        return "🔒 Blocked (PII)"
    if blocked_reason:
        return "🛡️ Blocked (injection)"
    return ""


def needs_human_review(result: dict) -> bool:
    """Return True when the Compliance Agent revised the response."""
    return result.get("compliance_status", "") == "REVISED"


def format_route_label(result: dict) -> str:
    """Return a one-line route summary for display as a caption."""
    blocked_r = result.get("blocked_reason", "")
    if blocked_r:
        return f"Guard: {guard_badge(blocked_r)}"

    sp    = result.get("specialist", "—")
    cs    = result.get("compliance_status", "")
    badge = compliance_badge(cs)
    label = f"Route: {sp}"
    if badge:
        label += f" | {badge}"
    return label


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def _init_session() -> None:
    if "graph" not in st.session_state:
        from langgraph.checkpoint.memory import MemorySaver
        st.session_state.graph     = build_graph(checkpointer=MemorySaver())
        st.session_state.thread_id = str(uuid4())
        st.session_state.messages  = []
        st.session_state.routes    = []


def _sidebar() -> None:
    with st.sidebar:
        st.header("🏦 WealthDesk")
        st.caption("BNB Customer Assistant")
        st.divider()

        if st.button("🔄 New Conversation", use_container_width=True):
            for key in ["graph", "thread_id", "messages", "routes", "pending_hitl"]:
                st.session_state.pop(key, None)
            st.rerun()

        if "thread_id" in st.session_state:
            st.caption(f"Session: {st.session_state.thread_id[:8]}…")

        st.divider()
        st.subheader("Agents")
        st.markdown(
            "- **Guard** — blocks injections & PII *(new in S14)*\n"
            "- **Supervisor** — classifies clean queries\n"
            "- **Documents Agent** — policy & document queries\n"
            "- **Rates Agent** — rates, branch info\n"
            "- **Compliance Agent** — SEBI rules check\n"
            "- **Human-in-the-Loop** — reviews revisions"
        )


def _render_history() -> None:
    messages = st.session_state.get("messages", [])
    routes   = st.session_state.get("routes",   [])
    assistant_idx = 0
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
        if msg["role"] == "assistant":
            if assistant_idx < len(routes):
                st.caption(routes[assistant_idx])
            assistant_idx += 1


def _handle_hitl() -> bool:
    """Render compliance-revision approval form if active. Returns True while blocking."""
    if "pending_hitl" not in st.session_state:
        return False

    pending = st.session_state.pending_hitl
    st.warning(
        "⚠️ **Compliance Review Required** — The Compliance Agent revised this response. "
        "Please review and approve before sending to the customer."
    )

    with st.form("hitl_approval"):
        edited = st.text_area(
            "Review and edit the response if needed:",
            value=pending["response"],
            height=220,
        )
        col1, col2 = st.columns(2)
        approved  = col1.form_submit_button("✅ Approve & Send", use_container_width=True)
        discarded = col2.form_submit_button("❌ Discard",         use_container_width=True)

    if approved:
        st.session_state.messages.append({"role": "assistant", "content": edited})
        st.session_state.routes.append(pending["route_label"])
        del st.session_state.pending_hitl
        st.rerun()
    elif discarded:
        del st.session_state.pending_hitl
        st.rerun()

    return True


def main() -> None:
    st.set_page_config(
        page_title="WealthDesk | Bharat National Bank",
        page_icon="🏦",
        layout="wide",
    )
    st.title("🏦 WealthDesk | Bharat National Bank")
    st.caption("AI-powered wealth assistant — Session 14: Security and Guardrails")

    _init_session()
    _sidebar()
    _render_history()

    hitl_active = _handle_hitl()

    if not hitl_active:
        prompt = st.chat_input("Ask about BNB deposits, home loans, or investment options…")
        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.spinner("WealthDesk is thinking…"):
                result = st.session_state.graph.invoke(
                    build_input_state(prompt),
                    config=get_thread_config(st.session_state.thread_id),
                )

            route_label = format_route_label(result)

            if needs_human_review(result):
                st.session_state.pending_hitl = {
                    "response":    result["response"],
                    "route_label": route_label,
                }
                st.rerun()
            else:
                response = result["response"]
                with st.chat_message("assistant"):
                    st.markdown(response)
                st.caption(route_label)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.session_state.routes.append(route_label)


if __name__ == "__main__":
    main()
