# S07 MCP Server — Slide Deck

**Course:** Agentic AI Engineering — Batch 1
**Session:** 7 (WealthDesk: MCP Server Part 1 — US-06 Part 1)
**Audience:** Working developers who have completed S06. Comfortable with the WealthDesk agent, LangSmith tracing, and SQLite tool calls from S05.
**Duration:** 2.5 hours (20 min problem framing + 15 min concepts + 25 min walkthrough + 30 min hands-on + 25 min Inspector demo + 10 min tests/debrief + ~25 min transitions/Q&A/setup)
**Slide count:** 13

---

## Slide 1 — Title + Learning Objective

**Heading:** MCP Server — Decoupling Tools from the Agent

**Subtitle:** Same tools. Same database. Separate process.

**Learning objective box (visible on slide):**
> By the end of this session you will be able to:
> build a standalone FastMCP server exposing `query_rates` and `query_branch`, explain the Server / Client / Schema contract, test MCP tools with Inspector independently of any agent code, and describe how Session 8 will wire the WealthDesk agent to this server.

**Instructor note:**
[2 min] S07 is a decoupling session, not a feature. The agent does the same thing it did in S05. The tools now live in a separate process. Set that expectation up front — participants who expect new agent behaviour will be confused. The payoff is architectural: the same tools can serve any MCP-compatible client (Inspector today, the agent in S08, Claude Desktop in S11). No LLM calls happen in this session — if Groq is down, today is unaffected.

---

## Slide 2 — The Problem: Tight Coupling

**Heading:** Tools trapped inside the agent

**Code snippet (from S05):**
```python
# s05/solution/wealthdesk/tools.py  ← same file as agent
from langchain_core.tools import tool

@tool
def query_rates(product_type: str = "all") -> str:
    """Fetch current BNB interest rates from the database."""
    ...

@tool
def query_branch(city: str = "all") -> str:
    """Fetch BNB branch locations from the database."""
    ...

# agent.py — same package
llm_with_tools = llm.bind_tools([query_rates, query_branch])
```

**Two-column:**

Left — WHAT WE'VE BEEN DOING:
- Tools live inside the agent's package
- To test a tool, you start the whole agent
- To use a tool in a second agent, you copy the code
- To update a tool, you touch agent code — and risk breaking the graph

Right — WHAT GOES WRONG AT SCALE:
- A banking system with 20 tools and 5 different agents
- Copy-paste across agent files = guaranteed drift
- Tool version and agent version are permanently locked together
- Compliance audit: "Show me all agents that use `query_rates` v2" — impossible

**Callout at bottom:**
This is tight coupling: the tool and the agent share a file. A frontend that embeds its own database queries has the same problem. The solution is the same too: separation of concerns.

**Instructor note:**
[4 min] Open `s05/solution/wealthdesk/tools.py` on screen. Ask: "If a second agent — say, a loan eligibility checker — also needs `query_rates`, what do you do?" Let them answer. The naïve answer is copy-paste. The right answer is: extract the tools into a shared service. MCP is that service. Ask: "To test just `query_rates` without running the whole agent, what would you need to do right now?" The answer is: write a test that imports tools.py, which is fine — but that test depends on the same Python environment and process as the agent. MCP separates them at the process boundary.

---

## Slide 3 — The Architecture Shift

**Heading:** Decoupling — the MCP architecture

**Two-column diagram:**

WITHOUT MCP:
```
agent.py
  @tool query_rates()
  @tool query_branch()
  llm.bind_tools([...])
  classify → retrieve → respond

# Tools and agent: same application/package
# Test a tool = start the agent
# Share a tool = copy-paste
```

WITH MCP:
```
mcp_server.py  (Session 7)
  @mcp.tool() query_rates()
  @mcp.tool() query_branch()
  mcp.run()  # waits for clients

agent.py  (Session 8)
  connect to mcp_server.py
  tools discovered at runtime
  graph topology: unchanged
```

