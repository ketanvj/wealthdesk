"""
wealthdesk/tools.py
-------------------
STARTER FILE -- your task is to implement the three TODO sections below.

Goal
  Connect the WealthDesk agent to the MCP server built in Session 7
  (s07/solution/mcp_server.py) using langchain-mcp-adapters instead of
  hand-written @tool functions. The graph and agent code are unchanged
  from Session 5 -- only how query_rates/query_branch are sourced changes.

What is already done for you
  - LLM clients (llm, classifier_llm) are created below
  - MCP_SERVER_PATH points to the Session 7 server
  - _extract_text() and _run_tool()'s docstring/signature are provided

Your task
  TODO 1: Create a MultiServerMCPClient pointing at the Session 7 server
  TODO 2: Load its tools (async, bridged with asyncio.run) and bind them to llm
  TODO 3: Implement _run_tool() to dispatch a call by name and extract the
          plain-text result from the MCP content-block list

Run when done
  python -m wealthdesk.agent   (from inside s08/starter/)
"""
import asyncio
import sys

from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
# from langsmith import traceable  # Uncomment to label MCP server in traces (see below)

from .config import (
    CLASSIFIER_MAX_TOKENS, CLASSIFIER_MODEL, CLASSIFIER_TEMPERATURE,
    GROQ_API_KEY, MAX_TOKENS, MCP_SERVER_PATH, MODEL_NAME, TEMPERATURE,
)

llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=MODEL_NAME,
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
)

classifier_llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=CLASSIFIER_MODEL,
    temperature=CLASSIFIER_TEMPERATURE,
    max_tokens=CLASSIFIER_MAX_TOKENS,
)


# ---------------------------------------------------------------------------
# TODO 1 of 3 -- Create the MultiServerMCPClient
# ---------------------------------------------------------------------------
# MultiServerMCPClient takes a dict mapping a server name you choose (e.g.
# "wealthdesk") to a connection config. For a stdio server, the config needs:
#   "transport": "stdio"
#   "command":   sys.executable          -- run the server with this Python
#   "args":      [str(MCP_SERVER_PATH)]  -- the script to run
#
#   _mcp_client = MultiServerMCPClient({
#       "wealthdesk": {
#           "transport": "stdio",
#           "command": sys.executable,
#           "args": [str(MCP_SERVER_PATH)],
#       }
#   })
# ---------------------------------------------------------------------------
_mcp_client = None  # TODO 1: replace with a MultiServerMCPClient(...) instance


# ---------------------------------------------------------------------------
# TODO 2 of 3 -- Load the server's tools and bind them to the LLM
# ---------------------------------------------------------------------------
# _mcp_client.get_tools() is async and returns a list of ready-to-bind
# LangChain tools (their names/descriptions/schemas come from the server's
# own @mcp.tool() docstrings -- no second copy of them needed here). Bridge
# it to sync with asyncio.run() once, at module import time:
#
#   mcp_tools      = asyncio.run(_mcp_client.get_tools())
#   _tool_registry = {t.name: t for t in mcp_tools}
#   llm_with_tools = llm.bind_tools(mcp_tools)
# ---------------------------------------------------------------------------
mcp_tools      = []    # TODO 2: replace with asyncio.run(_mcp_client.get_tools())
_tool_registry = {}    # TODO 2: replace with {t.name: t for t in mcp_tools}
llm_with_tools = None  # TODO 2: replace with llm.bind_tools(mcp_tools)


def _extract_text(result) -> str:
    """MCP tool results come back as a list of content blocks, e.g.
    [{"type": "text", "text": "...", "id": "..."}]. Join the text blocks
    into the plain string the rest of the agent code expects. Provided --
    no changes needed."""
    if isinstance(result, list):
        return "\n".join(
            block.get("text", "") for block in result if isinstance(block, dict)
        )
    return str(result)


# ---------------------------------------------------------------------------
# TODO 3 of 3 -- Implement _run_tool()
# ---------------------------------------------------------------------------
# Look up tool_name in _tool_registry. If missing, return an "Unknown tool"
# message. Otherwise call it -- tools loaded via langchain-mcp-adapters are
# async-only (they negotiate a fresh MCP session per call), so bridge with
# asyncio.run(tool.ainvoke(tool_args)) inside a try/except, then pass the
# result through _extract_text() to get a plain string:
#
#   # @traceable(name="mcp · wealthdesk-tools")
#   # Uncomment the line above (and the import at the top) to see the MCP server
#   # name as a parent span in LangSmith: respond → mcp · wealthdesk-tools → query_rates
#   def _run_tool(tool_name: str, tool_args: dict) -> str:
#       if tool_name not in _tool_registry:
#           return f"Unknown tool: {tool_name}"
#       try:
#           result = asyncio.run(_tool_registry[tool_name].ainvoke(tool_args))
#           return _extract_text(result)
#       except Exception as e:
#           return f"Tool error ({tool_name}): {e}"
# ---------------------------------------------------------------------------
# @traceable(name="mcp · wealthdesk-tools")
# Uncomment the line above (and the import at the top) to see the MCP server name
# as a parent span in LangSmith: respond → mcp · wealthdesk-tools → query_rates
def _run_tool(tool_name: str, tool_args: dict) -> str:
    raise NotImplementedError("TODO 3: implement _run_tool()")
