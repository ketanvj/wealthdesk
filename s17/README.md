# S17 — Tier 2 SEBI Compliance: RAG-Based Regulatory Judgment

**Reference session — self-study only. Not taught in class.**

> This session extends WealthDesk's compliance layer from S09's phrase filter
> to a two-track retrieval system that consults actual SEBI regulation documents.
> It is a practical blueprint for production-grade AI compliance in financial services.

---

## Why This Exists

S09's compliance checker works like this:

```python
BANNED_PHRASES = ["guaranteed return", "risk-free", "assured profit", ...]
for phrase in BANNED_PHRASES:
    if phrase in response.lower():
        flag()
```

This catches obvious violations. But consider:

> "Our Fixed Deposits offer stable, consistent returns and your capital is fully protected."

- No banned phrase fires (`"capital is fully protected"` is not on the list)
- The response passes S09's compliance check
- It **violates SEBI IA Regulations 2013, Regulation 22(1)** — prohibition on guaranteed returns

Phrase filters can't catch paraphrase violations. The regulation is not a word list;
it's a legal concept. The only way to check against the concept is to retrieve the
regulation and ask an LLM to reason about it.

---

## Two-Track Architecture

```
Draft response + query_type
        │
        ├── Track 1: Deterministic retrieval ──────────────────►┐
        │   • No LLM, no embedding, zero retrieval miss        │
        │   • query_type → source files → all chunks from     │
        │     those files fetched directly from vectorstore    │
        │   • RATES always pulls rate_disclosure_requirements  │
        │   • POLICY always pulls fair_practices + ia_regs     │
        │                                                       │
        └── Track 2: Hypothesis-driven retrieval ─────────────►┤
            • LLM generates: "What might this violate?"        │
            • That hypothesis is the search query              │
            • ChromaDB semantic search on the hypothesis       │
            • Returns top-K chunks closest to the violation    │
                                                               │
                    Merge + deduplicate                        │
                           │◄──────────────────────────────────┘
                           ▼
              Judge LLM + regulation context
                           │
             COMPLIANT  or  VIOLATION: <regulation cited>
```

### Track 1 — Deterministic

```python
QUERY_TYPE_TO_SOURCES = {
    "RATES":   ["rate_disclosure_requirements.md", "ia_regulations_2013.md"],
    "POLICY":  ["rbi_fair_practices.md", "investment_advice_prohibitions.md"],
    "COMPLEX": ["investment_advice_prohibitions.md", "ia_regulations_2013.md"],
}
```

Rate queries **always** pull rate-disclosure regulations. You never miss a rate-disclosure
violation because the regulations are always in the judge's context, regardless of what
the response says.

**Tradeoff:** This retrieves potentially irrelevant chunks when there's no violation.
The judge LLM is smart enough to return COMPLIANT when the regulations don't apply.
The cost is extra tokens. For compliance, correctness beats efficiency.

### Track 2 — Hypothesis-Driven

```python
# 1. Ask LLM to hypothesize a violation
hypothesis = llm("What regulation might this response violate?")
# → "Potential violation: guaranteed returns language, possibly Reg 22(1)"

# 2. Strip the prefix and search
query = "guaranteed returns language regulation 22"
docs  = sebi_vectorstore.similarity_search(query, k=4)
```

Track 2 catches violations in unexpected domains — a RATES-classified query that
accidentally gives investment advice, for example. Track 1 wouldn't catch it because
investment advice regulations aren't in the RATES source list.

---

## The Knowledge Cutoff Problem

Track 2 has a fundamental limitation:

```
SEBI issues new circular in 2025
        │
        ├── You add it to sebi_regulations/ and re-ingest
        │   ✓ The circular is now in the vectorstore
        │
        └── Track 2's hypothesis generator is a pre-2025 LLM
            ✗ The LLM doesn't know this circular exists
            ✗ It won't hypothesize a violation under it
            ✗ The circular is never retrieved
            ✗ Violation missed
```

This is not a retrieval failure — the regulation is retrievable. It's a **generation
failure**: the hypothesis generator cannot hypothesize violations it doesn't know about.

### Four Mitigations

| # | Mitigation | How | Tradeoff |
|---|---|---|---|
| 1 | **Exhaustive category retrieval** | Extend Track 1 to fetch ALL regulations for the domain — not just the key sources | Zero miss for known domains; more tokens, latency |
| 2 | **BM25 hybrid search** | Add keyword (BM25) search alongside semantic search — new circulars with new terminology get found by term frequency even if semantically distant from hypothesis | Needs `langchain-community[bm25]`, ~30% more retrieval time |
| 3 | **Few-shot hypothesis prompting** | Add examples from actual regulatory corpus to the hypothesis prompt — anchors the LLM's vocabulary to current regulation language | Reduces miss rate; doesn't eliminate it for truly novel regulations |
| 4 | **Regulation-keyed lookup** | Maintain a code-level map: `if word X in response → always include regulation Y` | Most reliable for known trigger words; becomes a maintenance burden over time |

**None of these fully solve the problem.** The knowledge cutoff gap is a fundamental
architectural limitation of LLM-based compliance systems. Production systems combine
multiple mitigations and include human oversight for high-stakes decisions.

