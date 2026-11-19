"""
s09/tests/test_s09.py
---------------------
Tests for Session 9: SEBI Compliance Filter + LangSmith Observability.

Run with:
    pytest s09/tests/ -v

Tests verify the compliance layer added in S09:
  _normalize_for_check() — Unicode hyphen handling
  _extract_rates()       — rate pattern extraction
  _check_compliance()    — banned-phrase and hallucinated-rate detection
  check_compliance node  — state update on PASS and FAIL

Also verifies the full graph (S09 adds check_compliance between respond and END).

Test groups:
  TestNormalize        -- _normalize_for_check() Unicode/ASCII handling
  TestExtractRates     -- _extract_rates() pattern matching
  TestCheckCompliance  -- banned phrases + hallucinated rates
  TestComplianceNode   -- check_compliance() state updates
  TestBuildGraph       -- S09 graph structure and routing
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import wealthdesk.nodes as _nodes
from wealthdesk.config import SAFE_COMPLIANCE_RESPONSE, SEBI_BANNED_PHRASES
from wealthdesk.nodes import (
    _check_compliance,
    _extract_rates,
    _normalize_for_check,
    check_compliance,
    decline,
    escalate,
)
from wealthdesk.state import WealthDeskState
from wealthdesk.agent import build_graph


# ---------------------------------------------------------------------------
# TestNormalize
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_lowercases_text(self):
        assert _normalize_for_check("RISK-FREE") == "risk-free"

    def test_ascii_hyphen_preserved(self):
        result = _normalize_for_check("risk-free")
        assert "risk-free" in result

    def test_unicode_non_breaking_hyphen(self):
        # U+2011 non-breaking hyphen → ASCII hyphen
        result = _normalize_for_check("risk‑free")
        assert "risk-free" in result

    def test_en_dash(self):
        # U+2013 en-dash → ASCII hyphen
        result = _normalize_for_check("risk–free")
        assert "risk-free" in result

    def test_em_dash(self):
        # U+2014 em-dash → ASCII hyphen
        result = _normalize_for_check("risk—free")
        assert "risk-free" in result

    def test_unicode_minus_sign(self):
        # U+2212 minus sign → ASCII hyphen
        result = _normalize_for_check("risk−free")
        assert "risk-free" in result

    def test_nfkc_applied(self):
        # U+2126 Ohm sign normalises to U+03A9 Omega under NFKC
        result = _normalize_for_check("Ω")
        assert "ω" in result or "Ω" in result.upper()

    def test_returns_lowercase(self):
        assert _normalize_for_check("Hello") == "hello"


# ---------------------------------------------------------------------------
# TestExtractRates
# ---------------------------------------------------------------------------

class TestExtractRates:
    def test_extracts_decimal_rate(self):
        rates = _extract_rates("Home loan rate: 8.5% p.a.")
        assert 8.5 in rates

    def test_extracts_integer_rate(self):
        rates = _extract_rates("FD rate: 6% p.a.")
        assert 6.0 in rates

    def test_extracts_per_annum_form(self):
        rates = _extract_rates("Interest rate is 9.99% per annum.")
        assert 9.99 in rates

    def test_extracts_multiple_rates(self):
        rates = _extract_rates("Home loan: 8.5% p.a. and car loan: 9.5% p.a.")
        assert 8.5 in rates
        assert 9.5 in rates

    def test_ignores_non_rate_percentages(self):
        rates = _extract_rates("Processing fee: 2% of loan amount.")
        assert rates == []

    def test_empty_string(self):
        assert _extract_rates("") == []

    def test_returns_floats(self):
        rates = _extract_rates("FD: 5.5% p.a.")
        assert all(isinstance(r, float) for r in rates)


# ---------------------------------------------------------------------------
# TestCheckCompliance
# ---------------------------------------------------------------------------

class TestCheckCompliance:
    def test_clean_text_passes(self):
        ok, reason = _check_compliance("BNB offers home loans at competitive rates.")
        assert ok
        assert reason == "PASS"

    def test_guaranteed_returns_fails(self):
        ok, reason = _check_compliance("Our FD offers guaranteed returns of 7%.")
        assert not ok
        assert "guaranteed returns" in reason

    def test_risk_free_ascii_hyphen_fails(self):
        ok, reason = _check_compliance("This is a risk-free investment.")
        assert not ok
        assert "risk-free" in reason

    def test_risk_free_unicode_hyphen_fails(self):
        # U+2011 non-breaking hyphen — should still match after normalisation
        ok, reason = _check_compliance("This is a risk‑free investment.")
        assert not ok
        assert "risk-free" in reason

    def test_no_risk_fails(self):
        ok, reason = _check_compliance("This product has no risk at all.")
        assert not ok

    def test_assured_profit_fails(self):
        ok, reason = _check_compliance("BNB provides assured profit on FDs.")
        assert not ok

    def test_valid_rate_passes(self):
        # 8.5% is in the BNB DB for home loans
        ok, reason = _check_compliance("Home loan rate is 8.5% p.a.")
        assert ok
        assert reason == "PASS"

    def test_hallucinated_rate_fails(self):
        ok, reason = _check_compliance("Home loan rate is 9.99% p.a.")
        assert not ok
        assert "9.99" in reason

    def test_hallucinated_per_annum_fails(self):
        ok, reason = _check_compliance("Rate is 9.99% per annum.")
        assert not ok
        assert "9.99" in reason

    def test_banned_phrase_checked_before_rates(self):
        # Both violations: banned phrase should be caught first
        ok, reason = _check_compliance("Guaranteed returns at 9.99% p.a.")
        assert not ok
        assert "guaranteed" in reason.lower()

    def test_no_rate_mentioned_passes(self):
        ok, reason = _check_compliance("BNB offers home loans and FDs.")
        assert ok


# ---------------------------------------------------------------------------
# TestComplianceNode
# ---------------------------------------------------------------------------

class TestComplianceNode:
    def _make_state(self, response: str, msg: str = "test") -> WealthDeskState:
        return {
            "customer_message":  msg,
            "response":          response,
            "history":           [],
            "query_type":        "SIMPLE",
            "retrieved_docs":    [],
            "compliance_status": "",
        }

    def test_pass_sets_compliance_status(self):
        with patch.object(_nodes, "_check_compliance", return_value=(True, "PASS")):
            result = check_compliance(self._make_state("BNB offers competitive rates."))
        assert result["compliance_status"] == "PASS"

    def test_pass_does_not_replace_response(self):
        good_response = "BNB offers competitive rates."
        with patch.object(_nodes, "_check_compliance", return_value=(True, "PASS")):
            result = check_compliance(self._make_state(good_response))
        # On PASS, response should not appear in the returned dict
        assert "response" not in result

    def test_fail_sets_compliance_status(self):
        with patch.object(_nodes, "_check_compliance",
                          return_value=(False, "banned phrase: 'guaranteed returns'")):
            result = check_compliance(self._make_state("Guaranteed returns."))
        assert "FAIL" in result["compliance_status"]
        assert "guaranteed returns" in result["compliance_status"]

    def test_fail_replaces_response(self):
        with patch.object(_nodes, "_check_compliance",
                          return_value=(False, "banned phrase: 'risk-free'")):
            result = check_compliance(self._make_state("Risk-free returns."))
        assert result["response"] == SAFE_COMPLIANCE_RESPONSE

    def test_safe_response_mentions_bnb(self):
        with patch.object(_nodes, "_check_compliance",
                          return_value=(False, "hallucinated rate: 9.99% p.a. not in database")):
            result = check_compliance(self._make_state("Rate is 9.99% p.a."))
        assert "BNB" in result["response"]


# ---------------------------------------------------------------------------
# TestBuildGraph
# ---------------------------------------------------------------------------

class TestBuildGraph:
    def test_build_graph_compiles(self):
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph(checkpointer=MemorySaver())
        assert graph is not None

    def test_graph_routes_complex_to_escalation(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content="COMPLEX")
            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "Should I take a loan now?", "response": "",
                 "compliance_status": ""},
                config={"configurable": {"thread_id": "test-s09-complex"}},
            )
        assert "Relationship Manager" in result["response"]
        assert result["query_type"] == "COMPLEX"

    def test_graph_routes_oos_to_decline(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_llm:
            mock_llm.invoke.return_value = MagicMock(content="OUT_OF_SCOPE")
            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "Who won the cricket World Cup?", "response": "",
                 "compliance_status": ""},
                config={"configurable": {"thread_id": "test-s09-oos"}},
            )
        assert "only help with BNB" in result["response"]
        assert result["query_type"] == "OUT_OF_SCOPE"

    def test_graph_simple_runs_check_compliance(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_cls, \
             patch.object(_nodes, "llm_with_tools") as mock_llm, \
             patch.object(_nodes, "_check_compliance", return_value=(True, "PASS")) as mock_cc:
            mock_cls.invoke.return_value = MagicMock(content="SIMPLE")
            mock_llm.invoke.return_value = MagicMock(content="BNB is great.", tool_calls=[])

            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "What products does BNB offer?", "response": "",
                 "compliance_status": ""},
                config={"configurable": {"thread_id": "test-s09-simple"}},
            )

        # check_compliance must have been called (the SIMPLE path runs it)
        mock_cc.assert_called_once()
        assert result["compliance_status"] == "PASS"

    def test_graph_compliance_fail_replaces_response(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_cls, \
             patch.object(_nodes, "llm_with_tools") as mock_llm, \
             patch.object(_nodes, "_check_compliance",
                          return_value=(False, "banned phrase: 'guaranteed returns'")):
            mock_cls.invoke.return_value = MagicMock(content="SIMPLE")
            mock_llm.invoke.return_value = MagicMock(
                content="FD offers guaranteed returns.", tool_calls=[]
            )

            graph = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "Tell me about FDs.", "response": "",
                 "compliance_status": ""},
                config={"configurable": {"thread_id": "test-s09-fail"}},
            )

        assert result["response"] == SAFE_COMPLIANCE_RESPONSE
        assert "FAIL" in result["compliance_status"]
