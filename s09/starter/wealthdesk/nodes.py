"""
wealthdesk/nodes.py  (starter)
-------------------------------
Session 9: add SEBI compliance checking.

New this session:  check_compliance node — the only node you need to implement.
Everything else (classify, retrieve_docs, respond, escalate, decline,
route_query) is carried forward from Session 8 unchanged.

Three TODOs — all inside check_compliance and its helpers:

  TODO 1 — _normalize_for_check()       Unicode normalisation + dash variants
  TODO 2 — _check_compliance()          banned-phrase check + rate hallucination check
  TODO 3 — check_compliance node        read draft, call _check_compliance, update state

Quick self-test (run from s09/starter/):
  python -c "
  import sys; sys.path.insert(0, '.')
  from wealthdesk.nodes import _normalize_for_check, _check_compliance
  # 1. Banned phrase test
  ok, reason = _check_compliance('Our FD offers guaranteed returns.')
  assert not ok and 'guaranteed returns' in reason, f'Expected banned-phrase fail, got: {ok}, {reason}'
  # 2. Hallucinated rate test
  ok, reason = _check_compliance('Home loan rate is 9.99% p.a.')
  assert not ok and '9.99' in reason, f'Expected hallucination fail, got: {ok}, {reason}'
  # 3. Valid rate test
  ok, reason = _check_compliance('Home loan rate is 8.5% p.a.')
  assert ok, f'Expected PASS, got: {ok}, {reason}'
  print('All self-tests PASS')
  "
  Expected initially: NotImplementedError
  After all three TODOs: 'All self-tests PASS'
"""
import re
import sqlite3
import unicodedata

from langchain_chroma import Chroma
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_huggingface import HuggingFaceEmbeddings
from langsmith import traceable

from .config import (
    CLASSIFY_SYSTEM,
    DB_PATH,
    DECLINE_RESPONSE,
    EMBED_MODEL,
    ESCALATE_RESPONSE,
    RETRIEVAL_K,
    SAFE_COMPLIANCE_RESPONSE,
    SEBI_BANNED_PHRASES,
    SYSTEM_PROMPT,
    VECTORSTORE_DIR,
)
from .state import WealthDeskState
from .tools import _run_tool, classifier_llm, llm, llm_with_tools

vectorstore = None

# Compile the banned-phrase list into a single regex automaton at import time.
# O(M) per check regardless of how many phrases are listed (vs O(N×M) loops).
# For 10k+ phrases, replace with Aho-Corasick (pyahocorasick / flashtext).
_BANNED_PATTERN: re.Pattern = re.compile(
    "|".join(re.escape(p) for p in SEBI_BANNED_PHRASES),
    re.IGNORECASE,
)


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


def _load_valid_rates() -> set:
    # Reads SQLite directly (not via MCP) — compliance needs floats, not formatted strings.
    try:
        conn      = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        loan_rows = conn.execute("SELECT interest_rate FROM loan_products").fetchall()
        fd_rows   = conn.execute("SELECT interest_rate, senior_rate FROM fd_products").fetchall()
        conn.close()
        loan_rates = {row[0] for row in loan_rows}
        fd_base    = {row[0] for row in fd_rows}
        fd_senior  = {row[0] + row[1] for row in fd_rows}
        return loan_rates | fd_base | fd_senior
    except Exception:
        return set()


def _extract_rates(text: str) -> list:
    # Pattern: (\d+\.?\d*)  captures the numeric part.
    #          \s*%\s*       allows whitespace around the percent sign.
    #          (?:p\.a\.|per\s+annum)  matches both "p.a." and "per annum".
    # re.findall with a capture group returns only the captured part,
    # so matches is ["8.5", "9.0"], not ["8.5% p.a.", ...].
    # float() converts to float for comparison against _load_valid_rates().
    matches = re.findall(r"(\d+\.?\d*)\s*%\s*(?:p\.a\.|per\s+annum)", text, re.IGNORECASE)
    return [float(m) for m in matches]


