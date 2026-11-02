"""
wealthdesk/tools.py
-------------------
Tool definitions and LLM setup for WealthDesk.

Session 5 adds two @tool functions that give the LLM live access to the
BNB database. Instead of relying only on RAG policy chunks (Session 4),
the LLM can now call query_rates() and query_branch() to get exact data.

New this session:
  query_rates()   -- fetches current loan and FD interest rates from the DB
  query_branch()  -- fetches BNB branch locations and contact details
  TOOLS           -- list of available tools (used by both bind_tools and _run_tool)
  llm_with_tools  -- the respond LLM with tools bound
  _run_tool()     -- helper that executes whichever tool the LLM requested

Carries forward from Session 4:
  llm             -- still used internally; llm_with_tools wraps it
  classifier_llm  -- unchanged: classifier does not use tools
"""
import os
import sqlite3

# langchain_core.tools is a submodule that ships several tool-related utilities:
#   tool            -- decorator used here: wraps a plain function into a LangChain Tool object
#   BaseTool        -- base class all tools inherit from (used internally by @tool)
#   StructuredTool  -- explicit alternative to @tool when you need more control
#   InjectedToolArg -- marks arguments the system fills in, not the LLM
# We only import `tool` because the @tool decorator handles everything automatically.
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from .config import DB_PATH, MODEL_NAME, CLASSIFIER_MODEL, TEMPERATURE, MAX_TOKENS, CLASSIFIER_TEMPERATURE, CLASSIFIER_MAX_TOKENS

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY not found.\n"
        "Did you copy .env.example to .env and fill in your key?\n"
        "  Windows:  copy .env.example .env\n"
        "  Mac/Linux: cp .env.example .env"
    )

llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=MODEL_NAME,
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
)

classifier_llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=CLASSIFIER_MODEL,
    temperature=CLASSIFIER_TEMPERATURE,
    max_tokens=CLASSIFIER_MAX_TOKENS,
    reasoning_effort="low",
)


# ---------------------------------------------------------------------------
# TODO 1 of 4 -- implement query_rates()
# ---------------------------------------------------------------------------
# query_rates() fetches current BNB interest rates from the SQLite database.
#
# Decorate with @tool and give it a clear docstring -- the docstring becomes
# the tool's description in the JSON schema sent to the LLM. The LLM reads
# it to decide when and how to call the tool. Poor docstrings = wrong calls.
#
# Steps:
#
#   1. Decorate with @tool:
#        @tool
#        def query_rates(product_type: str = "all") -> str:
#
#   2. Write a descriptive docstring explaining:
#        - what the function does (fetch BNB interest rates)
#        - what product_type accepts: "loan", "fd", or "all"
#        - what the return value looks like
#
#   3. Open a SQLite connection (use check_same_thread=False):
#        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
#        lines = []
#
#   4. Query loan products when product_type is "loan" or "all":
#        if product_type in ("loan", "all"):
#            rows = conn.execute(
#                "SELECT name, interest_rate, tenure_min_years, tenure_max_years "
#                "FROM loan_products ORDER BY interest_rate"
#            ).fetchall()
#            for name, rate, min_y, max_y in rows:
#                lines.append(f"{name}: {rate:.2f}% p.a., tenure {min_y}-{max_y} years")
#
#   5. Query FD products when product_type is "fd" or "all":
#        if product_type in ("fd", "all"):
#            rows = conn.execute(
#                "SELECT tenure_label, interest_rate, senior_rate "
#                "FROM fd_products ORDER BY tenure_months"
#            ).fetchall()
#            for label, rate, senior in rows:
#                lines.append(
#                    f"FD {label}: {rate:.2f}% p.a. "
#                    f"(senior citizens: {rate + senior:.2f}%, extra +{senior:.2f}%)"
#                )
#
#   6. Close the connection and return the result:
#        conn.close()
#        return "\n".join(lines) if lines else "No rate data found."
#
# WHY check_same_thread=False?
# SQLite raises ProgrammingError if a connection is used from a different thread
# than the one that created it. LangGraph runs tool calls in a thread-pool
# executor, so the tool may run on a different thread than the one that opened
# the connection. This flag disables that check.
# ---------------------------------------------------------------------------

# TODO 1: implement query_rates() below -- keep the @tool decorator and docstring
raise NotImplementedError("TODO 1: implement query_rates() in wealthdesk/tools.py")


# ---------------------------------------------------------------------------
# TODO 2 of 4 -- implement query_branch()
# ---------------------------------------------------------------------------
# query_branch() fetches BNB branch locations from the SQLite database.
#
# Steps:
#
#   1. Decorate with @tool:
#        @tool
#        def query_branch(city: str = "all") -> str:
#
#   2. Write a descriptive docstring explaining:
#        - what the function does (fetch branch info)
#        - what city accepts: any city name or "all"
#        - what the return value looks like
#
#   3. Open connection (check_same_thread=False):
#        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
#
#   4. Fetch branches:
#      - If city == "all": SELECT all branches
#      - Otherwise: filter by city column first, then retry by branch name if no rows found
#        (neighbourhoods like "Andheri West" are stored in the name column, not city)
#        SELECT name, city, address, ifsc, phone FROM branches WHERE city LIKE ?
#        If no rows: retry:
#        SELECT name, city, address, ifsc, phone FROM branches WHERE name LIKE ?
#        Use (f"%{city}%",) as the parameter (% wildcards for partial match)
#
#   5. Format each branch as:
#        f"{name} ({city_})\n"
#        f"  Address: {address}\n"
#        f"  IFSC: {ifsc}  |  Phone: {phone}"
#      Join all parts with "\n\n" and return.
#
#   6. If no rows: return f"No BNB branches found for city: '{city}'."
#
# ---------------------------------------------------------------------------

# TODO 2: implement query_branch() below -- keep the @tool decorator and docstring
raise NotImplementedError("TODO 2: implement query_branch() in wealthdesk/tools.py")


# ---------------------------------------------------------------------------
# TODO 3 of 4 -- TOOLS list + llm_with_tools + _run_tool()
# ---------------------------------------------------------------------------
# Three steps:
#
#   Step A: build the TOOLS list
#     Declaring TOOLS as a named list makes it easy to add or remove tools
#     in one place. Both bind_tools() and _run_tool's registry are built from
#     this single list, so you never have to update two places when adding
#     a new tool.
#
#        TOOLS = [
#            query_rates,
#            query_branch,
#        ]
#
#   Step B: create llm_with_tools
#     bind_tools() reads each function's type hints and docstring, converts them
#     to a JSON schema, and includes that schema in every request sent to the LLM.
#     The LLM was fine-tuned on examples with this schema format, so it knows to
#     respond with a structured tool call instead of guessing the answer from memory.
#
#        llm_with_tools = llm.bind_tools(TOOLS)
#
#   Step C: implement _run_tool()
#
#        def _run_tool(tool_name: str, tool_args: dict) -> str:
#
#     Build a registry dict from TOOLS:
#        _registry = {t.name: t for t in TOOLS}
#     Return an error string if the tool name is unknown.
#     Otherwise call the tool's .invoke() method:
#        return _registry[tool_name].invoke(tool_args)
#     Wrap in try/except and return an error string on failure.
#
# WHY .invoke() and not a plain function call?
#   .invoke() validates arguments against the tool's schema before executing,
#   and it integrates with LangSmith — the tool call appears as a separate trace span.
# ---------------------------------------------------------------------------

# TODO 3: add TOOLS list, llm_with_tools, and _run_tool() below
raise NotImplementedError("TODO 3: add TOOLS, llm_with_tools, and _run_tool() in wealthdesk/tools.py")
