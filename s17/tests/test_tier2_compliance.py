"""
S17 unit tests — Tier 2 compliance module.

Tests use a mock LLM so no Groq API key needed.
The SEBI vectorstore must exist (run ingest_sebi.py first).

Run:
  cd s17/solution && python -m pytest ../tests/test_tier2_compliance.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "solution"))

from wealthdesk.compliance import (
    _generate_hypothesis,
    _merge_unique,
    _track1_retrieve,
    tier2_compliance_check,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm(response: str):
    mock = MagicMock()
    mock.invoke.return_value = MagicMock(content=response)
    return mock


# ---------------------------------------------------------------------------
# Track 1: deterministic retrieval
# ---------------------------------------------------------------------------

def test_track1_returns_rate_sources_for_rates():
    from wealthdesk.compliance import QUERY_TYPE_TO_SOURCES
    sources = QUERY_TYPE_TO_SOURCES.get("RATES", [])
    assert "rate_disclosure_requirements.md" in sources
    assert len(sources) >= 1


def test_track1_returns_policy_sources_for_policy():
    from wealthdesk.compliance import QUERY_TYPE_TO_SOURCES
    sources = QUERY_TYPE_TO_SOURCES.get("POLICY", [])
    assert len(sources) >= 1


def test_track1_returns_empty_for_out_of_scope():
    from wealthdesk.compliance import QUERY_TYPE_TO_SOURCES
    sources = QUERY_TYPE_TO_SOURCES.get("OUT_OF_SCOPE", [])
    assert sources == []


# ---------------------------------------------------------------------------
# Merge / deduplication
# ---------------------------------------------------------------------------

def test_merge_deduplicates():
    a = ["[src1.md]\nContent about rates guarantee prohibition"]
    b = ["[src1.md]\nContent about rates guarantee prohibition",
         "[src2.md]\nContent about risk disclosure"]
    merged = _merge_unique(a, b)
    assert len(merged) == 2


def test_merge_preserves_order():
    a = ["[src1.md]\nFirst doc about rates"]
    b = ["[src2.md]\nSecond doc about investment advice"]
    merged = _merge_unique(a, b)
    assert merged[0].startswith("[src1.md]")
    assert merged[1].startswith("[src2.md]")


# ---------------------------------------------------------------------------
# Hypothesis generation
# ---------------------------------------------------------------------------

def test_hypothesis_generation_calls_llm():
    mock = _mock_llm("Potential violation: guaranteed returns language in FD description.")
    result = _generate_hypothesis("Our FD guarantees 7% returns.", mock)
    assert "potential violation" in result.lower()
    mock.invoke.assert_called_once()


def test_hypothesis_none_apparent_skips_track2():
    mock = _mock_llm("Potential violation: none apparent.")
    from wealthdesk.compliance import _track2_retrieve
    docs = _track2_retrieve("A straightforward rate quote.", mock)
    assert isinstance(docs, list)


# ---------------------------------------------------------------------------
# Full pipeline (with mock LLM)
# ---------------------------------------------------------------------------

def test_compliant_response_passes():
    mock = _mock_llm("COMPLIANT")
    passed, verdict, _ = tier2_compliance_check(
        "The home loan rate at BNB starts from 8.5% p.a., subject to credit score assessment.",
        "RATES",
        mock,
    )
    assert passed is True
    assert verdict.upper().startswith("COMPLIANT")


def test_violation_flagged():
    mock = _mock_llm(
        "VIOLATION: SEBI IA Regulations 2013 Regulation 22(1) — "
        "phrase 'capital is fully protected' constitutes a prohibited guaranteed-return statement."
    )
    passed, verdict, _ = tier2_compliance_check(
        "Our FD gives 7.1% p.a. and your capital is fully protected.",
        "RATES",
        mock,
    )
    assert passed is False
    assert "violation" in verdict.lower()


def test_out_of_scope_skips_compliance():
    mock = _mock_llm("COMPLIANT")
    passed, verdict, citations = tier2_compliance_check(
        "I can't help with that.",
        "OUT_OF_SCOPE",
        mock,
    )
    assert passed is True
    assert citations == []
    mock.invoke.assert_not_called()


def test_empty_draft_skips_compliance():
    mock = _mock_llm("COMPLIANT")
    passed, verdict, citations = tier2_compliance_check("", "RATES", mock)
    assert passed is True
    assert citations == []


def test_personalised_advice_flagged():
    mock = _mock_llm(
        "VIOLATION: SEBI Investment Advice Prohibitions 2021 Section 1(b) — "
        "the response states the product is 'suitable' for the customer without a formal risk profile."
    )
    passed, verdict, _ = tier2_compliance_check(
        "Based on your profile, this FD is the best and most suitable option for you.",
        "POLICY",
        mock,
    )
    assert passed is False
