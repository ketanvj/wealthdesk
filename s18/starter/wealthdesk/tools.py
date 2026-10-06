"""
S18 tools — identical to S16 (SSE MCP), now reads from Pydantic settings.
"""
import asyncio

from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import settings

llm = ChatGroq(
    api_key=settings.groq_api_key,
    model=settings.model_name,
    temperature=settings.temperature,
    max_tokens=settings.max_tokens,
)

classifier_llm = ChatGroq(
    api_key=settings.groq_api_key,
    model=settings.classifier_model,
    temperature=0.0,
    max_tokens=settings.classifier_max_tokens,
)

_mcp_client = MultiServerMCPClient({
    "wealthdesk": {
        "transport": "sse",
        "url": settings.mcp_server_url,
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
