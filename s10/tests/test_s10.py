"""
s10/tests/test_s10.py
---------------------
Tests for Session 10: Multi-Agent Architecture (Supervisor + Specialist Agents).

Run with:
    pytest s10/tests/ -v

All tests use the solution directory (conftest patches MCPAdapter before import).
Mocks patch module-level instances (_nodes._documents_agent, _nodes._rates_agent)
rather than factory functions — the instances are already built at import time.

Test groups:
  TestState              (4)  -- specialist field, no compliance_status
  TestClassifyNode       (7)  -- all four categories, error handling
  TestDocumentsAgent     (6)  -- factory, compilation, invocation
  TestRatesAgent         (6)  -- factory, compilation, tool dispatch
  TestSupervisorNodes    (7)  -- call nodes stamp specialist; escalate/decline
  TestRouting            (5)  -- route_supervisor returns correct node names
  TestSupervisorGraph   (11)  -- build_graph, all nodes, all 4 routes
                              ─────
  Total                 46
"""
from unittest.mock import MagicMock, patch

import pytest

import wealthdesk.nodes as _nodes
from wealthdesk.config import DECLINE_RESPONSE, ESCALATE_RESPONSE
from wealthdesk.nodes import (
    call_documents_agent,
    call_rates_agent,
    classify,
    create_documents_agent,
    create_rates_agent,
    decline,
    escalate,
    route_supervisor,
)
from wealthdesk.state import WealthDeskState
from wealthdesk.agent import build_graph


# ---------------------------------------------------------------------------
# TestState  (4 tests)
# ---------------------------------------------------------------------------

class TestState:
    def test_specialist_field_present(self):
        assert "specialist" in WealthDeskState.__annotations__

    def test_no_compliance_status_field(self):
        assert "compliance_status" not in WealthDeskState.__annotations__

    def test_query_type_field_present(self):
        assert "query_type" in WealthDeskState.__annotations__

    def test_retrieved_docs_field_is_list(self):
        # TypedDict annotations store the type hint
        import typing
        hint = WealthDeskState.__annotations__["retrieved_docs"]
        assert "list" in str(hint).lower()


# ---------------------------------------------------------------------------
# TestClassifyNode  (7 tests)
# ---------------------------------------------------------------------------

class TestClassifyNode:
    def _state(self, msg: str) -> WealthDeskState:
        return {
            "customer_message": msg,
            "response": "",
            "history": [],
            "query_type": "",
            "retrieved_docs": [],
            "specialist": "",
        }

    def test_rates_category(self):
        with patch.object(_nodes, "classifier_llm") as m:
            m.invoke.return_value = MagicMock(content="RATES")
            result = classify(self._state("What is the home loan rate?"))
        assert result["query_type"] == "RATES"

    def test_policy_category(self):
        with patch.object(_nodes, "classifier_llm") as m:
            m.invoke.return_value = MagicMock(content="POLICY")
            result = classify(self._state("What documents do I need?"))
        assert result["query_type"] == "POLICY"

    def test_complex_category(self):
        with patch.object(_nodes, "classifier_llm") as m:
            m.invoke.return_value = MagicMock(content="COMPLEX")
            result = classify(self._state("Should I take a loan now?"))
        assert result["query_type"] == "COMPLEX"

    def test_out_of_scope_category(self):
        with patch.object(_nodes, "classifier_llm") as m:
            m.invoke.return_value = MagicMock(content="OUT_OF_SCOPE")
            result = classify(self._state("Who won the cricket World Cup?"))
        assert result["query_type"] == "OUT_OF_SCOPE"

    def test_invalid_label_defaults_to_rates(self):
        with patch.object(_nodes, "classifier_llm") as m:
            m.invoke.return_value = MagicMock(content="GIBBERISH")
            result = classify(self._state("some query"))
        assert result["query_type"] == "RATES"

    def test_classifier_error_defaults_to_rates(self):
        with patch.object(_nodes, "classifier_llm") as m:
            m.invoke.side_effect = RuntimeError("API down")
            result = classify(self._state("some query"))
        assert result["query_type"] == "RATES"

    def test_whitespace_stripped(self):
        with patch.object(_nodes, "classifier_llm") as m:
            m.invoke.return_value = MagicMock(content="  POLICY  ")
            result = classify(self._state("some policy question"))
        assert result["query_type"] == "POLICY"


# ---------------------------------------------------------------------------
# TestDocumentsAgent  (6 tests)
# ---------------------------------------------------------------------------

