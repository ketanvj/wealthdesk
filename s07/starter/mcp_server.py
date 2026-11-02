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
  - New file: s07/starter/mcp_server.py (this file)
  - query_rates and query_branch from s05 are moved here as @mcp.tool()
    functions. Same SQL queries, same return format, different decorator.
  - Agent code (s05/s06) is not touched -- evaluation still imports from s05

Why MCP (the one-sentence version)
  Direct tool binding (s05 pattern) couples tools to the agent file.
  MCP decouples them: the server runs independently, any MCP-compatible
  agent can call it, and tools can be tested and versioned separately.

Run the server
  python s07/starter/mcp_server.py
  (Server starts and waits on stdin for MCP messages -- use Inspector to send them)

Inspect with MCP Inspector
  npx @modelcontextprotocol/inspector python s07/starter/mcp_server.py
  Then open the URL printed in the terminal (includes ?MCP_INSPECTOR_API_TOKEN=...).
"""

import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server instantiation
# ---------------------------------------------------------------------------

# FastMCP handles all the MCP protocol machinery (tool registration, schema
# generation, JSON-RPC message handling). You only write the business logic.
# The string here is the server name visible to MCP clients like the Inspector.
mcp = FastMCP("wealthdesk-tools")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH  = DATA_DIR / "bnb_data.db"

# ---------------------------------------------------------------------------
# TODO 1 of 2 -- implement query_rates()
# ---------------------------------------------------------------------------
# Copy the query_rates() function body from s05/solution/wealthdesk/tools.py.
# Change @tool to @mcp.tool() -- that is the only required change.
# The SQL queries and return format are identical.
#
# The function should:
#   1. Accept product_type: str = "all" (same signature)
#   2. Connect to DB_PATH with check_same_thread=False
#   3. If product_type in ("loan", "all"): query loan_products table
#      SELECT name, interest_rate, tenure_min_years, tenure_max_years
#      FROM loan_products ORDER BY interest_rate
#      Format each row as: "{name}: {rate:.1f}% p.a., tenure {min_y}-{max_y} years"
#   4. If product_type in ("fd", "all"): query fd_products table
#      SELECT tenure_label, interest_rate, senior_rate
#      FROM fd_products ORDER BY tenure_months
#      Format each row as: "FD {label}: {rate:.1f}% p.a. (senior citizens: {rate+senior:.1f}%)"
#   5. Close the connection and return "\n".join(lines) or "No rate data found."
#
# WHY @mcp.tool() instead of @tool?
#   @tool (from langchain_core) makes a LangChain StructuredTool. It is
#   consumed by llm.bind_tools() inside the agent.
#   @mcp.tool() makes an MCP Tool. FastMCP generates the JSON Schema from
#   type hints and serves it via the MCP protocol -- any MCP client discovers
#   and calls it, not just this agent.
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
    # TODO 1: implement the function body
    # Copy the SQL logic from s05/solution/wealthdesk/tools.py
    raise NotImplementedError("TODO 1: implement query_rates() in mcp_server.py")


# ---------------------------------------------------------------------------
# TODO 2 of 2 -- implement query_branch()
# ---------------------------------------------------------------------------
# Copy the query_branch() function body from s05/solution/wealthdesk/tools.py.
# Change @tool to @mcp.tool() -- that is the only required change.
#
# The function should:
#   1. Accept city: str = "all" (same signature)
#   2. Connect to DB_PATH with check_same_thread=False
#   3. If city == "all": SELECT all branches ORDER BY city, name
#      Otherwise: SELECT branches WHERE city LIKE ? (parameterised -- keep the ?)
#      If no rows found by city, retry by branch name (WHERE name LIKE ?)
#   4. Format each row as a multi-line block:
#        "{name} ({city_})\n  Address: {address}\n  IFSC: {ifsc}  |  Phone: {phone}"
#   5. Return "\n\n".join(parts) or "No BNB branches found for city: '{city}'."
#
# WHY keep the parameterised query (? placeholder)?
#   The ? placeholder prevents SQL injection -- the value is passed separately
#   and the database driver escapes it before it reaches the SQL engine.
#   Replacing ? with an f-string (f"WHERE city LIKE '%{city}%'") would allow
#   an attacker to inject arbitrary SQL by passing city = "' OR 1=1--".
#   S14 (Security) will revisit this in detail.
# ---------------------------------------------------------------------------

@mcp.tool()
def query_branch(city: str = "all") -> str:
    """Fetch BNB branch locations from the database.

    Args:
        city: Filter branches by city name. Examples: "Bengaluru", "Mumbai",
              "Chennai", "Hyderabad", "Delhi". Use "all" for every branch.

    Returns branch names, addresses, IFSC codes, and phone numbers.
    """
    # TODO 2: implement the function body
    # Copy the SQL logic from s05/solution/wealthdesk/tools.py
    # Keep the parameterised query (? placeholder) -- do not replace with f-string
    raise NotImplementedError("TODO 2: implement query_branch() in mcp_server.py")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # mcp.run() starts the server with STDIO transport.
    # No port or HTTP -- the MCP Inspector (and the agent in S08) starts this
    # file as a subprocess and communicates over stdin/stdout.
    mcp.run()  # STDIO transport by default
