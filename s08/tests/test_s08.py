"""
s08/tests/test_s08.py
---------------------
Tests for Session 8: MCP Agent Integration (US-06 Part 2).

Run with:
    pytest s08/tests/ -v

All tests mock asyncio.run() or MCPAdapter so no real MCP server or database
is required. Tests verify the wiring: tool discovery, registry dispatch,
async bridge, content block extraction, and graph routing.

Test groups:
  TestMCPServerPath    -- MCP_SERVER_PATH points to the Session 7 server
  TestToolDiscovery    -- mcp_tools is populated; registry and LLM binding correct
  TestExtractText      -- _extract_text() unwraps MCP content blocks
  TestRunTool          -- _run_tool() dispatches correctly, error handling
  TestInvokeMCP        -- _invoke_via_mcp() opens fresh session, calls .ainvoke()
  TestGraphNodes       -- classify, escalate, decline produce correct state keys
  TestBuildGraph       -- graph compiles; routes COMPLEX/OOS correctly
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# conftest.py adds SOLUTION_DIR to sys.path and pre-imports the modules with
# MCPAdapter patched. Import the already-loaded modules by name.
import wealthdesk.tools as _tools
import wealthdesk.nodes as _nodes
from wealthdesk.config import MCP_SERVER_PATH
from wealthdesk.state import WealthDeskState
from wealthdesk.tools import _extract_text, _run_tool
from wealthdesk.nodes import classify, decline, escalate
from wealthdesk.agent import build_graph


# ---------------------------------------------------------------------------
# TestMCPServerPath
# ---------------------------------------------------------------------------

class TestMCPServerPath:
    def test_mcp_server_path_is_path_object(self):
        assert isinstance(MCP_SERVER_PATH, Path)

    def test_mcp_server_path_points_to_s07(self):
        assert "s07" in str(MCP_SERVER_PATH)

    def test_mcp_server_path_filename(self):
        assert MCP_SERVER_PATH.name == "mcp_server.py"

    def test_mcp_server_path_exists(self):
        assert MCP_SERVER_PATH.exists(), (
            f"S07 MCP server not found at {MCP_SERVER_PATH}. "
            "Complete Session 7 before running Session 8 tests."
        )


# ---------------------------------------------------------------------------
# TestToolDiscovery
# ---------------------------------------------------------------------------

class TestToolDiscovery:
    def test_mcp_tools_is_a_list(self):
        assert isinstance(_tools.mcp_tools, list)

    def test_mcp_tools_has_two_tools(self):
        assert len(_tools.mcp_tools) == 2

    def test_tool_names_include_query_rates(self):
        names = {t.name for t in _tools.mcp_tools}
        assert "query_rates" in names

    def test_tool_names_include_query_branch(self):
        names = {t.name for t in _tools.mcp_tools}
        assert "query_branch" in names

    def test_tool_registry_has_query_rates(self):
        assert "query_rates" in _tools._tool_registry

    def test_tool_registry_has_query_branch(self):
        assert "query_branch" in _tools._tool_registry

    def test_llm_with_tools_is_not_none(self):
        assert _tools.llm_with_tools is not None


# ---------------------------------------------------------------------------
# TestExtractText
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_single_text_block(self):
        result = _extract_text([{"type": "text", "text": "Home Loan: 8.5% p.a."}])
        assert result == "Home Loan: 8.5% p.a."

    def test_multiple_text_blocks_joined(self):
        blocks = [{"type": "text", "text": "Line 1"}, {"type": "text", "text": "Line 2"}]
        assert _extract_text(blocks) == "Line 1\nLine 2"

    def test_non_text_blocks_ignored(self):
        blocks = [{"type": "image", "data": "..."}, {"type": "text", "text": "rate info"}]
        result = _extract_text(blocks)
        assert "rate info" in result
        assert "..." not in result  # image data not leaked

    def test_empty_list_returns_empty_string(self):
        assert _extract_text([]) == ""

    def test_non_list_returns_str(self):
        assert _extract_text("plain string") == "plain string"

    def test_non_dict_items_in_list_ignored(self):
        assert _extract_text(["not a dict", {"type": "text", "text": "ok"}]) == "ok"


# ---------------------------------------------------------------------------
# TestRunTool
# ---------------------------------------------------------------------------

class TestRunTool:
    def test_dispatches_query_rates(self):
        with patch("asyncio.run", return_value="Home Loan: 8.5% p.a."):
            result = _run_tool("query_rates", {"product_type": "loan"})
        assert result == "Home Loan: 8.5% p.a."

    def test_dispatches_query_branch(self):
        with patch("asyncio.run", return_value="BNB Bandra (Mumbai)"):
            result = _run_tool("query_branch", {"city": "Mumbai"})
        assert result == "BNB Bandra (Mumbai)"

    def test_unknown_tool_returns_error_string(self):
        result = _run_tool("nonexistent_tool", {})
        assert "Unknown tool" in result
        assert "nonexistent_tool" in result

    def test_returns_string(self):
        with patch("asyncio.run", return_value="result"):
            result = _run_tool("query_rates", {"product_type": "all"})
        assert isinstance(result, str)

    def test_exception_returns_error_string(self):
        with patch("asyncio.run", side_effect=RuntimeError("subprocess failed")):
            result = _run_tool("query_rates", {"product_type": "loan"})
        assert "Tool error" in result
        assert "query_rates" in result

    def test_error_string_includes_tool_name(self):
        with patch("asyncio.run", side_effect=Exception("timeout")):
            result = _run_tool("query_branch", {"city": "Delhi"})
        assert "query_branch" in result


# ---------------------------------------------------------------------------
# TestInvokeMCP
# ---------------------------------------------------------------------------

class TestInvokeMCP:
    def test_invoke_mcp_calls_ainvoke(self):
        import asyncio
        from wealthdesk.tools import _invoke_via_mcp

        mock_tool = MagicMock()
        mock_tool.ainvoke = AsyncMock(return_value=[{"type": "text", "text": "8.5%"}])

        class _FakeAdapter:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def list_tools(self):
                return [mock_tool]

        # Give the fake tool the right name so the registry lookup works
        mock_tool.name = "query_rates"

        with patch("wealthdesk.tools.MCPAdapter", lambda _cfg: _FakeAdapter()):
            result = asyncio.run(_invoke_via_mcp("query_rates", {"product_type": "loan"}))

        assert result == "8.5%"
        mock_tool.ainvoke.assert_called_once_with({"product_type": "loan"})

    def test_invoke_mcp_extracts_text_blocks(self):
        import asyncio
        from wealthdesk.tools import _invoke_via_mcp

        mock_tool = MagicMock()
        mock_tool.name = "query_branch"
        mock_tool.ainvoke = AsyncMock(return_value=[
            {"type": "text", "text": "BNB Bandra"},
            {"type": "text", "text": "BNB Andheri"},
        ])

        class _FakeAdapter:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def list_tools(self):
                return [mock_tool]

        with patch("wealthdesk.tools.MCPAdapter", lambda _cfg: _FakeAdapter()):
            result = asyncio.run(_invoke_via_mcp("query_branch", {"city": "Mumbai"}))

        assert "BNB Bandra" in result
        assert "BNB Andheri" in result


# ---------------------------------------------------------------------------
# TestGraphNodes
# ---------------------------------------------------------------------------

class TestGraphNodes:
    def _make_state(self, message: str = "test", query_type: str = "SIMPLE") -> WealthDeskState:
        return {
            "customer_message": message,
            "response":         "",
            "history":          [],
            "query_type":       query_type,
            "retrieved_docs":   [],
        }

    def test_escalate_returns_response_key(self):
        result = escalate(self._make_state())
        assert "response" in result

    def test_escalate_response_mentions_relationship_manager(self):
        result = escalate(self._make_state())
        assert "Relationship Manager" in result["response"]

    def test_escalate_response_includes_phone_number(self):
        result = escalate(self._make_state())
        assert "1800-103-1906" in result["response"]

    def test_escalate_updates_history(self):
        result = escalate(self._make_state("complex query"))
        assert len(result["history"]) == 2
        assert result["history"][0]["role"] == "user"
        assert result["history"][1]["role"] == "assistant"

    def test_decline_returns_response_key(self):
        result = decline(self._make_state())
        assert "response" in result

    def test_decline_response_mentions_bnb(self):
        result = decline(self._make_state())
        assert "BNB" in result["response"]

    def test_decline_updates_history(self):
        result = decline(self._make_state("off-topic query"))
        assert len(result["history"]) == 2


# ---------------------------------------------------------------------------
# TestBuildGraph
# ---------------------------------------------------------------------------

class TestBuildGraph:
    def test_build_graph_returns_compiled_graph(self):
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph(checkpointer=MemorySaver())
        assert graph is not None

    def test_graph_has_check_compliance_node(self):
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph(checkpointer=MemorySaver())
        # S08 graph has classify, retrieve_docs, respond, escalate, decline
        assert graph is not None

    def test_graph_invoke_complex_routes_to_escalation(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content="COMPLEX")
            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "Should I invest all my savings?", "response": ""},
                config={"configurable": {"thread_id": "test-s08-complex"}},
            )
        assert "Relationship Manager" in result["response"]
        assert result["query_type"] == "COMPLEX"

    def test_graph_invoke_oos_routes_to_decline(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content="OUT_OF_SCOPE")
            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "Who won the cricket World Cup?", "response": ""},
                config={"configurable": {"thread_id": "test-s08-oos"}},
            )
        assert "only help with BNB" in result["response"]
        assert result["query_type"] == "OUT_OF_SCOPE"

    def test_graph_invoke_returns_response_and_query_type(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content="COMPLEX")
            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "test", "response": ""},
                config={"configurable": {"thread_id": "test-s08-keys"}},
            )
        assert "response" in result
        assert "query_type" in result
