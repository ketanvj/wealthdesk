# WealthDesk — production Dockerfile
# Session 15: Cloud Deployment (US-13)
#
# Three-layer mental model:
#   1. System environment  — base image + OS packages
#   2. Python environment  — pip dependencies (cached separately from code)
#   3. Application layer   — source, data, pre-built artefacts
#
# Build:
#   docker build -t wealthdesk .
#
# Run:
#   docker run -p 8501:8501 -e GROQ_API_KEY=gsk_... wealthdesk
#   docker run -p 8501:8501 --env-file .env wealthdesk
#
# Security: GROQ_API_KEY is passed at runtime only — never baked into the image.
# Anyone who runs `docker history wealthdesk` would see a baked-in key.

# ── Layer 1: System environment ───────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# chromadb and tokenizers require C build tools.
# --no-install-recommends keeps the image ~40 MB smaller.
# Deleting the apt cache in the same RUN layer avoids storing it in the image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Layer 2: Python environment ───────────────────────────────────────────────

# Copy requirements.txt BEFORE any application code.
# Docker caches this layer separately. When you edit app.py, Docker skips
# this expensive pip install and jumps straight to Layer 3.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model (~90 MB from HuggingFace Hub).
# Baking it here means the first customer query starts instantly rather
# than triggering a 30-second download inside the running container.
RUN python -c \
    "from sentence_transformers import SentenceTransformer; \
     SentenceTransformer('all-MiniLM-L6-v2')"

# ── Layer 3: Application ──────────────────────────────────────────────────────

# Application source code
COPY app.py .
COPY wealthdesk/ wealthdesk/
COPY langgraph.json .

# MCP server lives alongside app.py so the COPY above works within
# this build context (Docker cannot reach files outside the context directory).
COPY mcp_server.py .

# Policy documents and data scripts
COPY data/ data/

# Build the SQLite database and the ChromaDB vector store at image build time.
# Both scripts are idempotent — running them twice is safe.
# Baking data into the image means the container starts with data ready,
# with no external database dependency. (In production you would use an
# external RDS / managed ChromaDB instead.)
RUN python data/seed.py && python data/ingest.py

# ── Runtime ───────────────────────────────────────────────────────────────────

EXPOSE 8501

# Cloud platforms (Render, Railway, Cloud Run) poll this endpoint to decide
# when the container is ready to receive traffic.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