class TestDocumentsAgent:
    def test_factory_returns_compiled_graph(self):
        agent = create_documents_agent()
        assert agent is not None

    def test_two_calls_return_different_instances(self):
        a = create_documents_agent()
        b = create_documents_agent()
        assert a is not b

    def test_has_retrieve_docs_node(self):
        agent = create_documents_agent()
        # LangGraph compiled graphs expose their nodes
        assert "retrieve_docs" in agent.nodes

    def test_has_respond_node(self):
        agent = create_documents_agent()
        assert "respond" in agent.nodes

    def test_invocable_returns_response(self):
        with patch.object(_nodes, "llm") as m:
            m.invoke.return_value = MagicMock(content="Policy answer.")
            agent = create_documents_agent()
            result = agent.invoke({
                "customer_message": "What documents do I need?",
                "history": [],
                "response": "",
                "query_type": "POLICY",
                "retrieved_docs": [],
                "specialist": "",
            })
        assert "response" in result
        assert result["response"] == "Policy answer."

    def test_updates_history(self):
        with patch.object(_nodes, "llm") as m:
            m.invoke.return_value = MagicMock(content="Policy answer.")
            agent = create_documents_agent()
            result = agent.invoke({
                "customer_message": "What documents do I need?",
                "history": [],
                "response": "",
                "query_type": "POLICY",
                "retrieved_docs": [],
                "specialist": "",
            })
        assert len(result.get("history", [])) == 2


# ---------------------------------------------------------------------------
# TestRatesAgent  (6 tests)
# ---------------------------------------------------------------------------

class TestRatesAgent:
    def test_factory_returns_compiled_graph(self):
        agent = create_rates_agent()
        assert agent is not None

    def test_has_respond_node(self):
        agent = create_rates_agent()
        assert "respond" in agent.nodes

    def test_no_retrieve_docs_node(self):
        agent = create_rates_agent()
        assert "retrieve_docs" not in agent.nodes

    def test_invocable_no_tool_calls(self):
        with patch.object(_nodes, "llm_with_tools") as m:
            m.invoke.return_value = MagicMock(content="Rates answer.", tool_calls=[])
            agent = create_rates_agent()
            result = agent.invoke({
                "customer_message": "What is the home loan rate?",
                "history": [],
                "response": "",
                "query_type": "RATES",
                "retrieved_docs": [],
                "specialist": "",
            })
        assert result["response"] == "Rates answer."

    def test_tool_calls_dispatched(self):
        tool_call = {"name": "query_rates", "args": {"product_type": "loan"}, "id": "tc1"}
        first_response = MagicMock(content="", tool_calls=[tool_call])
        second_response = MagicMock(content="8.5% p.a.", tool_calls=[])

        with patch.object(_nodes, "llm_with_tools") as mock_tools_llm, \
             patch.object(_nodes, "llm") as mock_llm, \
             patch.object(_nodes, "_run_tool", return_value="Home Loan: 8.5%") as mock_tool:
            mock_tools_llm.invoke.return_value = first_response
            mock_llm.invoke.return_value = second_response

            agent = create_rates_agent()
            result = agent.invoke({
                "customer_message": "What is the home loan rate?",
                "history": [],
                "response": "",
                "query_type": "RATES",
                "retrieved_docs": [],
                "specialist": "",
            })

        mock_tool.assert_called_once_with("query_rates", {"product_type": "loan"})
        assert result["response"] == "8.5% p.a."

    def test_updates_history(self):
        with patch.object(_nodes, "llm_with_tools") as m:
            m.invoke.return_value = MagicMock(content="Rates answer.", tool_calls=[])
            agent = create_rates_agent()
            result = agent.invoke({
                "customer_message": "What is the home loan rate?",
                "history": [],
                "response": "",
                "query_type": "RATES",
                "retrieved_docs": [],
                "specialist": "",
            })
        assert len(result.get("history", [])) == 2


# ---------------------------------------------------------------------------
# TestSupervisorNodes  (7 tests)
# ---------------------------------------------------------------------------

class TestSupervisorNodes:
    def _state(self, msg: str = "test", qt: str = "RATES") -> WealthDeskState:
        return {
            "customer_message": msg,
            "response": "",
            "history": [],
            "query_type": qt,
            "retrieved_docs": [],
            "specialist": "",
        }

    def test_call_documents_agent_sets_specialist(self):
        with patch.object(_nodes, "_documents_agent") as mock_agent:
            mock_agent.invoke.return_value = {
                "response": "Policy info.", "history": [], "retrieved_docs": ["chunk1"]
            }
            result = call_documents_agent(self._state(qt="POLICY"))
        assert result["specialist"] == "documents_agent"

    def test_call_documents_agent_returns_response(self):
        with patch.object(_nodes, "_documents_agent") as mock_agent:
            mock_agent.invoke.return_value = {
                "response": "Required docs: PAN, Aadhaar.", "history": [], "retrieved_docs": []
            }
            result = call_documents_agent(self._state(qt="POLICY"))
        assert result["response"] == "Required docs: PAN, Aadhaar."

    def test_call_documents_agent_returns_retrieved_docs(self):
        with patch.object(_nodes, "_documents_agent") as mock_agent:
            mock_agent.invoke.return_value = {
                "response": "Policy.", "history": [], "retrieved_docs": ["[source]\nchunk"]
            }
            result = call_documents_agent(self._state(qt="POLICY"))
        assert len(result["retrieved_docs"]) == 1

    def test_call_rates_agent_sets_specialist(self):
        with patch.object(_nodes, "_rates_agent") as mock_agent:
            mock_agent.invoke.return_value = {
                "response": "Home Loan: 8.5% p.a.", "history": []
            }
            result = call_rates_agent(self._state(qt="RATES"))
        assert result["specialist"] == "rates_agent"

    def test_call_rates_agent_returns_response(self):
        with patch.object(_nodes, "_rates_agent") as mock_agent:
            mock_agent.invoke.return_value = {
                "response": "Home Loan: 8.5% p.a.", "history": []
            }
            result = call_rates_agent(self._state(qt="RATES"))
        assert result["response"] == "Home Loan: 8.5% p.a."

    def test_escalate_sets_specialist(self):
        result = escalate(self._state())
        assert result["specialist"] == "escalated"

    def test_decline_sets_specialist(self):
        result = decline(self._state())
        assert result["specialist"] == "declined"


