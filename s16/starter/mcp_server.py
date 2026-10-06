"""
WealthDesk -- Session 16: MCP Server over SSE (US-06 Part 3)
=============================================================

What you change this session
  The two BNB database tools are identical to S07/S15.
  The ONLY change is the transport: stdio → SSE.

  SSE turns the MCP server into a persistent HTTP service that any client
  can connect to without spawning a subprocess.

Why SSE over stdio
  stdio       SSE
  ──────────  ─────────────────────────────────────────────────
  New process per agent startup   One persistent server process
  Slower cold start               Instant tool calls once server is up
  Single caller at a time         Multiple agents can share the same server
  No auth layer needed            Can add API keys, TLS, load balancer

Your task
  1. The tools below (query_rates, query_branch) are complete — don't change them.
  2. At the bottom, fill in the TODO to start the server with SSE transport.

Run this server (once working)
  python mcp_server.py
  Expected: [WealthDesk MCP] Starting SSE server on http://0.0.0.0:8001/sse

Inspect with MCP Inspector
  npx @modelcontextprotocol/inspector
  Transport: SSE  |  URL: http://localhost:8001/sse
"""

import os
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server instantiation
# ---------------------------------------------------------------------------

mcp = FastMCP("wealthdesk-tools")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"  # shared wealthdesk/data/
DB_PATH  = DATA_DIR / "bnb_data.db"

MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8001"))

# ---------------------------------------------------------------------------
# MCP Tools (identical to s07 -- only the transport changes)
# ---------------------------------------------------------------------------

@mcp.tool()
def query_rates(product_type: str = "all") -> str:
    """Fetch current BNB interest rates from the database.

    Args:
        product_type: Which rates to return. Options:
            "loan" -- all loan products (home, personal, car, education, gold)
            "fd"   -- all fixed deposit products
            "all"  -- both loans and FDs (default)

    Returns formatted rate information as a plain-text string.
    """
    conn  = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    lines = []

    if product_type in ("loan", "all"):
        rows = conn.execute(
            "SELECT name, interest_rate, tenure_min_years, tenure_max_years "
            "FROM loan_products ORDER BY interest_rate"
        ).fetchall()
        for name, rate, min_y, max_y in rows:
            lines.append(
                f"{name}: {rate:.1f}% p.a., tenure {min_y}-{max_y} years"
            )

    if product_type in ("fd", "all"):
        rows = conn.execute(
            "SELECT tenure_label, interest_rate, senior_rate "
            "FROM fd_products ORDER BY tenure_months"
        ).fetchall()
        for label, rate, senior in rows:
            lines.append(
                f"FD {label}: {rate:.1f}% p.a. "
                f"(senior citizens: {rate + senior:.1f}%)"
            )

    conn.close()
    return "\n".join(lines) if lines else "No rate data found."


@mcp.tool()
def query_branch(city: str = "all") -> str:
    """Fetch BNB branch locations from the database.

    Args:
        city: Filter branches by city name. Examples: "Bengaluru", "Mumbai",
              "Chennai", "Hyderabad", "Delhi". Use "all" for every branch.

    Returns branch names, addresses, IFSC codes, and phone numbers.
    """
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)

    if city.lower() == "all":
        rows = conn.execute(
            "SELECT name, city, address, ifsc, phone "
            "FROM branches ORDER BY city, name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name, city, address, ifsc, phone "
            "FROM branches WHERE city LIKE ? ORDER BY name",
            (f"%{city}%",),
        ).fetchall()

    conn.close()

    if not rows:
        return f"No BNB branches found for city: '{city}'."

    parts = []
    for name, city_, address, ifsc, phone in rows:
        parts.append(
            f"{name} ({city_})\n"
            f"  Address: {address}\n"
            f"  IFSC: {ifsc}  |  Phone: {phone}"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# TODO 1: Start the MCP server with SSE transport
# ---------------------------------------------------------------------------
# Replace the stdio startup below with SSE transport.
# Hint: mcp.settings.host = MCP_HOST; mcp.settings.port = MCP_PORT; mcp.run(transport="sse")

if __name__ == "__main__":
    print(f"[WealthDesk MCP] Starting SSE server on http://{MCP_HOST}:{MCP_PORT}/sse")
    # TODO: mcp.run(transport=???, host=???, port=???)
    raise NotImplementedError("Replace this line with mcp.run(...)")
