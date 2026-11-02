from langchain_chroma import Chroma
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_huggingface import HuggingFaceEmbeddings

from .config import (
    CLASSIFY_SYSTEM_PROMPT, DECLINE_RESPONSE, ESCALATE_RESPONSE,
    EMBED_MODEL, RETRIEVAL_K, RETRIEVAL_SCORE_THRESHOLD, SYSTEM_PROMPT, VECTORSTORE_DIR,
)
from .state import WealthDeskState
from .tools import classifier_llm, llm_with_tools, _run_tool

vectorstore = None

BLOCKLIST = [
    "ignore all previous",
    "forget everything",
    "you are now",
    "disregard your system",
    "act as",
    "jailbreak",
]


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


def classify(state: WealthDeskState) -> dict:
    msg = state["customer_message"].strip()

    if not msg or len(msg) < 3 or len(msg) > 500:
        return {"query_type": "OUT_OF_SCOPE", "retrieved_docs": []}

    if any(phrase in msg.lower() for phrase in BLOCKLIST):
        return {"query_type": "OUT_OF_SCOPE", "retrieved_docs": []}

    messages = [
        SystemMessage(content=CLASSIFY_SYSTEM_PROMPT),
        HumanMessage(content=state["customer_message"]),
    ]
    try:
        result     = classifier_llm.invoke(messages)
        query_type = result.content.strip().upper()
        if query_type not in {"SIMPLE", "COMPLEX", "OUT_OF_SCOPE"}:
            query_type = "SIMPLE"
    except Exception as e:
        print(f"[WealthDesk] Classification error: {e}")
        query_type = "SIMPLE"
    return {"query_type": query_type, "retrieved_docs": []}


def retrieve_docs(state: WealthDeskState) -> dict:
    _init_vectorstore()
    if vectorstore is None:
        return {"retrieved_docs": []}
    try:
        results   = vectorstore.similarity_search_with_relevance_scores(
            state["customer_message"], k=RETRIEVAL_K
        )
        retrieved = []
        for doc, score in results:
            if score >= RETRIEVAL_SCORE_THRESHOLD:
                retrieved.append(
                    f"[{doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
                )
            else:
                print(
                    f"[WealthDesk] Chunk skipped (score {score:.2f} < {RETRIEVAL_SCORE_THRESHOLD}): "
                    f"{doc.metadata.get('source', 'unknown')}"
                )
        print(f"[WealthDesk] Retrieval: {len(results)} candidates, {len(retrieved)} passed threshold ({RETRIEVAL_SCORE_THRESHOLD}).")
    except Exception as e:
        print(f"[WealthDesk] Retrieval error: {e}")
        retrieved = []
    return {"retrieved_docs": retrieved}


def respond(state: WealthDeskState) -> dict:
    history   = state.get("history", [])
    retrieved = state.get("retrieved_docs", [])

    # S04 escalated here when retrieved was empty — no docs meant no answer.
    # S05 removes that early return: even with no RAG docs, the LLM can still
    # call query_rates() or query_branch() to get a live answer from the database.
    # RAG and tools are now two independent data sources; either can satisfy the query.
    if retrieved:
        context_block  = "\n\n".join(f"<policy_chunk>\n{chunk}\n</policy_chunk>" for chunk in retrieved)
        system_content = (
            SYSTEM_PROMPT
            + f"\n\n<retrieved_documents>\n{context_block}\n</retrieved_documents>"
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

        # We execute tools manually here because WealthDeskState uses a custom
        # shape (history: list[dict]). In projects using LangGraph's standard
        # MessagesState you'd use the built-in ToolNode instead:
        #
        #   from langgraph.prebuilt import ToolNode
        #   builder.add_node("tools", ToolNode([query_rates, query_branch]))
        #   builder.add_edge("respond", "tools")
        #   builder.add_edge("tools", "respond")
        #
        # Both patterns are valid. ToolNode is less code; this gives more control.
        # result.tool_calls is a list of dicts, one per tool the LLM wants to call.
        # Each dict has exactly four keys — defined by LangChain's ToolCall TypedDict,
        # not by us. LangChain normalises across providers (OpenAI, Anthropic, Gemini
        # all return different raw formats; LangChain maps them to the same four keys):
        #   tc["name"] : str  -- tool name,  e.g. "query_rates"
        #   tc["args"] : dict -- arguments,  e.g. {"product_type": "loan"}
        #   tc["id"]   : str  -- unique ID,  e.g. "call_abc123" (used to match ToolMessage back)
        #   tc["type"] : str  -- always "tool_call" in this list
        # Example for "What is the home loan rate?":
        #   [{"name": "query_rates", "args": {"product_type": "loan"}, "id": "call_abc123", "type": "tool_call"}]
        #
        # AIMessage also has result.invalid_tool_calls (type = "invalid_tool_call") for
        # malformed calls the LLM returned (bad JSON, unknown name, etc.). We log those
        # below so they are visible rather than silently swallowed.
        if result.invalid_tool_calls:
            for itc in result.invalid_tool_calls:
                print(f"[WealthDesk] Invalid tool call ignored: {itc.get('name', 'unknown')} — {itc.get('error', 'parse error')}")
        # There can be valid as well as invalid tool calls in same turn hence two ifs instead of if else
        # while loop (not if) handles multi-round tool calling: after executing query_rates the LLM
        # may still want to call query_branch in the next round. Using if would call plain llm next,
        # which has no tools bound — Groq rejects that with "Tool choice is none, but model called a tool".
        # The loop keeps using llm_with_tools until the LLM stops requesting tools, then exits.
        max_tool_rounds = 5
        tool_rounds     = 0
        while result.tool_calls and tool_rounds < max_tool_rounds:
            messages.append(result)
            for tc in result.tool_calls:
                tool_output = _run_tool(tc["name"], tc["args"])
                print(f"[WealthDesk] Tool: {tc['name']}({tc['args']}) -> {str(tool_output)[:80]}")
                # tool_call_id links this result back to the specific tool call in the AIMessage above.
                # When the LLM calls multiple tools in one turn, the second LLM call uses these IDs
                # to know which result belongs to which call. Most providers reject ToolMessages
                # that have no matching tool_call_id in the message history.
                messages.append(ToolMessage(content=str(tool_output), tool_call_id=tc["id"]))
            tool_rounds += 1
            result = llm_with_tools.invoke(messages)

        response_text = result.content or ""
        if not response_text:
            response_text = "I am temporarily unavailable. Please try again in a moment."

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