---

## What Changed from S16

| File | Change |
|------|--------|
| `wealthdesk/compliance.py` | **New** — two-track retrieval + judge LLM |
| `wealthdesk/nodes.py` | `call_compliance_agent` → `call_tier2_compliance_agent` |
| `wealthdesk/agent.py` | Same graph topology, new compliance node name |
| `wealthdesk/state.py` | Added `sebi_citations: list[str]` field |
| `wealthdesk/config.py` | Added `SEBI_VECTORSTORE_DIR` |
| `main.py` | `ChatResponse` includes `sebi_citations` |
| `ingest_sebi.py` | **New** — ingests regulation docs into SEBI vectorstore |
| `data/sebi_regulations/` | **New** — four regulation reference documents |
| Everything else | Unchanged from S16 |

---

## Running the Reference Implementation

### Setup (first time only)

```bash
cd s17/solution

# 1. Copy and fill in env vars
cp .env.example .env
# Edit .env: add GROQ_API_KEY

# 2. Install dependencies
pip install -r requirements.txt

# 3. Build SEBI vectorstore
python ingest_sebi.py
# → [Ingest] Vectorstore saved to data/sebi_vectorstore/
```

### Start the system

```bash
# Terminal 1 — MCP server (rates + branch tools)
python mcp_server.py

# Terminal 2 — FastAPI
uvicorn main:app --reload --port 8000

# Browser
open http://localhost:8000
```

### Run tests

```bash
# Unit tests (no API key needed — mocked LLM)
python -m pytest ../tests/test_tier2_compliance.py -v

# Live eval (both servers must be running, GROQ_API_KEY required)
python ../tests/live_eval.py
```

---

## Reading the Compliance Output

Every `/chat` response now includes `sebi_citations`:

```json
{
  "response": "BNB's home loan starts from 8.5% p.a., subject to credit score...",
  "specialist": "rates_agent",
  "compliance_status": "COMPLIANT",
  "sebi_citations": ["rate_disclosure_requirements.md", "ia_regulations_2013.md"],
  "blocked_reason": ""
}
```

`sebi_citations` lists which regulation files the judge consulted. Empty for escalated,
declined, or blocked responses. Useful for:
- Audit trail ("which regulations were checked?")
- Debugging ("why was this flagged?")
- LangSmith tracing (see regulation retrieval in the trace)

---

## Study Guide

Work through the code in this order:

1. **Read `data/sebi_regulations/ia_regulations_2013.md`** — focus on Regulation 22 (guarantee prohibition) and Regulation 23 (risk disclosure). These are the most commonly triggered.

2. **Read `wealthdesk/compliance.py`** — the two track functions (`_track1_retrieve`, `_track2_retrieve`) and how they're combined in `tier2_compliance_check`.

3. **Run the unit tests** — `test_tier2_compliance.py` shows each component in isolation with mock LLMs. Read the assertions before running.

4. **Start the system and test edge cases manually:**
   - "Our FD guarantees 7% returns" — should trigger Regulation 22
   - "This FD is the best and most suitable option for you" — should trigger investment advice prohibition
   - "BNB home loan starts from 8.5% p.a., subject to credit assessment" — should be COMPLIANT

5. **Read about the knowledge cutoff limitation** (above) and consider: if SEBI issues a new circular about AI disclosure requirements, what would you add to this system?

6. **Extension exercise:** Implement Mitigation #4 (regulation-keyed lookup). Add a `TRIGGER_WORD_MAP = {"guaranteed": "ia_regulations_2013.md", "suitable for you": "investment_advice_prohibitions.md"}` and merge those sources into Track 1 before calling Track 2.

---

## Connection to S09

S09's phrase filter (`SEBI_BANNED_PHRASES`) runs in `_check_compliance_logic()` in nodes.py.
S17's Tier 2 checker replaces this entirely.

The S09 approach was:
- Fast (no LLM call in compliance)
- Zero false negatives for exact phrases
- High false negative rate for paraphrase

The S17 approach is:
- Slower (2 LLM calls: hypothesis + judge)
- Zero false negatives for the domains in the Track 1 map
- Some false negative rate for novel post-cutoff regulations

In production, you'd run both: S09's phrase filter as a first pass (cheap), Tier 2 as
a second pass (comprehensive). The two layers are complementary, not alternatives.

---

## Regulatory Documents in This Session

| File | Coverage |
|------|----------|
| `ia_regulations_2013.md` | SEBI IA Regulations: Reg 22 guarantee prohibition, Reg 23 risk disclosure, Reg 33 records |
| `rbi_fair_practices.md` | RBI rate disclosure, teaser rate prohibition, AI/chatbot responsibility |
| `investment_advice_prohibitions.md` | SEBI 2021 circular: prohibited phrases, bank permissions, chatbot scope |
| `rate_disclosure_requirements.md` | Loan and deposit rate communication requirements, knowledge cutoff risk |

> **Note:** These documents are teaching references based on publicly available SEBI and RBI
> guidelines, simplified for educational use. Always consult the official Gazette notifications
> for authoritative legal text.
