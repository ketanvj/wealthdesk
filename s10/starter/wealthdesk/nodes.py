"""
wealthdesk/nodes.py  (starter)
-------------------------------
Session 10: Supervisor + Specialist Agents.

Split the single respond() node from S09 into two specialist subgraphs:
  - Documents Agent: retrieve_docs → respond  (RAG, plain llm, no tools)
  - Rates Agent:     respond                  (MCP tool calls, llm_with_tools)

4 TODOs in this file + 1 TODO in agent.py = 5 total for this session:

  TODO 1 — create_documents_agent()   build the Documents subgraph
  TODO 2 — create_rates_agent()       build the Rates subgraph
  TODO 3 — call_documents_agent()     supervisor node: invoke Documents Agent
  TODO 4 — call_rates_agent()         supervisor node: invoke Rates Agent

  (TODO 5 is in agent.py — wire the supervisor graph)

IMPORTANT: TODOs 1 and 2 must be done FIRST.
_documents_agent = create_documents_agent() runs at module import time.
If create_documents_agent() raises NotImplementedError, the entire module
fails to import — which blocks TODOs 3 and 4.

Quick self-test after each milestone:
  # After TODO 1 + 2:
  python -c "
  import sys; sys.path.insert(0, '.')
  from wealthdesk.nodes import create_documents_agent, create_rates_agent
  print('docs:', create_documents_agent())
  print('rates:', create_rates_agent())"

  # After all 5 TODOs:
  python -m wealthdesk.agent   # from s10/starter/
"""
from langchain_chroma import Chroma
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_huggingface import HuggingFaceEmbeddings
from langgraph.graph import END, StateGraph

from .config import (
    CLASSIFY_SYSTEM,
    DECLINE_RESPONSE,
    DOCS_SYSTEM_PROMPT,
    EMBED_MODEL,
    ESCALATE_RESPONSE,
    RETRIEVAL_K,
    SYSTEM_PROMPT,
    VECTORSTORE_DIR,
)
from .state import WealthDeskState
from .tools import _run_tool, classifier_llm, llm, llm_with_tools

vectorstore = None


def _init_vectorstore() -> None:
    global vectorstore
    if vectorstore is not None:
        return
    try:
        embeddings  = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
        vectorstore = Chroma(
            persist_directory=str(VECTORSTORE_DIR),
            embedding_function=embeddings,
        )
    except Exception as e:
        print(f"[WealthDesk] Could not load vectorstore: {e}")
        print("  Run 'python data/ingest.py' to create it.")


# ---------------------------------------------------------------------------
# Specialist agent node functions (PROVIDED — read these, do not modify)
# ---------------------------------------------------------------------------

def _doc_retrieve(state: WealthDeskState) -> dict:
    """Documents Agent node 1 of 2: retrieve relevant policy chunks from ChromaDB."""
    _init_vectorstore()
    if vectorstore is None:
        return {"retrieved_docs": []}
    try:
        docs = vectorstore.similarity_search(state["customer_message"], k=RETRIEVAL_K)
        return {
            "retrieved_docs": [
                f"[{doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
                for doc in docs
            ]
        }
    except Exception as e:
        print(f"[WealthDesk] Documents Agent retrieval error: {e}")
        return {"retrieved_docs": []}


def _doc_respond(state: WealthDeskState) -> dict:
    """Documents Agent node 2 of 2: generate answer using RAG context.

    Uses plain `llm` (no tools bound) — DOCS_SYSTEM_PROMPT tells the model it
    has no live-rates access. Using llm_with_tools here would cause Groq's parser
    to fail when the model tries to emit a tool call that isn't registered.
    """
    history   = state.get("history", [])
    retrieved = state.get("retrieved_docs", [])

    context_block  = "\n\n---\n\n".join(retrieved) if retrieved else ""
    system_content = (
        DOCS_SYSTEM_PROMPT
        + (
            "\n\nThe following sections from BNB's policy documents are relevant "
            "to the customer's question. Use this information in your answer:\n\n"
            + context_block
            if context_block else ""
        )
    )

    messages = [SystemMessage(content=system_content)]
    for turn in history:
        messages.append(
            HumanMessage(content=turn["content"]) if turn["role"] == "user"
            else AIMessage(content=turn["content"])
        )
    messages.append(HumanMessage(content=state["customer_message"]))

    try:
        result        = llm.invoke(messages)      # plain llm — no tool calls
        response_text = result.content
    except Exception as e:
        print(f"[WealthDesk] Documents Agent LLM error: {e}")
        response_text = "I am temporarily unavailable. Please try again in a moment."

    return {
        "response": response_text,
        "history":  history + [
            {"role": "user",      "content": state["customer_message"]},
            {"role": "assistant", "content": response_text},
        ],
    }


