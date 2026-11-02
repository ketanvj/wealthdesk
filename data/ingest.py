"""
data/ingest.py
--------------
Ingests BNB policy documents into ChromaDB.

Run independently of seed.py (no dependency between them):
    python data/ingest.py

What this script does:
  1. Reads all .md files from data/documents/
  2. Splits them into overlapping chunks (better retrieval precision)
  3. Generates embeddings using a free local model (all-MiniLM-L6-v2)
  4. Writes the vector store to data/vectorstore/ (persisted to disk)

First run: downloads ~90 MB of embedding model weights to ~/.cache/huggingface/.
Subsequent runs: uses the cache. No internet connection required after first run.

The script is idempotent -- it deletes and rebuilds the vector store on every run.
This mirrors seed.py's DROP TABLE / CREATE TABLE pattern. Participants can add or
edit a document and re-run ingest.py to make the change searchable, without any
leftover stale chunks from the previous run.

Why local embeddings (HuggingFace) rather than OpenAI embeddings?
  Using OpenAI for embeddings would require participants to have an OpenAI key
  from Session 1. We delay the OpenAI key requirement to Session 6 (eval judge).
  all-MiniLM-L6-v2 is fast, free, and produces good retrieval quality for
  English policy documents of this length.

Why are rates NOT in these documents?
  Rates are in data/bnb_data.db (see seed.py). Putting "home loan: 8.5%" in a
  document would create two sources of truth. When the rate changes (seed.py is
  re-run), the document would still say 8.5% while the database says something
  else. The compliance node (US-08, Session 9) specifically checks that the
  agent never retrieves stale rate information from documents.

Windows path note:
  ChromaDB's persist_directory requires a string. We pass str(VECTOR_DIR) where
  VECTOR_DIR is a pathlib.Path object. This gives the correct path on Windows
  without manual string manipulation.
"""

import re
import shutil
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

load_dotenv()

DATA_DIR   = Path(__file__).parent
DOCS_DIR   = DATA_DIR / "documents"
VECTOR_DIR = DATA_DIR / "vectorstore"

EMBED_MODEL   = "all-MiniLM-L6-v2"
CHUNK_SIZE    = 500   # characters per chunk
CHUNK_OVERLAP = 50    # overlap between consecutive chunks

# Smaller chunks (500 chars) give more precise retrieval but may split context
# across chunks. 50-char overlap ensures a sentence that straddles a boundary
# is preserved in at least one chunk.

# ---------------------------------------------------------------------------
# LLM09:2026 — Vector and Embedding Weaknesses: ingest-time content scanning
#
# OWASP 2026 Scenario #4 (RAG Repository Poisoning): an attacker contributes
# poisoned documents to the corpus. A matching query returns the modified
# content, whose instructions alter the LLM's output. As few as five poisoned
# documents achieved ~90% attack success against a knowledge base of millions.
#
# Defence: scan every chunk for injection patterns BEFORE storing it.
# Runtime framing in DOCS_SYSTEM_PROMPT (in nodes.py) is the second line of
# defence — this ingest-time scan is the first.
#
# Set SCAN_FOR_INJECTION = False to disable (not recommended in production).
# ---------------------------------------------------------------------------
SCAN_FOR_INJECTION = True

_INGEST_INJECTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"forget\s+everything",
    r"\byou\s+are\s+now\b",
    r"disregard\s+your\s+(system\s+)?prompt",
    r"(reveal|show|tell)\s+(me\s+)?(your\s+)?(system\s+prompt|instructions)",
    r"new\s+(persona|identity|role)\b",
    r"act\s+as\s+.*with\s+no\s+(restrictions|limits)",
]]


