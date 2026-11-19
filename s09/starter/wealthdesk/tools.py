"""
wealthdesk/tools.py
-------------------
LLM clients and MCP-backed tool loading for WealthDesk.

query_rates and query_branch are discovered dynamically from the MCP server
(s07/solution/mcp_server.py) using langchain.mcp.MCPAdapter.
Unchanged from Session 8.
"""
import asyncio
import sys

from langchain_groq import ChatGroq
from langchain.mcp import MCPAdapter
# from langsmith import traceable  # Uncomment to label MCP server in traces (see below)

from .config import (
    CLASSIFIER_MAX_TOKENS,
    CLASSIFIER_MODEL,
    GROQ_API_KEY,
    MAX_TOKENS,
    MCP_SERVER_PATH,
    MODEL_NAME,
    TEMPERATURE,
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
    temperature=0.0,
    max_tokens=CLASSIFIER_MAX_TOKENS,
)

# ---------------------------------------------------------------------------
# MCP tool loading -- langchain.mcp.MCPAdapter (unchanged from Session 8)
# ---------------------------------------------------------------------------

_mcp_config = {
    "mcpServers": {
        "wealthdesk": {
            "command": sys.executable,
            "args": [str(MCP_SERVER_PATH)],
        }
    }
}


async def _load_tools():
    async with MCPAdapter(_mcp_config) as adapter:
        return await adapter.list_tools()


mcp_tools      = asyncio.run(_load_tools())
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


async def _invoke_via_mcp(tool_name: str, tool_args: dict) -> str:
    async with MCPAdapter(_mcp_config) as adapter:
        tools    = await adapter.list_tools()
        registry = {t.name: t for t in tools}
        result   = await registry[tool_name].ainvoke(tool_args)
        return _extract_text(result)


# @traceable(name="mcp · wealthdesk-tools")
# Uncomment the line above (and the import at the top) to see the MCP server name
# as a parent span in LangSmith: respond → mcp · wealthdesk-tools → query_rates
def _run_tool(tool_name: str, tool_args: dict) -> str:
    if tool_name not in _tool_registry:
        return f"Unknown tool: {tool_name}"
    try:
        return asyncio.run(_invoke_via_mcp(tool_name, tool_args))
    except Exception as e:
        return f"Tool error ({tool_name}): {e}"