def _rates_respond(state: WealthDeskState) -> dict:
    """Rates Agent node: answer using MCP tool calls for live rate/branch data.

    Uses llm_with_tools so the model can request query_rates / query_branch.
    Two LLM calls when tools are used:
      1. llm_with_tools.invoke() → may return tool_calls
      2. llm.invoke(messages + tool results) → final answer
    """
    history  = state.get("history", [])
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    for turn in history:
        messages.append(
            HumanMessage(content=turn["content"]) if turn["role"] == "user"
            else AIMessage(content=turn["content"])
        )
    messages.append(HumanMessage(content=state["customer_message"]))

    try:
        result = llm_with_tools.invoke(messages)

        if result.tool_calls:
            messages.append(result)
            for tc in result.tool_calls:
                tool_output = _run_tool(tc["name"], tc["args"])
                print(
                    f"[WealthDesk] Rates Agent MCP: {tc['name']}({tc['args']}) "
                    f"-> {str(tool_output)[:80]}"
                )
                messages.append(ToolMessage(content=str(tool_output), tool_call_id=tc["id"]))
            result = llm.invoke(messages)

        response_text = result.content

    except Exception as e:
        print(f"[WealthDesk] Rates Agent LLM error: {e}")
        response_text = "I am temporarily unavailable. Please try again in a moment."

    return {
        "response": response_text,
        "history":  history + [
            {"role": "user",      "content": state["customer_message"]},
            {"role": "assistant", "content": response_text},
        ],
    }


# ---------------------------------------------------------------------------
# TODO 1 of 4 — implement create_documents_agent()
# ---------------------------------------------------------------------------
# Build the Documents Agent as a compiled subgraph.
# Two nodes: retrieve_docs → respond → END.
# No checkpointer — specialists are stateless (history is passed by value).
#
# Shape:
#   builder = StateGraph(WealthDeskState)
#   builder.add_node("retrieve_docs", _doc_retrieve)
#   builder.add_node("respond",       _doc_respond)
#   builder.set_entry_point("retrieve_docs")
#   builder.add_edge("retrieve_docs", "respond")
#   builder.add_edge("respond",       END)
#   return builder.compile()   ← compile() converts blueprint → executable graph
#
# WHY compile() with no checkpointer?
#   Specialists don't store state between calls. The supervisor passes the full
#   history on each invocation. If specialists had their own checkpointers they'd
#   each write to the same SQLite file — a coordination nightmare.
#
# WHY factory function (not module-level builder)?
#   The compiled graph is built once at module load (_documents_agent = ...).
#   Tests can call create_documents_agent() to get independent instances.
# ---------------------------------------------------------------------------

def create_documents_agent():
    """Return a compiled Documents Agent subgraph (retrieve_docs → respond → END)."""
    # TODO 1: build StateGraph, add retrieve_docs + respond nodes, compile()
    raise NotImplementedError("TODO 1: implement create_documents_agent()")


# ---------------------------------------------------------------------------
# TODO 2 of 4 — implement create_rates_agent()
# ---------------------------------------------------------------------------
# Build the Rates Agent as a compiled subgraph.
# One node: respond → END.
#
# Shape:
#   builder = StateGraph(WealthDeskState)
#   builder.add_node("respond", _rates_respond)
#   builder.set_entry_point("respond")
#   builder.add_edge("respond", END)
#   return builder.compile()
#
# WHY only one node?
#   Rates Agent does not use RAG. It calls the MCP server directly from
#   _rates_respond via llm_with_tools. No retrieve step is needed.
# ---------------------------------------------------------------------------

def create_rates_agent():
    """Return a compiled Rates Agent subgraph (respond → END)."""
    # TODO 2: build StateGraph, add respond node, compile()
    raise NotImplementedError("TODO 2: implement create_rates_agent()")


# Module-level instances — built once at import time, reused for every query.
# If TODO 1 or 2 raises, this line raises too — fix TODOs 1 and 2 first.
_documents_agent = create_documents_agent()
_rates_agent     = create_rates_agent()


# ---------------------------------------------------------------------------
# Supervisor nodes (provided — classify and route_supervisor are complete)
# ---------------------------------------------------------------------------