# ---------------------------------------------------------------------------
# TODO 1 of 3 — implement _normalize_for_check()
# ---------------------------------------------------------------------------
# LLMs often output Unicode punctuation that looks like ASCII but breaks
# substring matching. This function:
#   1. Applies NFKC normalisation (unicodedata.normalize("NFKC", text))
#      This converts ligatures, full-width chars, etc.
#   2. Replaces all Unicode hyphen/dash variants with an ASCII hyphen
#      so "risk‑free" (U+2011 non-breaking hyphen) matches the banned phrase
#      "risk-free" (U+002D standard hyphen).
#      Variants to replace: ‐‑‒–—―−  (hyphen variants + minus sign)
#   3. Returns the lowercased result.
#
# Shape:
#   def _normalize_for_check(text: str) -> str:
#       text = unicodedata.normalize("NFKC", text)
#       for ch in "‐‑‒–—―−":
#           text = text.replace(ch, "-")
#       return text.lower()
# ---------------------------------------------------------------------------

def _normalize_for_check(text: str) -> str:
    """NFKC-normalise, convert Unicode hyphens to ASCII, lowercase."""
    # TODO 1: apply NFKC normalisation, replace Unicode hyphen variants, lowercase
    raise NotImplementedError("TODO 1: implement _normalize_for_check()")


# ---------------------------------------------------------------------------
# TODO 2 of 3 — implement _check_compliance()
# ---------------------------------------------------------------------------
# Check whether a draft response passes SEBI compliance rules.
# Returns a tuple: (passed: bool, reason: str)
#
# Two checks in order:
#
# A. Banned-phrase check:
#    normalized = _normalize_for_check(draft)
#    match = _BANNED_PATTERN.search(normalized)
#    if match:
#        return False, f"banned phrase: '{match.group()}'"
#
# B. Rate hallucination check:
#    mentioned_rates = _extract_rates(normalized)
#    if mentioned_rates:
#        valid_rates = _load_valid_rates()
#        if valid_rates:                             # skip if DB unavailable
#            for rate in mentioned_rates:
#                if rate not in valid_rates:
#                    return False, f"hallucinated rate: {rate}% p.a. not in database"
#
# Return True, "PASS" if both checks pass.
#
# WHY the if valid_rates guard?
#   If the DB is missing or corrupt, _load_valid_rates() returns an empty set.
#   An empty set would cause every rate to look like a hallucination.
#   The guard lets a valid response through when the DB is unavailable,
#   rather than silently failing every compliance check.
# ---------------------------------------------------------------------------

@traceable(name="sebi_compliance_check")
def _check_compliance(draft: str) -> tuple:
    """Return (True, 'PASS') or (False, reason) for the given draft."""
    # TODO 2: normalize, check banned phrases (_BANNED_PATTERN), check rates
    raise NotImplementedError("TODO 2: implement _check_compliance()")


# ---------------------------------------------------------------------------
# TODO 3 of 3 — implement check_compliance node
# ---------------------------------------------------------------------------
# This is the new node in the Session 9 graph (between respond and END).
#
# Steps:
#   1. Read the draft from state["response"].
#   2. Call _check_compliance(draft) → (passed, reason).
#   3a. If NOT passed:
#         print(f"[WealthDesk] Compliance FAIL: {reason}")
#         return {
#             "response":          SAFE_COMPLIANCE_RESPONSE,
#             "compliance_status": f"FAIL: {reason}",
#         }
#   3b. If passed:
#         print("[WealthDesk] Compliance PASS")
#         return {"compliance_status": "PASS"}
#
# WHY return only compliance_status on a PASS (not response)?
#   LangGraph merges returned dicts into the state. Returning "response"
#   on a PASS would overwrite the good response with itself — harmless but
#   wasteful. On a FAIL we replace the response with SAFE_COMPLIANCE_RESPONSE.
# ---------------------------------------------------------------------------

def check_compliance(state: WealthDeskState) -> dict:
    """Check SEBI compliance rules. Replace response if any rule is violated."""
    # TODO 3: read state["response"], call _check_compliance, return updated state
    raise NotImplementedError("TODO 3: implement check_compliance()")