# Metadata map: filename → doc_type and product tags.
# Used for metadata filtering in the hybrid retriever (solutionhybridsearch).
# All sessions share this vectorstore; existing sessions ignore these extra fields.
DOCUMENT_METADATA: dict[str, dict] = {
    "home_loan_guide.md":   {"doc_type": "guide",  "product": "home_loan"},
    "personal_loan_guide.md": {"doc_type": "guide", "product": "personal_loan"},
    "car_loan_guide.md":    {"doc_type": "guide",  "product": "car_loan"},
    "fd_guide.md":          {"doc_type": "guide",  "product": "fd"},
    "faq.md":               {"doc_type": "faq",    "product": "general"},
    "bnb_policy.md":        {"doc_type": "policy", "product": "general"},
}


def load_documents() -> List[Document]:
    """Load every .md file in the documents directory.

    Each document is tagged with:
      source   : filename — appears in LangSmith traces so you can see which
                 document contributed to each agent response.
      doc_type : "guide" | "faq" | "policy" | "email_template" — used by the
                 hybrid retriever's metadata filter to restrict retrieval to the
                 right document category (e.g. only guides for customer queries).
      product  : "home_loan" | "car_loan" | "fd" | "loan" | "general" — used to
                 narrow retrieval further (e.g. only car_loan docs for car queries).
    """
    if not DOCS_DIR.exists():
        print(f"Error: Documents directory not found at {DOCS_DIR}", file=sys.stderr)
        print("Make sure you are running this script from the wealthdesk/ folder.", file=sys.stderr)
        sys.exit(1)

    docs = []
    md_files = sorted(DOCS_DIR.glob("*.md"))
    if not md_files:
        print(f"Error: No .md files found in {DOCS_DIR}", file=sys.stderr)
        sys.exit(1)

    for path in md_files:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            print(f"  Warning: {path.name} is empty -- skipping", file=sys.stderr)
            continue
        # extra: doc_type + product tags for this file, e.g. {"doc_type": "guide", "product": "home_loan"}
        # Falls back to {"doc_type": "other", "product": "general"} for any unregistered file.
        extra = DOCUMENT_METADATA.get(path.name, {"doc_type": "other", "product": "general"})
        # Merge source filename + extra tags into the Document's metadata dict.
        # These fields travel with every chunk and appear in LangSmith traces.
        # Example for home_loan_guide.md:
        #   doc.page_content : "# BNB Home Loan Guide\n\n## Who is Eligible..."
        #   doc.metadata     : {"source": "home_loan_guide.md", "doc_type": "guide", "product": "home_loan"}
        doc = Document(page_content=text, metadata={"source": path.name, **extra})
        docs.append(doc)
        print(f"  Loaded: {path.name:40s} ({len(text):,} chars)  [{extra['doc_type']}]")

    return docs


def split_documents(docs: List[Document]) -> List[Document]:
    """Split documents into chunks for retrieval.

    RecursiveCharacterTextSplitter tries to split at paragraph boundaries first,
    then sentence boundaries, then character boundaries. This preserves semantic
    context better than splitting at fixed character positions.
    """
    # RecursiveCharacterTextSplitter tries separators in order ("\n\n" → "\n" → " " → "")
    # so cuts land near natural boundaries. CharacterTextSplitter cuts at a fixed count
    # regardless of where a sentence ends — use that when strict size control matters more.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    return splitter.split_documents(docs)


