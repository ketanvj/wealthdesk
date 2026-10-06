"""
s15/tests/test_s15.py
---------------------
Tests for Session 15: Cloud Deployment.

Run with:
    pytest s15/tests/ -v

All tests are pure Python — no live LLM calls, no Docker daemon required.

Test groups:
  TestDockerfile          -- solution Dockerfile has all required elements
  TestStarterDockerfile   -- starter Dockerfile has the 5 student TODOs
  TestGracefulKeyError    -- GROQ_API_KEY check appears before wealthdesk import
  TestMCPPath             -- mcp_server.py co-located; path contains no "s07"
  TestBuildInputState     -- regression: build_input_state includes blocked_reason
  TestAgentGraph          -- build_graph() compiles; guard is the entry point
"""
import importlib.util
import sys
from pathlib import Path

SOLUTION_DIR = Path(__file__).parent.parent / "solution"
STARTER_DIR  = Path(__file__).parent.parent / "starter"

# Wipe any previously loaded wealthdesk modules so we get the s15 version.
for _k in list(sys.modules):
    if _k == "wealthdesk" or _k.startswith("wealthdesk."):
        sys.modules.pop(_k)

# Load app.py without running Streamlit — same technique as s14 tests.
_spec = importlib.util.spec_from_file_location("app", SOLUTION_DIR / "app.py")
_app  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_app)

build_input_state  = _app.build_input_state
get_thread_config  = _app.get_thread_config
compliance_badge   = _app.compliance_badge
guard_badge        = _app.guard_badge
needs_human_review = _app.needs_human_review
format_route_label = _app.format_route_label

from wealthdesk.agent  import build_graph    # noqa: E402
from wealthdesk.config import MCP_SERVER_PATH  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# TestDockerfile
# ---------------------------------------------------------------------------

class TestDockerfile:
    """Solution Dockerfile must be production-safe and self-contained."""

    DF = SOLUTION_DIR / "Dockerfile"

    def _text(self) -> str:
        assert self.DF.exists(), "Dockerfile not found in s15/solution/"
        return _read(self.DF)

    def test_base_image(self):
        assert "FROM python:3.11-slim" in self._text()

    def test_workdir(self):
        assert "WORKDIR /app" in self._text()

    def test_pip_install(self):
        text = self._text()
        assert "COPY requirements.txt" in text
        assert "pip install" in text

    def test_embedding_model_predownload(self):
        text = self._text()
        assert "SentenceTransformer" in text, \
            "Embedding model must be pre-downloaded during build to avoid cold-start delay"

    def test_seed_and_ingest_run(self):
        text = self._text()
        assert "seed.py" in text and "ingest.py" in text, \
            "data/seed.py and data/ingest.py must be executed during the build"

    def test_expose_8501(self):
        assert "EXPOSE 8501" in self._text()

    def test_cmd_streamlit(self):
        text = self._text()
        assert "streamlit" in text.lower()
        assert "run" in text
        assert "0.0.0.0" in text, "Streamlit must bind to 0.0.0.0 to accept external traffic"

    def test_headless_mode(self):
        assert "headless" in self._text(), \
            "--server.headless=true must be set so Streamlit doesn't try to open a browser"

    def test_no_groq_api_key_in_dockerfile(self):
        import re
        text = self._text()
        # Comments may mention GROQ_API_KEY — that's fine. Only ENV/ARG directives bake it in.
        baked = re.search(r"^\s*(ENV|ARG)\s+GROQ_API_KEY", text, re.MULTILINE)
        assert not baked, \
            "GROQ_API_KEY must never be baked into the image via ENV or ARG; pass it at runtime only"

    def test_mcp_server_copy(self):
        assert "mcp_server.py" in self._text(), \
            "mcp_server.py must be COPY'd — it lives alongside app.py in s15"


# ---------------------------------------------------------------------------
# TestStarterDockerfile
# ---------------------------------------------------------------------------