**Three annotation cards below the diagram:**

Card 1 — Separate process:
`mcp_server.py` runs independently. No agent code needed to test a tool. Any MCP-compatible client — Inspector, the WealthDesk agent, Claude Code, GitHub Copilot — can connect to it.

Card 2 — Discovered at runtime:
The client asks the server for its tool list when it connects. No Python imports are required. Zero code changes to the agent when a new tool is added to the server — restart the server, reconnect the client, and the new tool appears. This is fundamentally different from `bind_tools([...])`, which requires importing the function into the agent file.

Card 3 — Any client can connect:
MCP Inspector (today), the WealthDesk agent (S08), Claude Desktop (S11) — same server, different clients.

**Why companies adopt MCP (callout):**
One MCP server can be shared by Claude Desktop, Cursor, VS Code, internal AI agents, test clients, and future applications — without duplicating tool code. That's the architectural payoff this session sets up.

**Instructor note:**
[5 min] Draw this diagram on screen before showing the slide. Ask: "What is different between the two sides?" Let them spot it: the tools moved out of the agent file. Then ask: "What does the agent in S08 need to change to use this server?" The answer: only how it discovers tools — the graph topology is unchanged. Use the API analogy: "Your frontend doesn't embed the database query. It calls an API endpoint. MCP is that API, applied to LLM tool calls."

---

## Slide 4 — Three Things to Know

**Heading:** Three things to know about MCP

**Three stacked cards, labelled 1 / 2 / 3:**

**Card 1 — SERVER**
A process that exposes tools (and optionally resources and prompts).
- Runs as a separate process: `python mcp_server.py`
- Communicates over STDIO (this course) or HTTP (enterprise deployments)
- Registers tools with `@mcp.tool()` decorators
- Answers two core requests: `list_tools()` and `call_tool()`

*Today: you build this.*

**Card 2 — CLIENT**
The agent or inspector that connects to the server.
- Discovers available tools by calling `list_tools()` at startup
- Invokes tools by calling `call_tool(name, arguments)`
- Think of `list_tools()` / `call_tool()` as the REST equivalent of GET and POST — but for tools.
- MCP Inspector is a visual client — ideal for testing
- Session 8: the WealthDesk agent becomes the client

*Today: Inspector plays this role. Session 8: the agent does.*

**Card 3 — SCHEMA**
The tool's interface contract — generated automatically from Python.
- Name: the function name
- Description: from the Python docstring — **the LLM reads this to decide whether to use the tool.** Writing a clear docstring is prompt engineering.
- Parameters: JSON Schema generated from Python type hints
- The client uses the schema to know what arguments to pass

*FastMCP generates this for free from the docstring and type hints. No extra code.*

**Callout at bottom:**
For today: you are building the server. The Inspector is the client. The schema is generated automatically. Session 8: the WealthDesk agent becomes the client.

**How the schema flows (mini-diagram):**
```
Python function + docstring + type hints
        ↓  FastMCP reads these at registration time
    JSON Schema
        ↓  served via list_tools() to any client
    Inspector  ──or──  Agent  ──or──  Claude Desktop
        ↓  LLM reads description to decide which tool to call
      call_tool(name, args)
        ↓
    SQLite query → result string
```
People often wonder "where does the schema come from?" — this diagram shows the full chain.

**Instructor note:**
[5 min] Show the MCP Inspector UI on screen while explaining each concept.
- Point to the left panel (tool list) while explaining SERVER — the server advertised these.
- Point to the schema panel while explaining SCHEMA — FastMCP built this from the Python type hint.
- Point to the Run button while explaining CLIENT — calling `call_tool()`.
The visual reinforcement makes these abstract concepts concrete. Don't go deeper than this — the code walkthrough covers implementation.

---

## Slide 5 — Code Walkthrough: The Decorator Change

**Heading:** One decorator change — same function body

