"""
s10/tests/conftest.py
---------------------
Patches MCPAdapter before wealthdesk.tools is imported.
asyncio.run(_load_tools()) runs at module level in tools.py, so the patch must
happen BEFORE any wealthdesk.* import — same pattern as S08/S09.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")

for _k in list(sys.modules):
    if _k == "wealthdesk" or _k.startswith("wealthdesk."):
        sys.modules.pop(_k)

SOLUTION_DIR = Path(__file__).parent.parent / "solution"
sys.path.insert(0, str(SOLUTION_DIR))

from langchain_core.tools import StructuredTool   # noqa: E402


def _query_rates(product_type: str = "all") -> str:
    """Fetch current BNB interest rates from the database."""
    return f"mock rates for {product_type}"


def _query_branch(city: str = "all") -> str:
    """Fetch BNB branch locations from the database."""
    return f"mock branches for {city}"


MOCK_MCP_TOOLS = [
    StructuredTool.from_function(_query_rates, name="query_rates"),
    StructuredTool.from_function(_query_branch, name="query_branch"),
]


class _FakeMCPAdapter:
    def __init__(self, _config):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def list_tools(self):
        return MOCK_MCP_TOOLS


with patch("langchain.mcp.MCPAdapter", _FakeMCPAdapter):
    import wealthdesk.tools as _tools   # noqa: F401
    import wealthdesk.nodes as _nodes   # noqa: F401
    import wealthdesk.agent             # noqa: F401