def scan_chunks(chunks: List[Document]) -> List[Document]:
    """Remove chunks containing injection patterns before indexing (LLM09:2026).

    Each chunk is matched against _INGEST_INJECTION_PATTERNS. A chunk that
    matches is logged and dropped — it will not be stored in ChromaDB.

    Why here rather than at query time? A poisoned chunk already in the vector
    store can be retrieved by legitimate queries and feed adversarial
    instructions to the LLM. Blocking at ingest is the earliest and most
    effective control point; runtime framing in SYSTEM_PROMPT (nodes.py) is the
    fallback for content that slips through.
    """
    if not SCAN_FOR_INJECTION:
        return chunks

    clean, skipped = [], 0
    for chunk in chunks:
        matched = next(
            (p.pattern for p in _INGEST_INJECTION_PATTERNS
             if p.search(chunk.page_content)),
            None,
        )
        if matched:
            print(
                f"  [SCAN] BLOCKED chunk from "
                f"'{chunk.metadata.get('source', '?')}': "
                f"matched /{matched[:50]}/",
                file=sys.stderr,
            )
            skipped += 1
        else:
            clean.append(chunk)

    if skipped:
        print(
            f"\n  [SCAN] {skipped} chunk(s) blocked — injection patterns detected.\n"
            f"  [SCAN] Review the source documents and remove injected content.\n"
            f"  [SCAN] Set SCAN_FOR_INJECTION=False to bypass (not recommended).\n",
            file=sys.stderr,
        )
    return clean


def main() -> None:
    print("Ingesting BNB documents into ChromaDB")
    print(f"  Source : {DOCS_DIR}")
    print(f"  Target : {VECTOR_DIR}\n")

    # Delete the existing vector store before rebuilding. This makes the script
    # idempotent: running it twice produces the same result as running it once.
    # Without this, Chroma.from_documents() appends chunks to any existing
    # collection, causing duplicate retrieval results in Session 4.
    if VECTOR_DIR.exists():
        shutil.rmtree(VECTOR_DIR)
        print(f"  Cleared existing vector store (idempotent reset)\n")

    print("Loading documents...")
    docs = load_documents()

    # chunks: list of Document objects, each holding one text slice + inherited metadata
    chunks = split_documents(docs)
    print(f"\nSplit {len(docs)} documents into {len(chunks)} chunks")
    print(f"  chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}\n")

    # Overwrite chunks with the filtered list — any chunk containing injection
    # patterns is dropped here before it reaches the vector store.
    chunks = scan_chunks(chunks)
    print(f"  After ingest scan: {len(chunks)} chunks will be indexed\n")

    print(f"Loading embedding model: {EMBED_MODEL}")
    print("  First run downloads ~90 MB. Subsequent runs use cache.\n")

    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    print("Building vector store...")
    # Configure Chroma's HNSW index to use cosine similarity.
    #
    # During retrieval, Chroma compares the query embedding with every stored
    # embedding using this metric. Cosine measures the angle between vectors,
    # making it well-suited for semantic text similarity.
    #
    # This metric becomes part of the HNSW index structure when the collection
    # is created and cannot be changed later. Switching to a different metric
    # (e.g., L2) requires rebuilding the vector store.
    #
    # For the WealthDesk corpus, cosine also produces similarity scores that
    # separate meaningful queries from noise more cleanly, making thresholding
    # (e.g., 0.3) easier to tune.
    # hnsw - Hierarchical Navigable Small World)
    # hnsw:space sets the similarity metric for the HNSW index. Options:
    #   "cosine" — measures angle between vectors; best for semantic text similarity.
    #              Scores returned by similarity_search_with_relevance_scores are 0–1
    #              (higher = more similar). Used here.
    #   "l2"     — Euclidean (straight-line) distance; sensitive to vector magnitude,
    #              not just direction. ChromaDB default when hnsw:space is not set.
    #              Scores are distances (lower = more similar) — harder to threshold.
    #   "ip"     — Inner product (dot product); used when embeddings are pre-normalised.
    #              Less common; requires careful embedding model selection.
    #
    # This setting is permanent — changing it requires deleting vectorstore/ and
    # re-running ingest.py. The score threshold in config.py (0.3) is calibrated
    # for cosine; recalibrate if you switch metrics.
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(VECTOR_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )

    print(f"\nDone. {len(chunks)} chunks stored at {VECTOR_DIR}")
    print("Run 'python data/ingest.py' again after adding or editing documents.")
    print("\nSetup complete. Run 'python -m wealthdesk.agent' from inside s04/starter/ or s04/solution/ to start WealthDesk.")


if __name__ == "__main__":
    main()