def classify(state: WealthDeskState) -> dict:
    """4-category classifier: RATES | POLICY | COMPLEX | OUT_OF_SCOPE.

    Passes the last exchange from history so follow-up questions ("and what
    about personal loans?") are classified with their context, not in isolation.
    temperature=0 on classifier_llm → deterministic, reproducible routing.
    """
    messages = [SystemMessage(content=CLASSIFY_SYSTEM)]
    for turn in state.get("history", [])[-2:]:
        messages.append(
            HumanMessage(content=turn["content"]) if turn["role"] == "user"
            else AIMessage(content=turn["content"])
        )
    messages.append(HumanMessage(content=state["customer_message"]))
    try:
        result     = classifier_llm.invoke(messages)
        query_type = result.content.strip().upper()
        if query_type not in {"RATES", "POLICY", "COMPLEX", "OUT_OF_SCOPE"}:
            query_type = "RATES"   # safe default: a missed rate question < a silenced policy question
    except Exception as e:
        print(f"[WealthDesk] Supervisor classification error: {e}")
        query_type = "RATES"
    return {"query_type": query_type}


def route_supervisor(state: WealthDeskState) -> str:
    qt = state.get("query_type", "RATES")
    if qt == "POLICY":
        return "call_documents_agent"
    if qt == "COMPLEX":
        return "escalate"
    if qt == "OUT_OF_SCOPE":
        return "decline"
    return "call_rates_agent"


# ---------------------------------------------------------------------------
# TODO 3 of 4 — implement call_documents_agent()
# ---------------------------------------------------------------------------
# Supervisor node: invoke the Documents Agent subgraph and return its output.
#
# Key rules:
#   1. Pass a FRESH dict — do NOT pass state directly.
#      Always reset response="" and retrieved_docs=[] to prevent cross-turn bleed.
#   2. Copy history by VALUE (a new list), not by reference — specialists must
#      not accidentally mutate the supervisor's history.
#   3. The supervisor stamps specialist="documents_agent" — the subgraph itself
#      does NOT set this field, keeping subgraphs reusable.
#
# Shape:
#   print("[WealthDesk] Supervisor → Documents Agent")
#   result = _documents_agent.invoke({
#       "customer_message": state["customer_message"],
#       "history":          state.get("history", []),
#       "response":         "",
#       "query_type":       state.get("query_type", "POLICY"),
#       "retrieved_docs":   [],
#       "specialist":       "",
#   })
#   return {
#       "response":       result["response"],
#       "retrieved_docs": result.get("retrieved_docs", []),
#       "history":        result.get("history", state.get("history", [])),
#       "specialist":     "documents_agent",
#   }
# ---------------------------------------------------------------------------

def call_documents_agent(state: WealthDeskState) -> dict:
    """Supervisor node: delegate POLICY query to Documents Agent subgraph."""
    # TODO 3: invoke _documents_agent with a fresh dict, return response + specialist
    raise NotImplementedError("TODO 3: implement call_documents_agent()")


# ---------------------------------------------------------------------------
# TODO 4 of 4 — implement call_rates_agent()
# ---------------------------------------------------------------------------
# Same pattern as TODO 3, but for the Rates Agent.
# Note: Rates Agent does not return retrieved_docs (it uses MCP, not RAG),
# so do NOT include "retrieved_docs" in the return dict.
#
# Shape:
#   print("[WealthDesk] Supervisor → Rates Agent")
#   result = _rates_agent.invoke({
#       "customer_message": state["customer_message"],
#       "history":          state.get("history", []),
#       "response":         "",
#       "query_type":       state.get("query_type", "RATES"),
#       "retrieved_docs":   [],
#       "specialist":       "",
#   })
#   return {
#       "response":   result["response"],
#       "history":    result.get("history", state.get("history", [])),
#       "specialist": "rates_agent",
#   }
# ---------------------------------------------------------------------------

def call_rates_agent(state: WealthDeskState) -> dict:
    """Supervisor node: delegate RATES query to Rates Agent subgraph."""
    # TODO 4: invoke _rates_agent with a fresh dict, return response + specialist
    raise NotImplementedError("TODO 4: implement call_rates_agent()")


def escalate(state: WealthDeskState) -> dict:
    new_history = state.get("history", []) + [
        {"role": "user",      "content": state["customer_message"]},
        {"role": "assistant", "content": ESCALATE_RESPONSE},
    ]
    return {"response": ESCALATE_RESPONSE, "history": new_history, "specialist": "escalated"}


def decline(state: WealthDeskState) -> dict:
    new_history = state.get("history", []) + [
        {"role": "user",      "content": state["customer_message"]},
        {"role": "assistant", "content": DECLINE_RESPONSE},
    ]
    return {"response": DECLINE_RESPONSE, "history": new_history, "specialist": "declined"}