class TestStarterDockerfile:
    """Starter Dockerfile must have the 5 student TODOs and the pre-written lines."""

    DF = STARTER_DIR / "Dockerfile"

    def _text(self) -> str:
        assert self.DF.exists(), "Dockerfile not found in s15/starter/"
        return _read(self.DF)

    def test_has_todos(self):
        text = self._text()
        assert text.count("TODO") >= 5, "Starter must have at least 5 student TODOs"

    def test_prewritten_apt_install(self):
        assert "apt-get install" in self._text(), \
            "System dependency install (apt-get) should be pre-written for students"

    def test_prewritten_model_download(self):
        assert "SentenceTransformer" in self._text(), \
            "Embedding model pre-download should be pre-written for students"

    def test_prewritten_seed_ingest(self):
        text = self._text()
        assert "seed.py" in text and "ingest.py" in text, \
            "seed.py / ingest.py RUN commands should be pre-written for students"

    def test_prewritten_healthcheck(self):
        assert "HEALTHCHECK" in self._text(), \
            "HEALTHCHECK should be pre-written so students don't need to know the syntax"

    def test_from_placeholder(self):
        assert "FROM ___" in self._text(), "TODO 1: FROM placeholder must be present"

    def test_workdir_placeholder(self):
        assert "WORKDIR ___" in self._text(), "TODO 2: WORKDIR placeholder must be present"

    def test_run_placeholder(self):
        assert "RUN ___" in self._text(), "TODO 3: RUN pip install placeholder must be present"

    def test_copy_placeholder(self):
        assert "COPY ___" in self._text(), "TODO 4: COPY placeholder must be present"

    def test_expose_placeholder(self):
        assert "EXPOSE ___" in self._text(), "TODO 5: EXPOSE placeholder must be present"

    def test_cmd_placeholder(self):
        assert "CMD ___" in self._text(), "TODO 5: CMD placeholder must be present"


# ---------------------------------------------------------------------------
# TestGracefulKeyError
# ---------------------------------------------------------------------------

class TestGracefulKeyError:
    """GROQ_API_KEY must be validated BEFORE wealthdesk is imported."""

    APP_SRC = _read(SOLUTION_DIR / "app.py")

    def test_key_check_before_wealthdesk_import(self):
        src = self.APP_SRC
        key_check_pos   = src.find("GROQ_API_KEY")
        wealthdesk_pos  = src.find("from wealthdesk")
        assert key_check_pos != -1,  "GROQ_API_KEY check not found in app.py"
        assert wealthdesk_pos != -1, "wealthdesk import not found in app.py"
        assert key_check_pos < wealthdesk_pos, \
            "GROQ_API_KEY check must appear BEFORE 'from wealthdesk' import"

    def test_st_stop_called_on_missing_key(self):
        assert "st.stop()" in self.APP_SRC, \
            "st.stop() must be called when GROQ_API_KEY is missing"

    def test_st_error_called_on_missing_key(self):
        assert "st.error(" in self.APP_SRC, \
            "st.error() must inform the user how to configure the key"

    def test_error_message_mentions_docker(self):
        assert "docker" in self.APP_SRC.lower(), \
            "Error message should include Docker run instructions"

    def test_error_message_mentions_secrets(self):
        src = self.APP_SRC.lower()
        assert "secrets" in src or "settings" in src, \
            "Error message should mention Streamlit Cloud Secrets / Settings"


# ---------------------------------------------------------------------------
# TestMCPPath
# ---------------------------------------------------------------------------