# ---------------------------------------------------------------------------
# TestRouting  (5 tests)
# ---------------------------------------------------------------------------

class TestRouting:
    def _state(self, qt: str) -> WealthDeskState:
        return {
            "customer_message": "test",
            "response": "",
            "history": [],
            "query_type": qt,
            "retrieved_docs": [],
            "specialist": "",
        }

    def test_policy_routes_to_documents_agent(self):
        assert route_supervisor(self._state("POLICY")) == "call_documents_agent"

    def test_rates_routes_to_rates_agent(self):
        assert route_supervisor(self._state("RATES")) == "call_rates_agent"

    def test_complex_routes_to_escalate(self):
        assert route_supervisor(self._state("COMPLEX")) == "escalate"

    def test_oos_routes_to_decline(self):
        assert route_supervisor(self._state("OUT_OF_SCOPE")) == "decline"

    def test_unknown_routes_to_rates_agent(self):
        assert route_supervisor(self._state("UNKNOWN")) == "call_rates_agent"


# ---------------------------------------------------------------------------
# TestSupervisorGraph  (11 tests)
# ---------------------------------------------------------------------------

class TestSupervisorGraph:
    def test_build_graph_with_checkpointer(self):
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph(checkpointer=MemorySaver())
        assert graph is not None

    def test_build_graph_no_checkpointer(self):
        graph = build_graph()
        assert graph is not None

    def test_has_classify_node(self):
        graph = build_graph()
        assert "classify" in graph.nodes

    def test_has_call_documents_agent_node(self):
        graph = build_graph()
        assert "call_documents_agent [subgraph]" in graph.nodes

    def test_has_call_rates_agent_node(self):
        graph = build_graph()
        assert "call_rates_agent [subgraph]" in graph.nodes

    def test_has_escalate_node(self):
        graph = build_graph()
        assert "escalate" in graph.nodes

    def test_has_decline_node(self):
        graph = build_graph()
        assert "decline" in graph.nodes

    def test_policy_route_invokes_documents_agent(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_cls, \
             patch.object(_nodes, "_documents_agent") as mock_docs:
            mock_cls.invoke.return_value = MagicMock(content="POLICY")
            mock_docs.invoke.return_value = {
                "response": "Policy info.", "history": [], "retrieved_docs": []
            }
            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "What documents do I need?", "response": "",
                 "specialist": "", "retrieved_docs": []},
                config={"configurable": {"thread_id": "test-s10-policy"}},
            )

        assert result["specialist"] == "documents_agent"
        assert result["query_type"] == "POLICY"

    def test_rates_route_invokes_rates_agent(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_cls, \
             patch.object(_nodes, "_rates_agent") as mock_rates:
            mock_cls.invoke.return_value = MagicMock(content="RATES")
            mock_rates.invoke.return_value = {
                "response": "Home Loan: 8.5% p.a.", "history": []
            }
            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "What is the home loan rate?", "response": "",
                 "specialist": "", "retrieved_docs": []},
                config={"configurable": {"thread_id": "test-s10-rates"}},
            )

        assert result["specialist"] == "rates_agent"
        assert result["query_type"] == "RATES"

    def test_complex_route_escalates(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_cls:
            mock_cls.invoke.return_value = MagicMock(content="COMPLEX")
            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "Should I take a loan now?", "response": "",
                 "specialist": "", "retrieved_docs": []},
                config={"configurable": {"thread_id": "test-s10-complex"}},
            )

        assert result["specialist"] == "escalated"
        assert "Relationship Manager" in result["response"]

    def test_oos_route_declines(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_cls:
            mock_cls.invoke.return_value = MagicMock(content="OUT_OF_SCOPE")
            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "Who won the IPL?", "response": "",
                 "specialist": "", "retrieved_docs": []},
                config={"configurable": {"thread_id": "test-s10-oos"}},
            )

        assert result["specialist"] == "declined"
        assert "only help with BNB" in result["response"]
