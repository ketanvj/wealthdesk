"""
WealthDesk -- Session 6: Baseline Evaluation (US-05)
=====================================================

What you build this session
  A structured evaluation pipeline that runs 40 questions from a golden
  dataset through the Session 5 WealthDesk agent, scores each response,
  and produces a pass-rate report broken down by question category.

  Routing is evaluated deterministically (COMPLEX and OUT_OF_SCOPE have
  canned responses with known keywords). SIMPLE responses are scored 1-5
  by an LLM judge. A response passes if it is correctly routed, scores
  >= 3 out of 5, and contains no forbidden content.

What is NOT here yet
  - Regression tests comparing scores across commits (Session 12)

Run
  python s06/solution/evaluate.py

  The script imports the built WealthDesk graph from s05/solution/main.py
  and runs each question with a fresh MemorySaver checkpointer so no
  prior conversation state leaks between evaluation items.

Golden dataset
  s06/data/golden_dataset.json  --  40 Q&A items:
    20 SIMPLE  (loan rates, FD rates, branch info, policy)
    10 COMPLEX (financial planning, eligibility)
    10 OUT_OF_SCOPE (off-topic, competitor comparisons)

How this file is organised
  1. Configuration        -- thresholds, paths, model choice
  2. LLM judge            -- the second LLM that scores SIMPLE responses
  3. Dataset loading      -- reads and validates golden_dataset.json
  4. Response evaluation  -- scores one response against one dataset item
  5. Evaluation runner    -- loops over all dataset items, calls the graph
  6. Report generation    -- aggregates results into a summary dict
  7. Entry point          -- wires everything together
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found. Check your .env file.")

# The judge LLM does not need tool calling — it only reads text and returns a
# score. We deliberately use a DIFFERENT model FAMILY from the agent:
#   agent  → openai/gpt-oss-120b  (OpenAI GPT architecture via Groq)
#   judge  → qwen/qwen3.8-27b     (Alibaba Qwen architecture — completely different)
# This is true cross-architecture LLM-as-judge: the two models were trained
# independently on different corpora by different organisations. A judge from
# the same family as the agent can be biased toward the agent's own output
# style and phrasing — it tends to rate outputs that "sound like itself" higher.
# Using a different architecture eliminates that systematic bias.
MODEL_NAME  = "qwen/qwen3.8-27b"

# PASS_SCORE: the minimum judge score for a SIMPLE response to be considered
# passing. Scale is 1-5 (defined in JUDGE_PROMPT below).
# 3 = "Acceptable: the key information is present but incomplete"
# We accept 3 because we want the evaluation to catch genuinely wrong answers
# (score 1-2), not penalise minor phrasing variations (which score 3-4).
# Raise this to 4 or 5 to make the evaluation stricter.
PASS_SCORE  = 3

DATA_DIR     = Path(__file__).parent.parent / "data"
DATASET_PATH = DATA_DIR / "golden_dataset.json"

# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

# Two LLMs are at work in this script:
#   1. The WealthDesk agent LLM (imported from s05) — answers customer questions
#   2. This judge LLM — evaluates the quality of those answers
#
# Keeping them separate means a weak agent model can be evaluated by a stronger
# judge model, and the judge's verdict is independent of how the answer was
# generated. This is the "LLM-as-judge" pattern — common in production evals.
#
# temperature=0.0  → deterministic output; same question always gets same score.
#                    Critical for reproducibility: if you re-run the eval and
#                    the score changes, you want that to reflect a real change
#                    in the agent, not random variation in the judge.
# max_tokens=300   → the judge only needs to output "SCORE: N\nREASON: ..."
#                    which is well under 300 tokens. Set conservatively at 300
#                    so any model has headroom to emit the two required lines.
judge_llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=MODEL_NAME,
    temperature=0.0,
    max_tokens=300,
)

# JUDGE_PROMPT uses three placeholders filled at call time:
#   {question}      -- the original customer question
#   {criteria_list} -- bullet list of what the response should cover
#   {response}      -- the agent's actual response
#
# The rubric maps scores to clear descriptions so the judge has no ambiguity.
# The strict two-line output format ("SCORE: N\nREASON: ...") makes parsing
# reliable — we don't need to regex-hunt through a paragraph of commentary.
JUDGE_PROMPT = """You are evaluating a banking AI assistant's response to a customer question.

Customer question:
{question}

The response should cover these points:
{criteria_list}

Assistant response:
{response}

