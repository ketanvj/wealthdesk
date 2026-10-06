"""
s09/tests/test_s09.py
---------------------
Tests for Session 9: Compliance Filter + LangSmith Observability (US-08 + US-10).

Run with:
    pytest s09/tests/ -v

All tests mock the LLM and compliance internals -- no real Groq, LangSmith,
or SQLite calls required.

Test groups:
  TestSebiPhrases        -- each banned phrase triggers FAIL; clean text passes
  TestRateVerification   -- hallucinated rate fails; valid DB rate passes; no rate passes
  TestExtractRates       -- regex helper finds "X.X% p.a." correctly
  TestLoadValidRates     -- DB query returns correct set of floats
  TestCheckComplianceNode -- state in/out; FAIL replaces response; PASS preserves it
  TestBuildGraph         -- graph compiles; check_compliance node present; SIMPLE goes through it
  TestLangSmithSetup     -- env var wiring sets LANGCHAIN_TRACING_V2 when enabled
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SOLUTION_DIR = Path(__file__).parent.parent / "solution"
for _k in list(sys.modules):
    if _k == "wealthdesk" or _k.startswith("wealthdesk."):
        sys.modules.pop(_k)
sys.path.insert(0, str(SOLUTION_DIR))

from wealthdesk.config import SAFE_COMPLIANCE_RESPONSE, SEBI_BANNED_PHRASES  # noqa: E402
from wealthdesk.state import WealthDeskState  # noqa: E402
import wealthdesk.nodes as _nodes  # noqa: E402
from wealthdesk.nodes import (  # noqa: E402
    _check_compliance, _extract_rates, _load_valid_rates,
    check_compliance, decline, escalate,
)
from wealthdesk.agent import build_graph  # noqa: E402


# ---------------------------------------------------------------------------
# TestSebiPhrases
# ---------------------------------------------------------------------------

class TestSebiPhrases:
    def test_guaranteed_returns_fails(self):
        passed, reason = _check_compliance("This FD gives guaranteed returns of 7.1%.")
        assert not passed
        assert "guaranteed returns" in reason

    def test_risk_free_fails(self):
        passed, reason = _check_compliance("This is a completely risk-free investment.")
        assert not passed
        assert "risk-free" in reason

    def test_assured_profit_fails(self):
        passed, reason = _check_compliance("You will get assured profit from this scheme.")
        assert not passed
        assert "assured profit" in reason

    def test_no_risk_fails(self):
        passed, reason = _check_compliance("There is no risk with this product.")
        assert not passed
        assert "no risk" in reason

    def test_phrase_check_is_case_insensitive(self):
        passed, _ = _check_compliance("This gives GUARANTEED RETURNS every year.")
        assert not passed

    def test_phrase_partial_word_not_matched(self):
        passed, _ = _check_compliance("There is minimal risk involved in this product.")
        assert passed

    def test_clean_response_passes(self):
        passed, reason = _check_compliance(
            "The BNB home loan rate is 8.5% p.a. for tenures of 5-30 years.\n\n"
            "WealthDesk | Bharat National Bank"
        )
        assert passed
        assert reason == "PASS"

    def test_fail_reason_contains_phrase(self):
        _, reason = _check_compliance("This investment has no risk at all.")
        assert "no risk" in reason

    def test_all_banned_phrases_present(self):
        assert "guaranteed returns" in SEBI_BANNED_PHRASES
        assert "risk-free"          in SEBI_BANNED_PHRASES
        assert "assured profit"     in SEBI_BANNED_PHRASES
        assert "no risk"            in SEBI_BANNED_PHRASES

    def test_unicode_hyphen_variants_caught(self):
        # LLMs sometimes output non-breaking hyphens (U+2011) or other Unicode
        # dash variants that look identical to ASCII '-' but break string matching.
        # _normalize_for_check() must map them to ASCII '-' before the phrase scan.
        non_breaking = "the returns are not “risk‑free” in the absolute sense"
        en_dash       = "this is a risk–free product"
        passed_nb, reason_nb = _check_compliance(non_breaking)
        passed_en, reason_en = _check_compliance(en_dash)
        assert not passed_nb, f"non-breaking hyphen in 'risk-free' was not caught: {reason_nb}"
        assert not passed_en, f"en-dash in 'risk-free' was not caught: {reason_en}"


# ---------------------------------------------------------------------------
# TestRateVerification
# ---------------------------------------------------------------------------

class TestRateVerification:
    def test_valid_home_loan_rate_passes(self):
        with patch.object(_nodes, "_load_valid_rates", return_value={8.5, 9.5, 12.0, 6.8, 7.1}):
            passed, _ = _check_compliance(
                "The BNB home loan rate is 8.5% p.a. for tenures of 5-30 years."
            )
        assert passed

    def test_hallucinated_rate_fails(self):
        with patch.object(_nodes, "_load_valid_rates", return_value={8.5, 9.5, 12.0, 6.8, 7.1}):
            passed, reason = _check_compliance(
                "The BNB home loan rate is 9.0% p.a."
            )
        assert not passed
        assert "9.0" in reason

    def test_no_rate_in_response_passes(self):
        with patch.object(_nodes, "_load_valid_rates", return_value={8.5, 9.5}):
            passed, _ = _check_compliance(
                "Please visit your nearest BNB branch for more information."
            )
        assert passed

    def test_empty_valid_rates_skips_check(self):
        with patch.object(_nodes, "_load_valid_rates", return_value=set()):
            passed, _ = _check_compliance(
                "The BNB home loan rate is 99.9% p.a."
            )
        assert passed

    def test_valid_fd_rate_passes(self):
        with patch.object(_nodes, "_load_valid_rates", return_value={6.8, 7.1, 7.3, 8.5}):
            passed, _ = _check_compliance(
                "Our 2-year FD earns 7.1% p.a."
            )
        assert passed

    def test_per_annum_spelling_caught(self):
        # LLMs sometimes write "9.99% per annum" instead of "9.99% p.a."
        # Both must be caught by the rate extractor.
        with patch.object(_nodes, "_load_valid_rates", return_value={8.5, 9.5, 7.1}):
            passed, reason = _check_compliance(
                "Home loan rates at BNB start at 9.99% per annum."
            )
        assert not passed
        assert "9.99" in reason

    def test_per_annum_valid_rate_passes(self):
        with patch.object(_nodes, "_load_valid_rates", return_value={8.5, 9.5, 7.1}):
            passed, _ = _check_compliance(
                "The home loan rate is 8.5% per annum."
            )
        assert passed

    def test_multiple_rates_one_invalid_fails(self):
        with patch.object(_nodes, "_load_valid_rates", return_value={8.5, 7.1}):
            passed, reason = _check_compliance(
                "Home loan: 8.5% p.a. FD: 9.9% p.a."
            )
        assert not passed
        assert "9.9" in reason


# ---------------------------------------------------------------------------
# TestExtractRates
# ---------------------------------------------------------------------------

class TestExtractRates:
    def test_extracts_decimal_rate(self):
        assert _extract_rates("rate is 8.5% p.a.") == [8.5]

    def test_extracts_integer_rate(self):
        assert _extract_rates("rate is 12% p.a.") == [12.0]

    def test_extracts_multiple_rates(self):
        rates = _extract_rates("home loan 8.5% p.a. and FD 7.1% p.a.")
        assert 8.5 in rates
        assert 7.1 in rates

    def test_ignores_percentage_without_pa(self):
        assert _extract_rates("80% loan-to-value ratio") == []

    def test_case_insensitive_pa(self):
        assert _extract_rates("rate is 8.5% P.A.") == [8.5]

    def test_empty_string_returns_empty(self):
        assert _extract_rates("") == []

    def test_no_rate_returns_empty(self):
        assert _extract_rates("Please visit your nearest branch.") == []


# ---------------------------------------------------------------------------
# TestLoadValidRates
# ---------------------------------------------------------------------------

class TestLoadValidRates:
    def test_returns_set(self):
        result = _load_valid_rates()
        assert isinstance(result, set)

    def test_contains_home_loan_rate(self):
        result = _load_valid_rates()
        assert 8.5 in result

    def test_contains_personal_loan_rate(self):
        result = _load_valid_rates()
        assert 12.0 in result

    def test_contains_fd_base_rate(self):
        result = _load_valid_rates()
        assert 7.1 in result

    def test_contains_senior_fd_rate(self):
        result = _load_valid_rates()
        assert 7.6 in result  # 7.1 + 0.5 senior rate

    def test_returns_empty_set_on_bad_path(self):
        with patch.object(_nodes, "DB_PATH", Path("/nonexistent/path/db.sqlite")):
            result = _load_valid_rates()
        assert result == set()

    def test_all_loan_rates_present(self):
        result = _load_valid_rates()
        for rate in [8.5, 12.0, 9.5, 10.5, 11.0]:
            assert rate in result, f"{rate} missing from valid rates"


# ---------------------------------------------------------------------------
# TestCheckComplianceNode
# ---------------------------------------------------------------------------

class TestCheckComplianceNode:
    def _make_state(self, response: str, query_type: str = "SIMPLE") -> WealthDeskState:
        return {
            "customer_message":  "test",
            "response":          response,
            "history":           [],
            "query_type":        query_type,
            "retrieved_docs":    [],
            "compliance_status": "",
        }

    def test_fail_replaces_response(self):
        with patch.object(_nodes, "_check_compliance", return_value=(False, "banned phrase: 'risk-free'")):
            result = check_compliance(self._make_state("This is risk-free."))
        assert result["response"] == SAFE_COMPLIANCE_RESPONSE

    def test_fail_sets_compliance_status(self):
        with patch.object(_nodes, "_check_compliance", return_value=(False, "banned phrase: 'risk-free'")):
            result = check_compliance(self._make_state("This is risk-free."))
        assert "FAIL" in result["compliance_status"]
        assert "risk-free" in result["compliance_status"]

    def test_pass_preserves_response(self):
        original = "The home loan rate is 8.5% p.a.\n\nWealthDesk | Bharat National Bank"
        with patch.object(_nodes, "_check_compliance", return_value=(True, "PASS")):
            result = check_compliance(self._make_state(original))
        assert result.get("response") is None or result.get("response") == original

    def test_pass_sets_compliance_status(self):
        with patch.object(_nodes, "_check_compliance", return_value=(True, "PASS")):
            result = check_compliance(self._make_state("Clean response."))
        assert result["compliance_status"] == "PASS"

    def test_returns_dict(self):
        with patch.object(_nodes, "_check_compliance", return_value=(True, "PASS")):
            result = check_compliance(self._make_state("Clean."))
        assert isinstance(result, dict)

    def test_safe_response_contains_bnb(self):
        assert "BNB" in SAFE_COMPLIANCE_RESPONSE

    def test_safe_response_has_sign_off(self):
        assert "WealthDesk | Bharat National Bank" in SAFE_COMPLIANCE_RESPONSE


# ---------------------------------------------------------------------------
# TestBuildGraph
# ---------------------------------------------------------------------------

class TestBuildGraph:
    def test_build_graph_returns_compiled_graph(self):
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph(checkpointer=MemorySaver())
        assert graph is not None

    def test_check_compliance_node_in_graph(self):
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph(checkpointer=MemorySaver())
        assert "check_compliance" in graph.get_graph().nodes

    def test_respond_edges_to_check_compliance(self):
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph(checkpointer=MemorySaver())
        edges = graph.builder.edges
        assert ("respond", "check_compliance") in edges

    def test_escalate_does_not_go_through_compliance(self):
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph(checkpointer=MemorySaver())
        edges = graph.builder.edges
        edge_targets_from_escalate = [t for (s, t) in edges if s == "escalate"]
        assert "check_compliance" not in edge_targets_from_escalate

    def test_decline_does_not_go_through_compliance(self):
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph(checkpointer=MemorySaver())
        edges = graph.builder.edges
        edge_targets_from_decline = [t for (s, t) in edges if s == "decline"]
        assert "check_compliance" not in edge_targets_from_decline

    def test_graph_invoke_simple_includes_compliance_status(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_clf, \
             patch.object(_nodes, "_check_compliance", return_value=(True, "PASS")), \
             patch.object(_nodes, "llm_with_tools") as mock_llm:
            mock_clf.invoke.return_value = MagicMock(content="SIMPLE")
            mock_llm.invoke.return_value = MagicMock(
                content="Clean answer.", tool_calls=[]
            )
            graph  = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "What is the home loan rate?",
                 "response": "", "compliance_status": ""},
                config={"configurable": {"thread_id": "test-compliance-001"}},
            )
        assert "compliance_status" in result
        assert result["compliance_status"] == "PASS"

    def test_graph_invoke_complex_skips_compliance(self):
        from langgraph.checkpoint.memory import MemorySaver

        with patch.object(_nodes, "classifier_llm") as mock_clf:
            mock_clf.invoke.return_value = MagicMock(content="COMPLEX")
            graph  = build_graph(checkpointer=MemorySaver())
            result = graph.invoke(
                {"customer_message": "Should I invest?",
                 "response": "", "compliance_status": ""},
                config={"configurable": {"thread_id": "test-complex-001"}},
            )
        assert "Relationship Manager" in result["response"]
        assert result.get("compliance_status", "") == ""


# ---------------------------------------------------------------------------
# TestLangSmithSetup
# ---------------------------------------------------------------------------

class TestLangSmithSetup:
    def test_langchain_tracing_set_when_enabled(self):
        import importlib
        import os
        env_backup = {
            "LANGSMITH_API_KEY":      os.environ.get("LANGSMITH_API_KEY"),
            "LANGSMITH_TRACING":      os.environ.get("LANGSMITH_TRACING"),
            "LANGSMITH_PROJECT":      os.environ.get("LANGSMITH_PROJECT"),
            "LANGCHAIN_TRACING_V2":   os.environ.get("LANGCHAIN_TRACING_V2"),
            "LANGCHAIN_API_KEY":      os.environ.get("LANGCHAIN_API_KEY"),
            "LANGCHAIN_PROJECT":      os.environ.get("LANGCHAIN_PROJECT"),
        }
        try:
            os.environ["LANGSMITH_API_KEY"]    = "test-ls-key"
            os.environ["LANGSMITH_TRACING"]    = "true"
            os.environ["LANGSMITH_PROJECT"]    = "test-project"
            os.environ.pop("LANGCHAIN_TRACING_V2", None)
            os.environ.pop("LANGCHAIN_API_KEY",    None)
            os.environ.pop("LANGCHAIN_PROJECT",    None)

            for k in list(sys.modules):
                if k == "wealthdesk" or k.startswith("wealthdesk."):
                    sys.modules.pop(k)
            # Ensure THIS session's solution dir is first so multi-session
            # runs don't pick up another session's wealthdesk/__init__.py
            sys.path.insert(0, str(SOLUTION_DIR))
            importlib.invalidate_caches()
            import wealthdesk as _fresh  # noqa: F401

            assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
        finally:
            for k, v in env_backup.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            for k in list(sys.modules):
                if k == "wealthdesk" or k.startswith("wealthdesk."):
                    sys.modules.pop(k)
            if str(SOLUTION_DIR) in sys.path and sys.path.index(str(SOLUTION_DIR)) == 0:
                sys.path.pop(0)

    def test_tracing_not_set_without_api_key(self):
        import importlib
        import os
        env_backup = {k: os.environ.get(k) for k in
                      ["LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"]}
        try:
            os.environ.pop("LANGSMITH_API_KEY",    None)
            os.environ.pop("LANGCHAIN_TRACING_V2", None)

            for k in list(sys.modules):
                if k == "wealthdesk" or k.startswith("wealthdesk."):
                    sys.modules.pop(k)
            sys.path.insert(0, str(SOLUTION_DIR))
            importlib.invalidate_caches()
            with patch("dotenv.load_dotenv"):  # prevent .env from restoring the key
                import wealthdesk as _fresh  # noqa: F401

            assert os.environ.get("LANGCHAIN_TRACING_V2") != "true"
        finally:
            for k, v in env_backup.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            for k in list(sys.modules):
                if k == "wealthdesk" or k.startswith("wealthdesk."):
                    sys.modules.pop(k)
            if str(SOLUTION_DIR) in sys.path and sys.path.index(str(SOLUTION_DIR)) == 0:
                sys.path.pop(0)