**Sub-heading eyebrow:** CODE WALKTHROUGH — STEP 1 OF 3

**Side-by-side comparison:**

Left — Session 5 (`tools.py`):
```python
from langchain_core.tools import tool

@tool
def query_rates(
    product_type: str = "all"
) -> str:
    """Fetch current BNB interest rates.

    Args:
        product_type: loan / fd / all
    """
    conn = sqlite3.connect(DB_PATH)
    ...  # SQL queries here
```

Right — Session 7 (`mcp_server.py`):
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wealthdesk-tools")

@mcp.tool()
def query_rates(
    product_type: str = "all"
) -> str:
    """Fetch current BNB interest rates.

    Args:
        product_type: loan / fd / all
    """
    conn = sqlite3.connect(DB_PATH)
    ...  # IDENTICAL to Session 5
```

**Three annotation cards below:**

Card 1 — Decorator only:
The import and decorator change. The function body is identical. `@tool` (LangChain) → `@mcp.tool()` (FastMCP).

Card 2 — Schema for free (and docstring = prompt engineering):
FastMCP reads the docstring → generates the tool description. Reads the type hint `str` and default `"all"` → generates the JSON Schema. The Inspector shows a text field pre-filled with "all".
**The LLM reads this description when deciding whether to call the tool.** The docstring is not just for humans — it is a prompt. Write it clearly.

Card 3 — Body: copy-paste is correct:
Open `s05/solution/wealthdesk/tools.py`. Find the `query_rates` function body. Copy it. Paste into the TODO slot. That's TODO 1 done.

**Ask participants:**
"What does `product_type: str = "all"` tell the MCP Inspector?"
Answer: the parameter is a string, it is optional, and the default value is "all". The Inspector will show a text input field pre-filled with "all".

**Instructor note:**
[5 min] Open both files side by side in the editor. Ask: "What is literally different between these two files?" Let them find it: the import, the `mcp = FastMCP()` line, and the decorator. Emphasise: "You are not learning a new database API. You are learning a new registration mechanism." The SQL queries, the DB path, the return format — all unchanged. This is the key insight that makes the hands-on manageable: the implementation is a copy from S05.

---

## Slide 6 — Code Walkthrough: The Parameterised Query

**Heading:** The parameterised query — separating code from data

**Sub-heading eyebrow:** CODE WALKTHROUGH — STEP 2 OF 3

**Code (the `query_branch` body):**
```python
@mcp.tool()
def query_branch(city: str = "all") -> str:
    """Fetch BNB branch locations from the database."""
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
            (f"%{city}%",),   # ← city is a parameter, never part of the SQL string
        ).fetchall()
```

**Two annotation cards:**

Card 1 — SAFE — use this:
Parameterised SQL **separates code from data**. The `?` placeholder passes `city` as a parameter, not as part of the SQL string. The database treats it as a value, never as code. An attacker cannot escape the string context.

**Note:** Parameterised queries prevent SQL injection, but SQL wildcard characters (`%` and `_`) in user input are still interpreted literally as wildcards by the `LIKE` operator — e.g., `query_branch("%")` returns all branches. For this course that behaviour is acceptable; in production, escape wildcards or use `=` instead of `LIKE` for exact matches.

Card 2 — UNSAFE — never do this:
```python
f"WHERE city LIKE '%{city}%'"
```
If `city = "' OR 1=1 --"` then the query becomes:
`WHERE city LIKE '%' OR 1=1 --%'` — the injected condition bypasses the city filter and returns every branch instead of only the requested city.

**Callout at bottom:**
The SQL injection tests in `s07/tests/` verify this: `test_branch_city_injection_does_not_drop_table` passes a malicious string and confirms the `branches` table survives. We will revisit this at S14 (OWASP LLM Top 10).