Score the response on a scale of 1 to 5:
  5 = Excellent: all required points covered, factually accurate, professional
  4 = Good: most points covered, minor gaps
  3 = Acceptable: the key information is present but incomplete
  2 = Poor: missing important information or contains inaccuracies
  1 = Fail: refuses to answer, wrong information, or off-topic

Reply in exactly this format (two lines, no other text):
SCORE: <integer 1-5>
REASON: <one sentence explaining the score>"""


def parse_judge_response(output: str) -> tuple[int, str]:
    """Extract the integer score and one-line reason from the judge LLM output.

    Expected format:
      SCORE: 4
      REASON: The response correctly states the home loan rate and tenure.

    Why manual parsing instead of structured output / JSON mode?
    LangChain's .with_structured_output() adds schema overhead. For a
    two-field response (int + string) a simple line scan is more readable,
    easier to debug, and works across all Groq models without needing
    function-calling support.

    If parsing fails (judge returned unexpected text), returns (0, error string).
    Score is clamped to [1, 5] even if the LLM returns an out-of-range value —
    a safety net against a rogue "SCORE: 10" response.
    """
    score  = 0
    reason = "Could not parse judge output"
    for line in output.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("SCORE:"):
            try:
                raw = int(line.split(":", 1)[1].strip())
                # Clamp to valid range regardless of what the LLM returned
                score = max(1, min(5, raw))
            except ValueError:
                pass
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    return score, reason


def llm_judge(question: str, criteria: list[str], response: str) -> tuple[int, str]:
    """Ask the judge LLM to score a SIMPLE response.

    Formats the criteria as a bullet list so the judge can check each point
    individually rather than trying to hold a comma-separated string in mind.

    Returns (score, reason) where score is 1-5 and reason is a one-line string.
    Falls back to (0, error_message) on any exception so a single judge failure
    does not crash the entire evaluation run.
    """
    # Convert ["Mumbai", "Andheri West"] → "  - Mumbai\n  - Andheri West"
    # If a dataset item has no criteria, we still need to tell the judge
    # something rather than leaving the placeholder empty.
    criteria_list = "\n".join(f"  - {c}" for c in criteria) if criteria else "  - (none specified)"

    prompt = JUDGE_PROMPT.format(
        question=question,
        criteria_list=criteria_list,
        response=response,
    )
    # Retry up to 3 times: openai/gpt-oss-* occasionally returns an empty
    # response. A second call to the same prompt usually succeeds.
    for attempt in range(3):
        try:
            result = judge_llm.invoke([
                SystemMessage(content="You are a strict but fair evaluation judge."),
                HumanMessage(content=prompt),
            ])
            score, reason = parse_judge_response(result.content)
            if score > 0:
                return score, reason
        except Exception as e:
            return 0, f"Judge error: {e}"
    return 0, "Judge returned empty output after 3 attempts"


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

# Every dataset item must have these five fields. If any are missing the whole
# dataset is rejected at load time — better to fail fast with a clear message
# than to silently skip items or get a KeyError mid-evaluation.
REQUIRED_FIELDS = {"id", "query", "expected_route", "category", "criteria"}


def load_dataset(path: Path) -> list[dict]:
    """Load and validate the golden dataset from a JSON file.

    A "golden dataset" is a hand-curated set of questions with known correct
    answers (or routing expectations). "Golden" means the expected outcomes
    are trusted ground truth — not generated by the model being evaluated.

    Each item in golden_dataset.json has:
      id             : unique identifier, e.g. "S01", "C03", "O07"
      query          : the customer question to send to the agent
      expected_route : "SIMPLE", "COMPLEX", or "OUT_OF_SCOPE"
      category       : topic label used for grouping in the report
                       (e.g. "loan_rates", "branch", "oos")
      criteria       : list of strings that must appear in a passing response
                       (for SIMPLE: key facts; for COMPLEX/OOS: canned keywords)
      must_not_contain (optional): strings that must NOT appear
                       (e.g. competitor bank names, "I cannot help")

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if any item is missing required fields.
    """
    # Opens the JSON file and parses it into a Python list. Each element is
    # one dict representing one row from golden_dataset.json. The `with` block
    # closes the file automatically when done.
    with open(path, encoding="utf-8") as f:
        dataset = json.load(f)

    # enumerate() gives both the row index (i) and the row itself (item).
    # The index is only used in the error message so you know which row failed.
    for i, item in enumerate(dataset):
        # Set subtraction: REQUIRED_FIELDS minus the keys actually present
        # in this row. Result is the set of fields that are required but missing.
        # If all five fields are present, missing is an empty set.
        missing = REQUIRED_FIELDS - set(item.keys())
        if missing:
            # Fail immediately with a clear message rather than a confusing
            # KeyError later mid-evaluation. .get('id', '?') handles the edge
            # case where even the 'id' field itself is absent.
            raise ValueError(
                f"Golden dataset item {i} (id={item.get('id', '?')}) "
                f"is missing fields: {missing}"
            )
    return dataset


# ---------------------------------------------------------------------------
# Response evaluation
# ---------------------------------------------------------------------------

def evaluate_response(item: dict, result: dict) -> dict:
    """Score a single graph result against its golden dataset entry.

    Returns a dict with:
      id, query, category, expected_route, actual_route,
      route_correct, score, reason, forbidden_found, passed, response

    Two scoring strategies — chosen based on expected_route:

    COMPLEX / OUT_OF_SCOPE  →  Deterministic keyword check
      These routes always produce the same canned response (ESCALATE_RESPONSE
      or DECLINE_RESPONSE). There is nothing for an LLM judge to evaluate —
      either the exact keywords are present or they are not. Score is 5 if all
      criteria keywords are found, 1 if any are missing. No LLM call needed.

    SIMPLE  →  LLM-as-judge (1-5 scale)
      SIMPLE responses vary based on what the agent retrieved or which tools
      it called. A keyword check alone is too brittle — the agent might give a
      correct answer without using the exact expected phrasing. The judge LLM
      reads the full response and scores quality against the criteria list.

    Pass logic (a response must satisfy ALL three):
      1. route_correct    — the agent routed to the expected path
      2. score >= PASS_SCORE — judge gave a passing score (SIMPLE only;
                              COMPLEX/OOS use criteria_met as the score gate)
      3. no forbidden content — none of the must_not_contain strings appeared
    """
    # Pull the route the agent actually took and the response it returned.
    # .get() with a default avoids KeyError if the graph errored and returned
    # an incomplete dict.
    actual_route  = result.get("query_type", "UNKNOWN")
    response      = result.get("response", "")

    # Route check: did the classifier send this to the right path?
    # Simple string equality — "SIMPLE" == "SIMPLE", "COMPLEX" == "COMPLEX", etc.
    route_correct = (actual_route == item["expected_route"])

    # .get() with [] default so the code works even if a dataset item omits
    # these optional fields (must_not_contain is always optional).
    criteria = item.get("criteria", [])
    must_not = item.get("must_not_contain", [])

    # all() returns True only if every element in the generator is True.
    # c.lower() in response.lower() is a case-insensitive substring check —
    # "mumbai" matches "Mumbai", "MUMBAI", etc.
    # If criteria is empty, all() returns True (vacuously satisfied).
    criteria_met = all(c.lower() in response.lower() for c in criteria)

    # List comprehension that collects every forbidden string that actually
    # appeared in the response. We keep the list (not just a bool) so the
    # report can print exactly which word triggered the failure.
    # A non-empty list always causes failure regardless of route or score.
    # Example: if "HDFC" appears in a BNB response, the agent hallucinated a
    # competitor — an automatic fail even if the judge scores it 5/5.
    forbidden_found = [f for f in must_not if f.lower() in response.lower()]

    if item["expected_route"] in ("COMPLEX", "OUT_OF_SCOPE"):
        # Deterministic scoring: no LLM call needed.
        # The canned responses are fixed strings — we just check keywords.
        # Score is either 5 (all keywords present) or 1 (any keyword missing).
        score  = 5 if criteria_met else 1
        reason = "Canned response criteria met." if criteria_met else "Canned response keyword missing."
        # All three conditions must be true: right route, keywords present, no forbidden words.
        passed = route_correct and criteria_met and not forbidden_found
    else:
        # SIMPLE: delegate quality scoring to the LLM judge.
        # llm_judge returns (score, reason) — a tuple unpacked into two variables.
        score, reason = llm_judge(item["query"], criteria, response)
        # not forbidden_found is True when the list is empty (no forbidden words found).
        passed = route_correct and score >= PASS_SCORE and not forbidden_found

    # Return all fields as a flat dict — one row in the final results list.
    # Every field is included so callers can filter/group without re-querying.
    return {
        "id":              item["id"],           # str  — e.g. "S01", "C03", "O07"
        "query":           item["query"],         # str  — the original customer question
        "category":        item["category"],      # str  — e.g. "loan_rates", "branch", "oos"
        "expected_route":  item["expected_route"],# str  — "SIMPLE", "COMPLEX", or "OUT_OF_SCOPE"
        "actual_route":    actual_route,          # str  — what the classifier actually returned
        "route_correct":   route_correct,         # bool — True if actual_route == expected_route
        "score":           score,                 # int  — 1-5 (LLM judge) or 5/1 (deterministic)
        "reason":          reason,                # str  — one-line explanation from the judge
        "forbidden_found": forbidden_found,       # list — forbidden strings that appeared ([] if none)
        "passed":          passed,                # bool — True only if route + score + forbidden all pass
        "response":        response,              # str  — the full agent response text
    }


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------

def run_evaluation(graph, dataset: list[dict]) -> list[dict]:
    """Invoke the graph on every dataset item and return a list of eval results.

    State isolation: each item gets a unique thread_id ("eval-S01", "eval-C03",
    etc.). LangGraph's checkpointer stores conversation history keyed by
    thread_id. Without unique IDs, question 2 would see question 1's history
    and the agent would respond as if mid-conversation. With unique IDs, every
    question starts with a clean slate — exactly what evaluation requires.

    Error handling: if the graph raises an exception for one item, we record
    the error as the response and continue. A single broken question should not
    abort the entire 40-item run.
    """
    results = []
    for item in dataset:
        # Each question gets its own thread_id so LangGraph's checkpointer
        # gives it a clean conversation history. Without this, question 2
        # would inherit question 1's history and respond as if mid-conversation.
        config = {"configurable": {"thread_id": f"eval-{item['id']}"}}
        try:
            # Invoke the graph exactly as a real user would. "response": "" is
            # the initial empty value for the response field in WealthDeskState.
            graph_result = graph.invoke(
                {"customer_message": item["query"], "response": ""},
                config=config,
            )
        except Exception as e:
            # If this one question crashes the graph, record it as an ERROR
            # result and continue — don't abort the entire 40-item run.
            graph_result = {
                "query_type": "ERROR",
                "response": f"Graph error: {e}",
            }
        # Score the graph's output against the golden dataset entry.
        eval_result = evaluate_response(item, graph_result)
        # Print a one-line progress update so you can watch the run live.
        status = "PASS" if eval_result["passed"] else "FAIL"
        print(f"  [{status}] {item['id']}: {item['query'][:60]}")
        results.append(eval_result)
    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: list[dict]) -> dict:
    """Aggregate evaluation results into a structured report dict.

    Returns:
      total          : total number of questions evaluated
      passed         : number that passed all three pass conditions
      failed         : total - passed
      pass_rate      : passed / total as a float (0.0-1.0)
      average_score  : mean judge score for SIMPLE questions only
                       (COMPLEX and OOS scores are always 1 or 5 by formula,
                       not real LLM judgement, so they would skew the average)
      by_category    : dict of {category: {total, passed, pass_rate}}
                       used for the bar chart in print_report
      failures       : list of dicts for each failed item — id, query, reason,
                       score, actual_route. Printed at the bottom of the report
                       so you can diagnose failures without reading all 40 lines.
    """
    total  = len(results)
    # sum(1 for r in results if r["passed"]) counts how many results have
    # passed=True. Equivalent to len([r for r in results if r["passed"]]) but
    # without building a temporary list in memory.
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    # Collect judge scores for SIMPLE questions only.
    # COMPLEX and OOS scores are always 1 or 5 by formula (not real LLM
    # judgement), so including them would artificially inflate the average.
    # score > 0 excludes parse failures where the judge returned 0.
    simple_scores = [
        r["score"] for r in results
        if r["category"] not in ("complex", "oos") and r["score"] > 0
    ]
    # Guard against division by zero if there are no SIMPLE questions at all.
    avg_score = sum(simple_scores) / len(simple_scores) if simple_scores else 0.0

    # Build per-category pass/fail counts by iterating once over all results.
    # We start with an empty dict and add keys on first encounter so the report
    # automatically adapts if new categories are added to the dataset.
    by_category: dict[str, dict] = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            # First time we see this category — initialise its counters.
            by_category[cat] = {"total": 0, "passed": 0}
        by_category[cat]["total"] += 1
        if r["passed"]:
            by_category[cat]["passed"] += 1
    # Compute pass_rate in a second pass once totals are final.
    for cat, data in by_category.items():
        data["pass_rate"] = data["passed"] / data["total"] if data["total"] else 0.0

    # List comprehension that collects only the failed results, keeping just
    # the fields needed for the failure report (not the full response text).
    failures = [
        {
            "id":           r["id"],
            "query":        r["query"],
            "reason":       r["reason"],   # judge's one-line explanation
            "score":        r["score"],
            "actual_route": r["actual_route"],
        }
        for r in results if not r["passed"]
    ]

    return {
        "total":         total,
        "passed":        passed,
        "failed":        failed,
        # pass_rate as 0.0-1.0 float; print_report formats it as % with :.0%
        "pass_rate":     passed / total if total else 0.0,
        "average_score": round(avg_score, 2),
        "by_category":   by_category,
        "failures":      failures,
    }


def print_report(report: dict) -> None:
    """Print the evaluation report to stdout in a readable format.

    The bar chart under "By category:" encodes pass/fail visually:
      '#' = one passing test case in that category
      '-' = one failing test case in that category
    Bar length equals the total number of questions in the category, so
    categories with more questions have longer bars.

    Example:
      loan_rates  [#####] 5/5 (100%)   -- all 5 passed
      branch      [###--] 3/5  (60%)   -- 2 failed

    Failed items are listed below the chart with their judge reason so you
    know immediately what went wrong without re-reading raw responses.
    """
    print("\n" + "=" * 60)
    print("  WealthDesk Baseline Evaluation Report")
    print("=" * 60)
    print(f"  Total questions : {report['total']}")
    print(f"  Passed          : {report['passed']}")
    print(f"  Failed          : {report['failed']}")
    # :.0% formats a float as a percentage with no decimal places: 0.975 → "98%"
    print(f"  Pass rate       : {report['pass_rate']:.0%}")
    print(f"  Avg SIMPLE score: {report['average_score']} / 5")
    print()
    print("  By category:")
    # sorted() prints categories alphabetically so the order is stable across runs.
    for cat, data in sorted(report["by_category"].items()):
        # '#' * passed builds the filled portion: e.g. "###" for 3 passing.
        # '-' * (total - passed) builds the empty portion: e.g. "--" for 2 failing.
        # Concatenated: "###--" inside brackets → [###--] 3/5 (60%)
        bar = "#" * data["passed"] + "-" * (data["total"] - data["passed"])
        # {cat:<15} left-aligns the category name in a 15-character wide column
        # so all bars line up regardless of category name length.
        print(f"    {cat:<15} [{bar}] {data['passed']}/{data['total']} ({data['pass_rate']:.0%})")

    # Only print the failures section if there are any — keeps output clean on a perfect run.
    if report["failures"]:
        print()
        print(f"  Failed items ({len(report['failures'])}):")
        for f in report["failures"]:
            # [:55] truncates long queries so each failure fits on two lines.
            print(f"    {f['id']}: (route={f['actual_route']}, score={f['score']}) {f['query'][:55]}")
            print(f"         {f['reason']}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Load the golden dataset, build the S05 graph, run evaluation, print report.

    Why sys.path.insert?
    S06's evaluate.py needs to import WealthDesk from S05. They live in
    separate directories (s05/solution/ and s06/solution/) and neither is
    installed as a Python package. sys.path.insert(0, ...) adds the s05
    solution directory to Python's module search path so that
    `from wealthdesk.agent import build_graph` resolves correctly.
    The 0 means "look here first" — before site-packages — which avoids
    picking up an older installed version if one exists.

    Why MemorySaver and not SqliteSaver?
    MemorySaver keeps checkpoints in RAM. SqliteSaver writes to a file and
    requires a database path. For evaluation we don't need persistence across
    runs — each run is independent — and MemorySaver avoids creating a stale
    checkpoint file that could confuse future runs.
    """
    # Add s05/solution/ to the module search path so we can import wealthdesk
    s05_dir = Path(__file__).parent.parent.parent / "s05" / "solution"
    sys.path.insert(0, str(s05_dir))

    from langgraph.checkpoint.memory import MemorySaver
    from wealthdesk.agent import build_graph

    # MemorySaver: in-memory checkpointer. Each eval question gets a fresh
    # thread_id (see run_evaluation), so no state leaks between questions.
    graph = build_graph(checkpointer=MemorySaver())

    dataset = load_dataset(DATASET_PATH)
    print(f"\nRunning evaluation on {len(dataset)} questions...")
    print("-" * 60)

    results = run_evaluation(graph, dataset)
    report  = generate_report(results)
    print_report(report)


if __name__ == "__main__":
    main()
