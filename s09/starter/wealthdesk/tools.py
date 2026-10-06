"""
wealthdesk/tools.py
-------------------
LLM clients and MCP-backed tool loading for WealthDesk.
Unchanged from Session 8.
"""
import asyncio
import sys

from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
# from langsmith import traceable  # Uncomment to label MCP server in traces (see below)

from .config import GROQ_API_KEY, MAX_TOKENS, MCP_SERVER_PATH, MODEL_NAME, TEMPERATURE

llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=MODEL_NAME,
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
)

classifier_llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=MODEL_NAME,
    temperature=0.0,
    max_tokens=10,
)

# ---------------------------------------------------------------------------
# MCP tool loading -- langchain-mcp-adapters (unchanged from Session 8)
# ---------------------------------------------------------------------------

_mcp_client = MultiServerMCPClient({
    "wealthdesk": {
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(MCP_SERVER_PATH)],
    }
})

mcp_tools      = asyncio.run(_mcp_client.get_tools())   # [query_rates, query_branch]
_tool_registry = {t.name: t for t in mcp_tools}

llm_with_tools = llm.bind_tools(mcp_tools)


def _extract_text(result) -> str:
    """MCP tool results come back as a list of content blocks, e.g.
    [{"type": "text", "text": "...", "id": "..."}]. Join the text blocks
    into the plain string the rest of the agent code expects."""
    if isinstance(result, list):
        return "\n".join(
            block.get("text", "") for block in result if isinstance(block, dict)
        )
    return str(result)


# @traceable(name="mcp · wealthdesk-tools")
# Uncomment the line above (and the import at the top) to see the MCP server name
# as a parent span in LangSmith: respond → mcp · wealthdesk-tools → query_rates
def _run_tool(tool_name: str, tool_args: dict) -> str:
    if tool_name not in _tool_registry:
        return f"Unknown tool: {tool_name}"
    try:
        result = asyncio.run(_tool_registry[tool_name].ainvoke(tool_args))
        return _extract_text(result)
    except Exception as e:
        return f"Tool error ({tool_name}): {e}"
