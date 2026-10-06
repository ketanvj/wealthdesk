"""
S16 API tests — verifies the FastAPI backend works end-to-end.

Prerequisites
  1. python mcp_server.py   (terminal 1, port 8001)
  2. uvicorn main:app       (terminal 2, port 8000)
  3. cd s16/solution && python -m pytest ../tests/test_s16.py -v

These tests hit the live API (no mocks).
The MCP server and FastAPI server must both be running.
"""

import sys
import time
from pathlib import Path

import httpx
import pytest

BASE_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def post_chat(message: str, thread_id: str = "test-default") -> dict:
    resp = httpx.post(
        f"{BASE_URL}/chat",
        json={"message": message, "thread_id": thread_id},
        timeout=60,
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health():
    resp = httpx.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["graph"] == "ready"


def test_rates_query():
    data = post_chat("What are the home loan interest rates at BNB?", "test-rates")
    assert data["response"], "Empty response"
    assert data["specialist"] in ("rates_agent", "plans_agent"), (
        f"Unexpected specialist: {data['specialist']}"
    )
    resp_lower = data["response"].lower()
    assert any(kw in resp_lower for kw in ("rate", "%", "loan")), (
        f"Response doesn't mention rates: {data['response'][:200]}"
    )


def test_branch_query():
    time.sleep(3)
    data = post_chat("Where is the BNB branch in Mumbai?", "test-branch")
    assert data["response"], "Empty response"
    resp_lower = data["response"].lower()
    assert any(kw in resp_lower for kw in ("mumbai", "branch", "address")), (
        f"Response doesn't mention branch info: {data['response'][:200]}"
    )


def test_fd_rates():
    time.sleep(3)
    data = post_chat("What are the FD rates for senior citizens?", "test-fd")
    assert data["response"]
    resp_lower = data["response"].lower()
    assert any(kw in resp_lower for kw in ("fd", "fixed", "senior", "%")), (
        f"FD rates not in response: {data['response'][:200]}"
    )


def test_escalation():
    time.sleep(3)
    data = post_chat(
        "I lost my job and have a home loan EMI due. What should I do?",
        "test-escalate"
    )
    assert data["response"]
    assert data["specialist"] in ("escalated", "human_agent"), (
        f"Expected escalation, got: {data['specialist']}"
    )


def test_decline():
    time.sleep(3)
    data = post_chat("Who won the cricket World Cup?", "test-decline")
    assert data["response"]
    assert data["specialist"] in ("declined", "decline_agent"), (
        f"Expected decline, got: {data['specialist']}"
    )


def test_pii_blocked():
    time.sleep(3)
    data = post_chat(
        "My Aadhaar is 2345 6789 0123. Can I open an account?",
        "test-pii"
    )
    assert data["response"]
    assert data["blocked_reason"], (
        f"PII not blocked. Response: {data['response'][:200]}"
    )


def test_empty_message_rejected():
    resp = httpx.post(
        f"{BASE_URL}/chat",
        json={"message": "", "thread_id": "test-empty"},
        timeout=10,
    )
    assert resp.status_code == 400, (
        f"Expected 400 for empty message, got {resp.status_code}"
    )


def test_frontend_served():
    resp = httpx.get(f"{BASE_URL}/", timeout=5)
    assert resp.status_code == 200
    assert "WealthDesk" in resp.text, "Frontend page doesn't contain 'WealthDesk'"


def test_compliance_status_present():
    time.sleep(3)
    data = post_chat("What is the savings account rate at BNB?", "test-compliance")
    assert data["response"]
    assert "compliance_status" in data
