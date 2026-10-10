# WealthDesk -- In-Class Build

**Agentic AI Engineering, Batch 2 (October 2026)**

WealthDesk is the AI banking assistant for Bharat National Bank (BNB) that you build
session by session across the course. By Session 16 it is a multi-agent system with a
Streamlit UI, ChromaDB RAG, SQLite tool calls, MCP integration, compliance filtering,
LangSmith observability, and a Docker deployment.

---

## Getting Started

**Step 1 -- Fork this repo** (click Fork at the top right on GitHub). This gives you your own copy where you can save your work.

**Step 2 -- Clone your fork** (replace `YOUR_USERNAME` with your GitHub username):
```
git clone https://github.com/YOUR_USERNAME/wealthdesk.git
cd wealthdesk
```

**Step 3 -- Add the instructor repo as upstream** so you can pull new session files before each class:
```
git remote add upstream https://github.com/ketanvj/wealthdesk.git
```

**Step 4 -- Switch to the Batch 2 branch:**
```
git checkout -b cohort2 --track upstream/cohort2
```

**Before each session**, pull the latest starter files:
```
git pull upstream cohort2
```

**After working in class**, save your code to your fork:
```
git add .
git commit -m "Session X work"
git push
```

---

## What You Need Before Session 1

1. Python 3.11 or later
2. A Groq API key (free tier): https://console.groq.com/keys
3. VS Code with the Python extension

**Intel Mac users:** Use Python 3.11 or 3.12 for the local Hugging Face embeddings.
PyTorch does not publish Intel macOS wheels for Python 3.13 or later. Apple Silicon
and other supported platforms can use Python 3.13+.

**Setup (run once, before Session 1):**

```
# Step 1 -- Create a virtual environment (required)
# Mac (Apple Silicon): python3 -m venv .venv && source .venv/bin/activate
# Intel Mac (Python 3.12): python3.12 -m venv .venv312 && source .venv312/bin/activate
# Intel Mac (Python 3.11): python3.11 -m venv .venv311 && source .venv311/bin/activate
# Windows: python -m venv .venv && .venv\Scripts\activate

# Step 2 -- Install packages
pip install -r requirements.txt

# Step 3 -- Create your .env
# Mac:     cp .env.example .env
# Windows: copy .env.example .env
# Edit .env and add your actual Groq API key
```

**Seed the database and vector store (run once, before Session 1):**

```
python data/seed.py
python data/ingest.py
```

**Verify your setup:**

```
python test_setup.py
```

All checks should show OK. Take a screenshot and post it in the WhatsApp group.

---

## Folder Structure

```
wealthdesk/
  data/
    documents/          5 BNB policy documents (ChromaDB source)
    seed.py             Creates and seeds data/bnb_data.db
    ingest.py           Ingests documents into data/vectorstore/
    bnb_data.db         Generated -- do not commit (in .gitignore)
    vectorstore/        Generated -- do not commit (in .gitignore)

  s01/                  Session 1: Basic Conversational Agent (US-01)
    starter/            Your starting point -- fill in the TODOs
      wealthdesk/       The agent package (agent.py, nodes.py, config.py, state.py, tools.py)
      langgraph.json    LangGraph Studio config
    solution/           Reference solution (same package layout)
    tests/test_s01.py   Unit tests (run with: pytest s01/tests/ -v)

  s02/ ... s16/         Added as the course progresses

  requirements.txt      All packages for all sessions (install once)
  .env.example          Template for your .env file
  .gitignore            Excludes .env, database, and vector store from git
```

---

## Session Map

| Session | Story | What You Build |
|---|---|---|
| Pre-S1 | US-00 | Data layer: SQLite + ChromaDB setup (seed.py, ingest.py) |
| S1 | US-01 | Terminal chatbot with single-turn Groq + LangGraph |
| S2 | US-02 | Multi-turn memory with SQLite checkpointer |
| S3 | US-07 | Query routing: SIMPLE vs COMPLEX, RM escalation |
| S4 | US-03 | ChromaDB RAG: policy document retrieval |
| S5 | US-04 | SQLite tool calls: live rate and branch lookup |
| S6 | US-05 | Baseline evaluation: 40-question golden dataset, LLM-as-judge |
| S7 | US-06 pt.1 | MCP server setup and tool wrapping |
| S8 | US-06 pt.2 | Agent calls tools via MCP protocol |
| S9 | US-08+10 | Compliance filter (SEBI/DPDP) + LangSmith tracing |
| S10 | US-11 pt.1 + US-09 | Multi-agent: Supervisor, Documents Agent, Rates Agent |
| S11 | -- | Industry guest session (no build) |
| S12 | US-11 pt.2 | Multi-agent system complete: perf gate + Streamlit skeleton |
| S13 | US-12+16 | Streamlit UI + Human-in-the-Loop approval |
| S14 | US-14 | Security and guardrails (OWASP LLM Top 10 + DPDP Act) |
| S15 | US-13 | Dockerfile + Docker run + cloud deployment |
| S16 | US-15+17 | Advanced eval + data flywheel + prompt versioning |

---

## Running the Tests

```
# From the wealthdesk/ directory -- run one session at a time:
pytest s01/tests/ -v
pytest s02/tests/ -v

# Tests do not require a live Groq API key -- the LLM is mocked.
# You can also run multiple sessions together:
pytest s01/tests/ s02/tests/ s03/tests/ -v
```

---

## Important Rules

- Never commit your `.env` file. It contains your API key.
- Always run scripts from the `wealthdesk/` directory, not from inside a subfolder.
- If you accidentally expose an API key on GitHub, rotate it immediately at the provider's console.
- When in doubt about a rate or policy, the database is the source of truth -- not the documents, not the system prompt.

---

## Getting Help

Post in the WhatsApp group. Include: the error message, which script you were running,
and which operating system you are on.
