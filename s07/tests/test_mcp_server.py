"""
Tests for the S07 WealthDesk MCP server.

Run from wealthdesk/:
    pytest s07/tests/ -v

Tests cover:
  - Tool registration (FastMCP discovers both tools)
  - Correct data returned by query_rates and query_branch
  - SQL injection prevention in query_branch
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Add the solution directory to the path so tests run against the full implementation.
# Remove this line and replace "solution" with "starter" to test the starter after
# completing the TODOs.
sys.path.insert(0, str(Path(__file__).parent.parent / "solution"))

from mcp_server import mcp, query_rates, query_branch


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def test_server_has_two_tools():
    """FastMCP should register exactly query_rates and query_branch."""
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"query_rates", "query_branch"}, (
        f"Expected {{query_rates, query_branch}} but got {names}"
    )


def test_tool_names_match_functions():
    """Tool names should match the Python function names (FastMCP default)."""
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert "query_rates"  in names
    assert "query_branch" in names


# ---------------------------------------------------------------------------
# query_rates
# ---------------------------------------------------------------------------

def test_home_loan_rate_is_8_5():
    """Home loan rate should be 8.5% as seeded in bnb_data.db."""
    result = query_rates("loan")
    assert "8.5" in result, f"Expected 8.5% home loan rate in: {result}"


def test_personal_loan_rate_is_12():
    """Personal loan rate should be 12.0% as seeded."""
    result = query_rates("loan")
    assert "12.0" in result or "12%" in result, f"Expected 12% personal loan rate in: {result}"


def test_all_five_loan_products_returned():
    """query_rates('loan') should return all 5 loan products."""
    result = query_rates("loan")
    for product in ("Home Loan", "Personal Loan", "Car Loan", "Education Loan", "Gold Loan"):
        assert product in result, f"Missing product '{product}' in: {result}"


def test_fd_rates_returned():
    """query_rates('fd') should return FD products without loan data."""
    result = query_rates("fd")
    assert "FD" in result
    # Loan products should not appear in FD-only query
    assert "Home Loan" not in result


def test_query_rates_all_includes_both():
    """query_rates('all') should include both loan and FD products."""
    result = query_rates("all")
    assert "Home Loan" in result
    assert "FD" in result


def test_query_rates_default_is_all():
    """query_rates() with no argument should behave like query_rates('all')."""
    result_default = query_rates()
    result_all     = query_rates("all")
    assert result_default == result_all


# ---------------------------------------------------------------------------
# query_branch
# ---------------------------------------------------------------------------

def test_bengaluru_branches_returned():
    """Bengaluru query should return Indiranagar and Koramangala branches."""
    result = query_branch("Bengaluru")
    assert "Indiranagar" in result or "Koramangala" in result, (
        f"Expected Bengaluru branches in: {result}"
    )


def test_mumbai_branch_andheri_returned():
    """Mumbai query should include Andheri West branch."""
    result = query_branch("Mumbai")
    assert "Andheri" in result, f"Expected Andheri in Mumbai result: {result}"


def test_branch_ifsc_included():
    """Branch result should include the IFSC code."""
    result = query_branch("Bengaluru")
    assert "BNBI" in result, f"Expected IFSC code in: {result}"


def test_unknown_city_returns_not_found():
    """Querying a non-existent city should return a 'not found' message, not crash."""
    result = query_branch("Atlantis")
    assert "No BNB branches found" in result


def test_query_branch_all_returns_multiple_cities():
    """query_branch('all') should return branches from multiple cities."""
    result = query_branch("all")
    assert "Mumbai"   in result
    assert "Bengaluru" in result
    assert "Delhi"    in result


# ---------------------------------------------------------------------------
# SQL injection prevention
# ---------------------------------------------------------------------------

def test_branch_city_injection_does_not_crash():
    """SQL injection in city parameter should not crash the server."""
    # Parameterised query prevents injection -- the value is escaped by SQLite.
    result = query_branch("' OR 1=1--")
    # Should return no rows, not all rows (which would indicate injection succeeded)
    assert isinstance(result, str)


def test_branch_city_injection_does_not_return_all_rows():
    """SQL injection attempt should not bypass the city filter."""
    result = query_branch("' OR 1=1--")
    # If injection succeeded, all branches (including Mumbai) would appear.
    # The parameterised query treats the whole string as a literal city name,
    # so no rows match and we get the "not found" message.
    assert "Mumbai" not in result, (
        "SQL injection succeeded -- parameterised query may be broken"
    )


def test_branch_city_union_injection():
    """UNION-based SQL injection should be treated as a literal city name."""
    result = query_branch("x' UNION SELECT name,city,address,ifsc,phone FROM branches--")
    assert "Mumbai" not in result


def test_branch_city_injection_does_not_drop_table():
    """After an injection attempt, the branches table must still contain data."""
    # Attempt a DROP TABLE via the city parameter — parameterised query keeps it harmless.
    query_branch("Mumbai'; DROP TABLE branches;--")
    # If the injection succeeded, this call would raise OperationalError (no such table).
    result = query_branch("Mumbai")
    assert "Andheri" in result, "branches table was dropped — parameterised query may be broken"
