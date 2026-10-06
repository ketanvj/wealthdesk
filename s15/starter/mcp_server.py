"""
WealthDesk -- Session 7: MCP Server (US-06 Part 1)
===================================================

What you build this session
  WealthDesk's two database tools -- query_rates and query_branch --
  are reimplemented as MCP (Model Context Protocol) tools in a standalone
  server. MCP Inspector can discover and invoke them independently of any
  agent code.

  Session 8 connects the WealthDesk agent to this server. This session
  is about the server only -- the s05 agent is not changed.

What changed from Session 6
  - New file: s07/solution/mcp_server.py (this file)
  - query_rates and query_branch from s05 are moved here as @mcp.tool()
    functions. Same SQL queries, same return format, different decorator.
  - mcp>=1.0.0 is already in requirements.txt (added ahead of time)
  - Agent code (s05/s06) is not touched -- evaluation still imports from s05

Why MCP (the one-sentence version)
  Direct tool binding (s05 pattern) couples tools to the agent file.
  MCP decouples them: the server runs independently, any MCP-compatible
  agent can call it, and tools can be tested and versioned separately.

Run the server
  python s07/solution/mcp_server.py
  (Server starts and waits on stdin for MCP messages -- use Inspector to send them)

Inspect with MCP Inspector
  npx @modelcontextprotocol/inspector python s07/solution/mcp_server.py
  Then open http://localhost:5173 in a browser.
"""

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

DATA_DIR = Path(__file__).parent / "data"
DB_PATH  = DATA_DIR / "bnb_data.db"

# ---------------------------------------------------------------------------
# MCP Tools
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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()  # STDIO transport by default
