"""
S16 tools: change the MCP client from stdio subprocess to SSE HTTP.

Before (S15 — stdio):
    _mcp_client = MultiServerMCPClient({
        "wealthdesk": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(MCP_SERVER_PATH)],
        }
    })

After (S16 — SSE):
    _mcp_client = MultiServerMCPClient({
        "wealthdesk": {
            "transport": "sse",
            "url": MCP_SERVER_URL,          # e.g. "http://localhost:8001/sse"
        }
    })

IMPORTANT: the MCP server must be running BEFORE this module is imported.
Start it first: python mcp_server.py

Your task
  TODO 3: Update the MultiServerMCPClient block below to use SSE transport.
"""
import asyncio

from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import (
    CLASSIFIER_MAX_TOKENS,
    CLASSIFIER_MODEL,
    GROQ_API_KEY,
    MAX_TOKENS,
    MCP_SERVER_URL,
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
# TODO 3: Change transport from stdio to SSE
# ---------------------------------------------------------------------------
# Replace the stdio config with an SSE config that uses MCP_SERVER_URL.
# The rest of this file (mcp_tools, _tool_registry, llm_with_tools) stays
# exactly the same — that's the point: transport is the ONLY change.

_mcp_client = MultiServerMCPClient({
    "wealthdesk": {
        # TODO: change "transport" and "url" here
        "transport": "stdio",       # change to "sse"
        "url": MCP_SERVER_URL,      # this line is new — remove the stdio keys
        # REMOVE these two stdio lines once you switch to SSE:
        # "command": sys.executable,
        # "args": [str(MCP_SERVER_PATH)],
    }
})

mcp_tools      = asyncio.run(_mcp_client.get_tools())
_tool_registry = {t.name: t for t in mcp_tools}

llm_with_tools = llm.bind_tools(mcp_tools)


def _extract_text(result) -> str:
    if isinstance(result, list):
        return "\n".join(
            block.get("text", "") for block in result if isinstance(block, dict)
        )
    return str(result)


def _run_tool(tool_name: str, **kwargs) -> str:
    tool = _tool_registry.get(tool_name)
    if tool is None:
        return f"[Error: tool '{tool_name}' not found in MCP server]"
    result = asyncio.run(tool.ainvoke(kwargs))
    return _extract_text(result)