**Instructor note:**
[4 min] This is worth focused time — it is a security lesson embedded in an MCP lesson. Demo live in the Python REPL (run from the `s07/solution/` directory):
```python
from mcp_server import query_branch
print(query_branch("' OR 1=1 --"))  # returns "No BNB branches found for city"
# Table survived. Parameterised query rendered it harmless.
```
Then show what the f-string version produces as a string (don't execute it):
`f"WHERE city LIKE '%' OR 1=1 --%'"` — the SQL injection is visible.
Say: "The TODO says copy from tools.py — do that. The `?` is already there. The most common mistake is replacing it with an f-string while 'tidying up'. Leave it exactly as you find it."

---

## Slide 7 — Code Walkthrough: Entry Point

**Heading:** Server instantiation and the entry point

**Sub-heading eyebrow:** CODE WALKTHROUGH — STEP 3 OF 3

**Full code listing:**
```python
from mcp.server.fastmcp import FastMCP
import sqlite3
from pathlib import Path

# ① Server name — appears in Inspector and in LangSmith traces (S08)
mcp = FastMCP("wealthdesk-tools")

# ② Same DB as the S05 agent — one source of truth
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH  = DATA_DIR / "bnb_data.db"

@mcp.tool()
def query_rates(product_type: str = "all") -> str: ...

@mcp.tool()
def query_branch(city: str = "all") -> str: ...

if __name__ == "__main__":
    mcp.run()   # ③ STDIO transport — reads stdin, writes stdout
```

**Three annotation cards:**

Card 1 — ① Server name:
The string `"wealthdesk-tools"` appears in Inspector's header and in LangSmith traces (Session 8). Choose something descriptive — it is the server's public identity.

Card 2 — ② Shared DB path:
Same `bnb_data.db` the S05 agent uses. One database, accessed by both the agent and the MCP server. No data duplication, no sync problem.

Card 3 — ③ STDIO transport:
`mcp.run()` is a **blocking call** — code after it never executes. It reads JSON-RPC messages from stdin and writes responses to stdout. That's why the terminal appears to hang: the server is waiting for a client to connect. When Session 8's agent subprocess-starts this server, Python gives it a stdin pipe. No ports, no HTTP, no authentication configuration needed for this course.

**Important:** While using STDIO transport, never write debug output to `stdout` (no `print()` calls in the tool functions). Stdout is reserved for MCP protocol messages — extra output corrupts the communication stream. Use `logging` to `stderr` for any diagnostic output.

**Run the server live:**
```bash
python s07/solution/mcp_server.py
# Terminal appears to hang — correct.
# Server is waiting for JSON-RPC messages on stdin.
# Ctrl+C to stop.
```

**Instructor note:**
[3 min] Run the server live on screen before opening the Inspector. The "hanging terminal" surprises people — pre-empt it: "The server is waiting for messages. It doesn't print anything because nothing has connected yet." The server name in ① becomes meaningful in S08 when LangSmith shows `wealthdesk-tools` in the tool call trace. Plant that seed now: "You'll recognise this name in the LangSmith trace next session."

---

## Slide 8 — YOUR TURN

**Heading:** Your turn — 30 minutes

**Header bar:** Open `s07/starter/mcp_server.py` — replace two `NotImplementedError` bodies

**Two-column card layout:**

TODO 1 — `query_rates(product_type)`:
- Open `s05/solution/wealthdesk/tools.py`
- Find the `query_rates` function body (the SQL block)
- Copy the body, paste into the TODO 1 slot
- The `@mcp.tool()` decorator is already applied — the body is identical to S05

TODO 2 — `query_branch(city)`:
- Same process — copy from `s05/solution/wealthdesk/tools.py`
- The `?` placeholder in the SQL query **must stay** — do not replace it with an f-string
- The SQL injection tests verify this

**Quick self-test before opening Inspector:**
```bash
python -c "
import sys; sys.path.insert(0, 's07/starter')
from mcp_server import query_rates, query_branch
print(query_rates('loan'))       # tests product_type filter
print(query_rates())             # tests the default argument (should equal 'all')
print(query_branch('Bengaluru')) # tests city filter
"
```
If all three print real BNB data, the implementation is correct. Then open Inspector.

**Open Inspector:**
```bash
npx @modelcontextprotocol/inspector python s07/starter/mcp_server.py
# Open http://localhost:5173
```

**Common issues table:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: mcp` | Package not installed | `pip install -r requirements.txt` |
| `OperationalError: no such table: loan_products` | DB not seeded | `python data/seed.py` then retry |
| `NotImplementedError` still raised | TODO body not replaced | Delete the `raise` line, paste SQL body |
| Inspector shows no tools | Server startup or import error (tools register at import time, not at call time) | Check terminal for `ImportError` or `SyntaxError`; run `python s07/starter/mcp_server.py` directly to see the error |
| Tools visible but calls fail with `NotImplementedError` | TODO body not yet replaced | Delete the `raise NotImplementedError` line and paste the SQL body |
| `TypeError: 'tuple' object is not callable` | `params` not wrapped as tuple | Use `(f"%{city}%",)` not `f"%{city}%"` |
| `npx: command not found` | Node.js not installed | Install Node.js from nodejs.org |
| Inspector: `ModuleNotFoundError: mcp` | npx picked up system Python, not venv | Use `.venv/bin/python` (Mac/Linux) or `.venv\Scripts\python.exe` (Windows) |

**Instructor note:**
[30 min] The implementation goal is intentionally simple — copy from S05, paste into S07. The learning is in the recognition that the decorator changed but the logic did not. Circulate early to check two things: (1) the `raise NotImplementedError` line is fully deleted — it's easy to leave the `raise` and add the SQL after it; (2) the `?` placeholder in `query_branch` is preserved. The most common mistake is replacing it with an f-string "to make it cleaner." Recommend the quick self-test before they open Inspector — it gives a tight feedback loop before dealing with the browser UI.

---

## Slide 9 — MCP Inspector Demo

**Heading:** MCP Inspector — the client's view

**Sub-heading eyebrow:** LIVE DEMO

**Inspector launch command:**
```bash
npx @modelcontextprotocol/inspector python s07/starter/mcp_server.py
```
Open the URL printed in your terminal (do not assume a fixed port — newer Inspector versions use port 6274 by default).

**Node.js prerequisite:** Inspector requires Node.js 22.19 or newer. Run `node --version` to check. Install from nodejs.org if needed.

**Venv note:** `npx` may invoke the system Python rather than your active venv. If Inspector shows `ModuleNotFoundError: mcp`, use the explicit venv Python path:
```bash
# Mac/Linux
npx @modelcontextprotocol/inspector .venv/bin/python s07/starter/mcp_server.py
# Windows
npx @modelcontextprotocol/inspector .venv\Scripts\python.exe s07/starter/mcp_server.py
```

**Four walkthrough steps:**

Step 1 — Tool list panel (left):
`query_rates` and `query_branch` appear with their descriptions (from the docstring). "The Inspector just called `list_tools()` on your server. This is exactly what the WealthDesk agent will call at startup in Session 8."

Step 2 — Schema view:
Click `query_rates`. The input schema shows: `product_type`, type `string`, default `"all"`. "FastMCP generated this from your Python type hint `str = "all"`. No extra code. The client now knows what to pass."

Step 3 — Call `query_rates(product_type="loan")`:
Fill in `product_type: loan`, click Run. Real BNB rate data appears.

**Clarify the execution flow — Inspector does NOT contain the tools:**
```
Inspector (browser)
    ↓  JSON-RPC call_tool("query_rates", {"product_type": "loan"})
MCP Server (your Python process)
    ↓  executes query_rates() function
SQLite (bnb_data.db)
    ↓  returns rows
MCP Server  →  Inspector  →  you see the result
```
"Inspector is a client. It sent a message to your server. Your server ran the SQL. Inspector just displayed what came back."

Step 4 — Discussion point:
"What would you need to do to add a third tool — say, `query_emi(principal, rate, tenure)` that calculates a monthly EMI?"
Answer: add one `@mcp.tool()` function to `mcp_server.py`. Restart the server. Inspector (and in S08, the agent) sees three tools automatically. Zero changes to the agent.

**Also demo:**
- `query_branch(city="Bengaluru")` → Indiranagar and Koramangala appear
- `query_branch(city="Mumbai")` → different branch appears
- `query_rates()` with no argument (default "all") → both loans and FDs appear

**Instructor note:**
[10 min] Share screen with the Inspector browser tab open. Walk slowly — participants need to map what they see to what they built. Step 1 is the moment of recognition: "I can see my docstring as the tool description." Step 3 is the payoff: real data from their implementation. For Step 4, wait for their answers before confirming — the point is they derive the answer from the architecture, not from being told.

---

## Slide 10 — Three Clients, One Server

**Heading:** Same server. Three clients. Zero changes to `mcp_server.py`.

**Sub-heading eyebrow:** LIVE DEMO (if time allows)

**Two-column layout:**

Left — Claude Code:
```bash
# From inside the wealthdesk/ directory
claude mcp add wealthdesk-tools \
  python3 $(pwd)/s07/starter/mcp_server.py

# Start Claude Code
claude
```
Then ask: *"What are BNB's current home loan rates?"*
Claude Code calls `query_rates(product_type="loan")` and shows the live result.

```bash
# Remove after demo
claude mcp remove wealthdesk-tools
```

> **Note:** Claude Code must be opened from the `wealthdesk/` directory. Project-scoped servers only load when the project path matches.

Right — GitHub Copilot (VS Code Agent Mode):
Create `.vscode/mcp.json` in the `wealthdesk/` folder:
```json
{
  "servers": {
    "wealthdesk-tools": {
      "type": "stdio",
      "command": "python3",
      "args": ["${workspaceFolder}/s07/starter/mcp_server.py"]
    }
  }
}
```
Then in VS Code:
1. Open GitHub Copilot Chat (open the Chat panel from the Activity Bar)
2. Switch to **Agent** mode (dropdown at top of chat panel)
3. Click the **Tools** icon — `query_rates` and `query_branch` appear
4. Ask: *"What are BNB's home loan rates?"*

> Requires VS Code 1.99+ with GitHub Copilot and agent mode enabled.
> If tools don't appear: `Cmd+Shift+P` → Reload Window.

**Callout (full width):**
> "Three clients: Inspector, Claude Code, GitHub Copilot. The server didn't change. That is exactly what a standard protocol buys you — build once, connect everywhere. Session 8 makes our own Python agent the fourth client."

**Instructor note:**
[10 min — optional, run if time allows] This is the "USB-C for AI" moment — the abstract architecture argument becomes undeniable when they watch two production tools connect to the server they just built. Run both demos live if you can; if time is short, do Claude Code only — it has the tightest feedback loop. The teaching point to say out loud: "The server didn't change. Not a single line. What changed is the config file on the client side. That is exactly what a standard protocol buys you." Then preview S08: "Next session, our WealthDesk Python agent becomes the fourth client."

---

## Slide 11 — Tests and Debrief

**Heading:** What the tests verify

**Run command:**
```bash
pytest s07/tests/ -v
# All tests should pass
```

**Five test call-outs:**

`test_server_has_two_tools` — Structure test:
Confirms exactly two `@mcp.tool()` registrations. If you accidentally register the same function twice, this fails. **Note for homework:** When you add `query_emi` as the homework assignment, this test will fail — intentionally. Update the assertion from `== 2` to `== 3`. Tests must evolve with intentional changes to the system.

`test_home_loan_rate_is_8_5` — Data contract test:
Verifies the specific value expected in the S06 golden dataset. If someone changes the seeded rate in `bnb_data.db`, the S06 eval pass rate would drop without explanation. This test catches the data contract break.

`test_branch_city_injection_does_not_crash` — Security test:
Passes a SQL injection string as `city`. The parameterised query renders it harmless — the function returns "No branches found" instead of crashing or leaking data.

`test_branch_city_injection_does_not_drop_table` — Security test:
Attempts `"Mumbai'; DROP TABLE branches;--"` as the city value, then calls `query_branch("Mumbai")` again. If parameterisation is broken and DROP TABLE executes, the second call raises `OperationalError`. This test verifies the table survives.

`test_query_rates_default_is_all` — Default contract test:
Verifies that calling `query_rates()` with no argument is identical to `query_rates("all")`. Small test, but it catches the common mistake of defining the default in the function signature and then not respecting it inside the `if` conditions.

**Homework:**
1. Add `query_emi(principal: float, rate: float, tenure_years: int) -> str` — no database, pure math. Use this implementation:
```python
r = rate / (12 * 100)          # annual % → monthly decimal
n = tenure_years * 12           # years → months
emi = (principal * r * (1 + r)**n) / ((1 + r)**n - 1) if r > 0 else principal / n
```
The `r > 0` guard handles the edge case where `rate=0` (avoid division by zero). Verify it appears in Inspector with the correct schema and call `query_emi(500000, 8.5, 20)` to confirm the result.

2. Stretch: Add `query_rates_history(product_name: str) -> str` that reads the `rate_history` table. Test with `product_name="Home Loan"`.

**Instructor note:**
[5 min] Run live on screen. Walk through the five tests above specifically. On the security tests, say: "These aren't just checking that the function doesn't crash. They are checking that an attacker cannot compromise the database through this tool. That's a security guarantee, written as code." The data contract test bridges S06 to S07: a changed seed value silently breaks the eval. Unit tests catch that before it reaches a participant. `test_query_rates_default_is_all` is one participants often skip writing — a no-default call returning the same result as "all" is a small but invisible contract break if missed.

---

## Slide 12 — Preview Session 8

**Heading:** What changes in Session 8

**Two-column:**

Left — Today (S07) — Tools run here:
```python
# mcp_server.py runs standalone
# Agent code (s05) is unchanged
# Inspector is the client today

mcp = FastMCP("wealthdesk-tools")

@mcp.tool() query_rates()
@mcp.tool() query_branch()

mcp.run()  # waits for client
```

Right — Session 8 — Agent uses MCP server:
```python
# agent.py — graph topology unchanged
# Only tool-wiring changes

from langchain_mcp_adapters.client import ...

# Connects to mcp_server.py at startup
# Discovers tools via list_tools()
# MCP adapter → LangChain tools

# llm.bind_tools(mcp_tools)  ← input changed
# Graph topology: unchanged
```

**Architecture comparison:**

```
S05 (old)                        S08 (new)
─────────────────────────────    ──────────────────────────────────
Agent                            Agent
  ↓ imports query_rates()          ↓ connects to subprocess
Tool function (same process)     MCP Client
                                   ↓ JSON-RPC list_tools / call_tool
                                 MCP Server (separate process)
                                   ↓ executes function
                                 Tool function
```
This diagram is why the architecture matters for Claude Desktop, Cursor, VS Code — any client speaks the same JSON-RPC layer. The tools don't move; only the wiring does.

**Two annotation cards:**

What changes in S08 (RED):
How the agent discovers tools — instead of `llm.bind_tools([query_rates, query_branch])` with locally imported functions, the agent discovers tools at runtime via an MCP client connection to `mcp_server.py`. The MCP adapter converts the discovered tools into LangChain-compatible tools, and `bind_tools()` receives those adapted tools. The mechanism stays; the input changes.

What stays the same (GREEN):
Graph topology, `classify → retrieve → respond` flow, system prompts, LangSmith tracing. In fact, traces get richer: tool calls are attributed to `"wealthdesk-tools"` in the trace.

**Instructor note:**
[2 min] Main point: the graph topology does not change in S08 either. The tools are wired differently — but the LangGraph graph, the classifier, the prompts, the state — all unchanged. Use the S04 → S05 analogy: "In S05, the graph didn't change either. Adding capability in this architecture means changing what's inside a node, not the graph." Leave participants on that note before assignment.

---

## Slide 13 — Quick Reference

**Heading:** Quick Reference — Leave on screen during hands-on

**Card grid (2 rows × 4 columns):**

Row 1:
- `mcp_server.py` — Standalone process. Starts with `mcp.run()`. No agent code needed. Works with Inspector, the agent, or any MCP client.
- `@mcp.tool()` — Registers a function as an MCP tool. Docstring → description. Type hints → JSON Schema parameters.
- `FastMCP("name")` — Server instance. Name appears in Inspector and LangSmith traces. One per server file.
- `mcp.run()` — STDIO transport. Reads from stdin, writes to stdout. Inspector launches the server as a subprocess and connects to its stdin/stdout.

Row 2:
- `list_tools()` — Client calls this at startup. Server replies with name, description, and schema for each registered tool. JSON-RPC method: `tools/list`.
- `call_tool(name, args)` — Client calls this to invoke a tool. Server executes the function and returns the result as a string. JSON-RPC method: `tools/call`.
- `query_rates body` — IDENTICAL to S05 `tools.py`. Only the decorator changed. Copy-paste is the correct approach.
- `? placeholder` — Parameterised SQL separates code from data. Never replace with f-string. SQL injection tests verify this.

**Docstring quality matters:**
The LLM decides which tool to call based on the description in the schema. A vague docstring = wrong tool selected. Writing a clear docstring is prompt engineering — it becomes more important as tool count grows.

**Inspector command (prominent bar):**
```bash
npx @modelcontextprotocol/inspector python s07/starter/mcp_server.py
# Open the URL printed in your terminal (port 6274 on newer Inspector versions)

# If mcp is not found (venv not picked up):
# Mac/Linux: use .venv/bin/python  instead of  python
# Windows:   use .venv\Scripts\python.exe  instead of  python
```

**Common issues row:**
- Server won't start → `python s07/solution/mcp_server.py` directly to see the error
- No tools in Inspector → Server startup or import error; run `python s07/starter/mcp_server.py` directly to see the error
- Tools visible but calls fail → `raise NotImplementedError` still present — delete the `raise` line and paste the SQL body
- `OperationalError` → `python data/seed.py` then retry

**Assignment reminder:**
Add `query_emi(principal, rate, tenure_years)` — EMI formula, no DB. Verify it appears in Inspector.
Stretch: `query_rates_history(product_name)` — reads `rate_history` table.

**Instructor note:**
[Leave on screen] Leave this slide on the projector during the hands-on. The eight reference cards cover what participants most often look up. The Inspector command means they don't need to search for it. Remind participants: "The solution is at `s07/solution/mcp_server.py` if you want to check your work."

---

## Key Teaching Points (for all instructor notes)

1. **S07 is a decoupling session, not a feature** — the agent does the same thing as S05; the tools now live in a separate process. Set this expectation at the start.
2. **Decorator changed, body identical** — the SQL in `query_rates` and `query_branch` is byte-for-byte the same as S05. Copy-paste is the correct approach for the hands-on.
3. **The ? placeholder must survive** — the most common mistake is replacing it with an f-string "to make it cleaner." The security tests catch it, but it's better to catch it by saying it upfront.
4. **No LLM calls in S07** — the MCP server is pure SQLite. If Groq is down, this session is completely unaffected.
5. **The graph doesn't change in S08 either** — reinforce the pattern: adding capability in this architecture means changing what's inside a node, not the graph topology.
6. **Inspector demo is the payoff** — participants see their tool's docstring become the description, their type hint become the schema, and a real SQL query return live data — all without any agent code running.