def classify(state: WealthDeskState) -> dict:
    messages = [
        SystemMessage(content=CLASSIFY_SYSTEM),
        HumanMessage(content=state["customer_message"]),
    ]
    try:
        result = classifier_llm.invoke(messages)
        raw    = result.content.strip().upper()
        # Models sometimes return "OUT OF SCOPE" (space) or extra text.
        # Substring matching is more robust than an exact set check.
        if "OUT_OF_SCOPE" in raw or "OUT OF SCOPE" in raw:
            query_type = "OUT_OF_SCOPE"
        elif "COMPLEX" in raw:
            query_type = "COMPLEX"
        elif "SIMPLE" in raw:
            query_type = "SIMPLE"
        else:
            print(f"[WealthDesk] Unexpected classifier output: {repr(raw)!r} — defaulting to SIMPLE")
            query_type = "SIMPLE"
    except Exception as e:
        print(f"[WealthDesk] Classification error: {e}")
        query_type = "SIMPLE"
    return {"query_type": query_type}


def retrieve_docs(state: WealthDeskState) -> dict:
    _init_vectorstore()
    if vectorstore is None:
        return {"retrieved_docs": []}
    try:
        docs      = vectorstore.similarity_search(state["customer_message"], k=RETRIEVAL_K)
        retrieved = [
            f"[{doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
            for doc in docs
        ]
    except Exception as e:
        print(f"[WealthDesk] Retrieval error: {e}")
        retrieved = []
    return {"retrieved_docs": retrieved}


def respond(state: WealthDeskState) -> dict:
    history   = state.get("history", [])
    retrieved = state.get("retrieved_docs", [])

    if retrieved:
        context_block  = "\n\n---\n\n".join(retrieved)
        system_content = (
            SYSTEM_PROMPT
            + "\n\nThe following sections from BNB's policy documents are relevant "
              "to the customer's question. Use this information in your answer:\n\n"
            + context_block
        )
    else:
        system_content = SYSTEM_PROMPT

    messages = [SystemMessage(content=system_content)]
    for turn in history:
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["content"]))
        else:
            messages.append(AIMessage(content=turn["content"]))
    messages.append(HumanMessage(content=state["customer_message"]))

    try:
        result = llm_with_tools.invoke(messages)

        if result.tool_calls:
            messages.append(result)
            for tc in result.tool_calls:
                tool_output = _run_tool(tc["name"], tc["args"])
                print(
                    f"[WealthDesk] MCP tool: {tc['name']}({tc['args']}) "
                    f"-> {str(tool_output)[:80]}"
                )
                messages.append(
                    ToolMessage(
                        content=str(tool_output),
                        tool_call_id=tc["id"],
                    )
                )
            result = llm.invoke(messages)

        response_text = result.content

    except Exception as e:
        print(f"[WealthDesk] LLM error: {e}")
        response_text = "I am temporarily unavailable. Please try again in a moment."

    new_history = history + [
        {"role": "user",      "content": state["customer_message"]},
        {"role": "assistant", "content": response_text},
    ]
    return {"response": response_text, "history": new_history}


def escalate(state: WealthDeskState) -> dict:
    new_history = state.get("history", []) + [
        {"role": "user",      "content": state["customer_message"]},
        {"role": "assistant", "content": ESCALATE_RESPONSE},
    ]
    return {"response": ESCALATE_RESPONSE, "history": new_history}


def decline(state: WealthDeskState) -> dict:
    new_history = state.get("history", []) + [
        {"role": "user",      "content": state["customer_message"]},
        {"role": "assistant", "content": DECLINE_RESPONSE},
    ]
    return {"response": DECLINE_RESPONSE, "history": new_history}


def route_query(state: WealthDeskState) -> str:
    qt = state.get("query_type", "SIMPLE")
    if qt == "COMPLEX":
        return "escalate"
    if qt == "OUT_OF_SCOPE":
        return "decline"
    return "retrieve_docs"
