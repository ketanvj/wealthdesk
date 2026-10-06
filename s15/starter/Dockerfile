# WealthDesk — Dockerfile starter
# Session 15: Cloud Deployment (US-13)
#
# Complete the five TODOs to containerise the WealthDesk Streamlit app.
#
# When done, verify with:
#   docker build -t wealthdesk .
#   docker run -p 8501:8501 -e GROQ_API_KEY=gsk_... wealthdesk
# Then open http://localhost:8501 and ask: "What is the home loan rate?"

# ── TODO 1: Choose a base image ───────────────────────────────────────────────
# Use the official Python 3.11 slim image.
# "slim" omits documentation and test files — about 40 MB smaller than the
# full image. This matters: smaller images pull faster on every deploy.
#
# Hint: FROM python:3.11-slim
FROM ___


# ── TODO 2: Set the working directory ─────────────────────────────────────────
# All subsequent COPY and RUN instructions use this as their base path.
# Convention: /app is the standard directory for web applications.
#
# Hint: WORKDIR /app
WORKDIR ___


# Install system build tools (needed by chromadb and tokenizers).
# This is already written — you do not need to change it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*


# ── TODO 3: Install Python dependencies ───────────────────────────────────────
# Copy requirements.txt first, then run pip install.
#
# Why copy requirements.txt before app code?
# Docker rebuilds from the changed layer downward. If you copy all files first
# and then install, every code edit forces a full pip reinstall (~2 minutes).
# Copying requirements.txt separately lets Docker cache the pip layer — it only
# reinstalls when requirements.txt itself changes.
#
# Hint:
#   COPY requirements.txt .
#   RUN pip install --no-cache-dir -r requirements.txt
COPY requirements.txt .
RUN ___


# Pre-download the embedding model (~90 MB).
# Baking it here means the first customer query starts instantly.
# Already written — no changes needed.
RUN python -c \
    "from sentence_transformers import SentenceTransformer; \
     SentenceTransformer('all-MiniLM-L6-v2')"


# ── TODO 4: Copy application files ────────────────────────────────────────────
# Copy these into the container (all must be in the same build context):
#   app.py          — Streamlit app entry point
#   wealthdesk/     — Python package (agent, nodes, config, tools, state)
#   langgraph.json  — LangGraph Studio config
#   mcp_server.py   — MCP server (lives alongside app.py in this session)
#   data/           — seed.py, ingest.py, documents/
#
# Hint: one COPY per item, or COPY multiple items separated by spaces.
COPY ___


# Build the SQLite database and vector store inside the image.
# Already written — no changes needed.
RUN python data/seed.py && python data/ingest.py


# ── TODO 5: Expose the port and define the startup command ────────────────────
# Streamlit listens on port 8501 by default.
# The CMD must launch Streamlit in headless mode (no browser auto-open)
# and bind to 0.0.0.0 so traffic from outside the container can reach it.
#
# Hint:
#   EXPOSE 8501
#   CMD ["streamlit", "run", "app.py",
#        "--server.port=8501",
#        "--server.address=0.0.0.0",
#        "--server.headless=true",
#        "--browser.gatherUsageStats=false"]
EXPOSE ___

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ___