class TestMCPPath:
    """mcp_server.py must be co-located with app.py; path must not traverse s07."""

    def test_mcp_server_exists_in_solution(self):
        mcp = SOLUTION_DIR / "mcp_server.py"
        assert mcp.exists(), \
            "mcp_server.py must live alongside app.py in s15/solution/ (self-contained build context)"

    def test_mcp_server_path_no_s07(self):
        path_str = str(MCP_SERVER_PATH)
        assert "s07" not in path_str, \
            f"MCP_SERVER_PATH must not reference s07/; got: {path_str}"

    def test_mcp_server_path_resolves_locally(self):
        assert MCP_SERVER_PATH.exists(), \
            f"MCP_SERVER_PATH ({MCP_SERVER_PATH}) does not point to a real file"

    def test_mcp_server_path_alongside_app(self):
        assert MCP_SERVER_PATH.parent == SOLUTION_DIR, \
            "MCP_SERVER_PATH should resolve to s15/solution/mcp_server.py"


# ---------------------------------------------------------------------------
# TestBuildInputState
# ---------------------------------------------------------------------------

class TestBuildInputState:
    """Regression: build_input_state must include blocked_reason (added in S14)."""

    def _state(self) -> dict:
        return build_input_state("test query")

    def test_customer_message(self):
        assert self._state()["customer_message"] == "test query"

    def test_blocked_reason_present(self):
        state = self._state()
        assert "blocked_reason" in state, \
            "blocked_reason missing from build_input_state — regression from S14"

    def test_blocked_reason_empty_string(self):
        assert self._state()["blocked_reason"] == ""

    def test_response_present(self):
        assert "response" in self._state()

    def test_retrieved_docs_present(self):
        assert "retrieved_docs" in self._state()

    def test_compliance_status_present(self):
        assert "compliance_status" in self._state()

    def test_specialist_present(self):
        assert "specialist" in self._state()


# ---------------------------------------------------------------------------
# TestAgentGraph
# ---------------------------------------------------------------------------

class TestAgentGraph:
    """build_graph() must compile and have guard as the entry point."""

    def test_build_graph_compiles(self):
        graph = build_graph(checkpointer=None)
        assert graph is not None

    def test_guard_node_present(self):
        graph = build_graph(checkpointer=None)
        assert "guard" in graph.get_graph().nodes, \
            "guard node must be present — it was introduced in S14"

    def test_guard_is_entry_point(self):
        graph = build_graph(checkpointer=None)
        g = graph.get_graph()
        # In LangGraph, the entry point is represented as an edge from __start__
        entry_nodes = [edge.target for edge in g.edges if edge.source == "__start__"]
        assert "guard" in entry_nodes, \
            "guard must be the entry point (edge from __start__ → guard)"

    def test_no_checkpointer_by_default(self):
        # build_graph(None) must not raise and must return a compiled graph
        # Studio compatibility: compiled graph with no checkpointer is accepted
        graph = build_graph(checkpointer=None)
        assert hasattr(graph, "invoke")


# ---------------------------------------------------------------------------
# TestAppHelpers
# ---------------------------------------------------------------------------

class TestAppHelpers:
    """Helper functions carried forward from S14 — spot-check correctness."""

    def test_compliance_badge_pass(self):
        assert compliance_badge("PASS") == "✅ Compliant"

    def test_compliance_badge_revised(self):
        assert compliance_badge("REVISED") == "⚠️ Revised"

    def test_compliance_badge_fail(self):
        assert "❌" in compliance_badge("FAIL: something")

    def test_guard_badge_pii(self):
        assert "PII" in guard_badge("pii")

    def test_guard_badge_injection(self):
        badge = guard_badge("injection")
        assert badge and "Blocked" in badge

    def test_guard_badge_empty(self):
        assert guard_badge("") == ""

    def test_needs_human_review_true(self):
        assert needs_human_review({"compliance_status": "REVISED"})

    def test_needs_human_review_false(self):
        assert not needs_human_review({"compliance_status": "PASS"})

    def test_format_route_label_blocked(self):
        label = format_route_label({"blocked_reason": "pii", "specialist": "guard"})
        assert "Guard" in label or "Blocked" in label

    def test_format_route_label_clean(self):
        label = format_route_label({
            "blocked_reason": "",
            "specialist": "Documents Agent",
            "compliance_status": "PASS",
        })
        assert "Documents Agent" in label
