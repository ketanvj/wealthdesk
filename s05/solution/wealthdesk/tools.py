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


@tool
def query_rates(product_type: str = "all") -> str:
    """Fetch current BNB interest rates from the database.

    Args:
        product_type: Which rates to return. Options:
            "loan" -- all loan products (home, personal, car, education, gold)
            "fd"   -- all fixed deposit products
            "all"  -- both loans and FDs (default)

    Returns formatted rate information as a plain-text string.
    """
    # check_same_thread=False: SQLite normally raises ProgrammingError if a connection
    # is used from a thread other than the one that created it. LangGraph runs tool calls
    # in a thread-pool executor, so the tool may execute on a different thread than the
    # one that opened the connection. This flag disables that check.
    conn  = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    lines = []

    if product_type in ("loan", "all"):
        rows = conn.execute(
            "SELECT name, interest_rate, tenure_min_years, tenure_max_years "
            "FROM loan_products ORDER BY interest_rate"
        ).fetchall()
        for name, rate, min_y, max_y in rows:
            lines.append(f"{name}: {rate:.2f}% p.a., tenure {min_y}-{max_y} years")

    if product_type in ("fd", "all"):
        rows = conn.execute(
            "SELECT tenure_label, interest_rate, senior_rate "
            "FROM fd_products ORDER BY tenure_months"
        ).fetchall()
        for label, rate, senior in rows:
            lines.append(
                f"FD {label}: {rate:.2f}% p.a. "
                f"(senior citizens: {rate + senior:.2f}%, extra +{senior:.2f}%)"
            )

    conn.close()
    return "\n".join(lines) if lines else "No rate data found."


@tool
def query_branch(city: str = "all") -> str:
    """Fetch BNB branch locations from the database.

    Args:
        city: Filter branches by city name. Use "all" for every branch.

    Returns branch names, addresses, IFSC codes, and phone numbers.
    """
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)  # see query_rates for why

    if city.lower() == "all":
        rows = conn.execute(
            "SELECT name, city, address, ifsc, phone FROM branches ORDER BY city, name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name, city, address, ifsc, phone "
            "FROM branches WHERE city LIKE ? ORDER BY name",
            (f"%{city}%",),
        ).fetchall()
        if not rows:
            # Neighbourhood names (e.g. "Andheri West", "Koramangala") are stored
            # in the branch name, not the city column — retry by name.
            rows = conn.execute(
                "SELECT name, city, address, ifsc, phone "
                "FROM branches WHERE name LIKE ? ORDER BY name",
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


# Declaring TOOLS as a named list makes it easy to add or remove tools in one place.
# Both bind_tools() and _run_tool's registry are built from this single list,
# so you never have to update two places when adding a new tool.
TOOLS = [
    query_rates,
    query_branch,
]

# bind_tools() reads each function's type hints and docstring, converts them to a
# JSON schema, and includes that schema in every request sent to the LLM.
# The LLM was fine-tuned on examples with this schema format, so it knows to respond
# with a structured tool call instead of guessing the answer from memory.
llm_with_tools = llm.bind_tools(TOOLS)


def _run_tool(tool_name: str, tool_args: dict) -> str:
    # Build the registry dynamically from TOOLS so it stays in sync automatically.
    # t.name is set by @tool to match the function name (e.g. query_rates.name == "query_rates").
    # The LLM returns tc["name"] == "query_rates" -- this dict lets us look up the right tool.
    _registry = {t.name: t for t in TOOLS}
    if tool_name not in _registry:
        return f"Unknown tool: {tool_name}"
    try:
        # .invoke() is a LangChain BaseTool method, not a plain Python call.
        # When @tool wraps a function, it becomes a StructuredTool object with .invoke().
        # We use .invoke(tool_args) instead of calling the function directly because:
        #   1. tool_args is a dict {"product_type": "loan"} -- .invoke() unpacks it into
        #      keyword arguments automatically (equivalent to query_rates(product_type="loan"))
        #   2. It validates arguments against the tool's schema before executing
        #   3. It integrates with LangSmith -- the tool call appears as a separate trace span
        return _registry[tool_name].invoke(tool_args)
    except Exception as e:
        return f"Tool error ({tool_name}): {e}"
