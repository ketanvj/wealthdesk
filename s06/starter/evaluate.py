"""
WealthDesk -- Session 6: Baseline Evaluation (starter)
=======================================================

What you build this session
  A structured evaluation pipeline that runs 40 questions from a golden
  dataset through the Session 5 WealthDesk agent, scores each response,
  and produces a pass-rate report broken down by question category.

  Routing is evaluated deterministically (COMPLEX and OUT_OF_SCOPE have
  canned responses with known keywords). SIMPLE responses are scored 1-5
  by an LLM judge. A response passes if it is correctly routed, scores
  >= 3 out of 5, and contains no forbidden content.

Run
  python s06/starter/evaluate.py

  The script imports the built WealthDesk graph from s05/solution/ and
  runs each question with a fresh MemorySaver checkpointer so no prior
  conversation state leaks between evaluation items.

Golden dataset
  s06/data/golden_dataset.json  --  40 Q&A items:
    20 SIMPLE  (loan rates, FD rates, branch info, policy)
    10 COMPLEX (financial planning, eligibility)
    10 OUT_OF_SCOPE (off-topic, competitor comparisons)

How this file is organised
  1. Configuration        -- thresholds, paths, model choice
  2. LLM judge            -- the second LLM that scores SIMPLE responses  [DONE]
  3. Dataset loading      -- reads and validates golden_dataset.json      [TODO 1]
  4. Response evaluation  -- scores one response against one dataset item [TODO 2]
  5. Evaluation runner    -- loops over all dataset items, calls the graph [TODO 3]
  6. Report generation    -- aggregates results into a summary dict        [TODO 4]
  7. Entry point          -- wires everything together                     [DONE]
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

# The judge LLM does not need tool calling -- it only reads text and returns a
# score. We deliberately use a DIFFERENT model FAMILY from the agent:
#   agent  --> openai/gpt-oss-120b  (OpenAI GPT architecture via Groq)
#   judge  --> qwen/qwen3.8-27b     (Alibaba Qwen -- completely different architecture)
# This is true cross-architecture LLM-as-judge: the two models were trained
# independently on different corpora by different organisations. A judge from
# the same family as the agent can be biased toward the agent's own output
# style -- using a different architecture eliminates that systematic bias.
MODEL_NAME  = "qwen/qwen3.8-27b"

# PASS_SCORE: the minimum judge score for a SIMPLE response to be considered
# passing. Scale is 1-5 (defined in JUDGE_PROMPT below).
# 3 = "Acceptable: the key information is present but incomplete"
# We accept 3 because we want the evaluation to catch genuinely wrong answers
# (score 1-2), not penalise minor phrasing variations (which score 3-4).
PASS_SCORE  = 3

DATA_DIR     = Path(__file__).parent.parent / "data"
DATASET_PATH = DATA_DIR / "golden_dataset.json"

# ---------------------------------------------------------------------------
# LLM judge (complete -- do not modify)
# ---------------------------------------------------------------------------

# Two LLMs are at work in this script:
#   1. The WealthDesk agent LLM (imported from s05) -- answers customer questions
#   2. This judge LLM -- evaluates the quality of those answers
#
# temperature=0.0  -> deterministic output; same question always gets same score.
#                    Critical for reproducibility: if you re-run the eval and
#                    the score changes, you want that to reflect a real change
#                    in the agent, not random variation in the judge.
# max_tokens=300   -> the judge only needs to output "SCORE: N\nREASON: ..."
#                    which is well under 300 tokens. Set conservatively at 300
#                    so any model has headroom to emit the two required lines.
judge_llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=MODEL_NAME,
    temperature=0.0,
    max_tokens=300,
)

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

    Returns (score, reason). score is clamped to [1, 5].
    Falls back to (0, error string) on parse failure.
    """
    score  = 0
    reason = "Could not parse judge output"
    for line in output.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("SCORE:"):
            try:
                raw = int(line.split(":", 1)[1].strip())
                score = max(1, min(5, raw))
            except ValueError:
                pass
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    return score, reason


def llm_judge(question: str, criteria: list[str], response: str) -> tuple[int, str]:
    """Ask the judge LLM to score a SIMPLE response.

    Returns (score, reason) where score is 1-5.
    Falls back to (0, error_message) on any exception.
    """
    criteria_list = "\n".join(f"  - {c}" for c in criteria) if criteria else "  - (none specified)"
    prompt = JUDGE_PROMPT.format(
        question=question,
        criteria_list=criteria_list,
        response=response,
    )
    # Retry up to 3 times: qwen/qwen3.8-27b occasionally returns an empty
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
# TODO 1 of 4 -- implement load_dataset()
# ---------------------------------------------------------------------------
# load_dataset() reads and validates the golden dataset from a JSON file.
#
# A "golden dataset" is a hand-curated set of questions with known correct
# answers. "Golden" means the expected outcomes are trusted ground truth --
# not generated by the model being evaluated.
#
# Each item in golden_dataset.json has these required fields:
#   id             : unique identifier, e.g. "S01", "C03", "O07"
#   query          : the customer question to send to the agent
#   expected_route : "SIMPLE", "COMPLEX", or "OUT_OF_SCOPE"
#   category       : topic label, e.g. "loan_rates", "branch", "oos"
#   criteria       : list of strings a passing response should contain
#   must_not_contain (optional): strings that must NOT appear
#
# Steps:
#   1. Open the JSON file and parse it:
#        with open(path, encoding="utf-8") as f:
#            dataset = json.load(f)
#
#   2. For each item, check all required fields are present using set subtraction:
#        REQUIRED_FIELDS = {"id", "query", "expected_route", "category", "criteria"}
#        missing = REQUIRED_FIELDS - set(item.keys())
#        if missing:
#            raise ValueError(f"Golden dataset item {i} (id={item.get('id', '?')}) is missing fields: {missing}")
#
#   3. Return the dataset list.
#
# WHY validate at load time?
#   A KeyError mid-evaluation would abort the run after 20 questions. Failing
#   fast at load time with a clear message is far better than a silent failure.
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"id", "query", "expected_route", "category", "criteria"}


def load_dataset(path: Path) -> list[dict]:
    """Load and validate the golden dataset from a JSON file."""
    # TODO 1: open the file, parse JSON, validate required fields, return the list
    raise NotImplementedError("TODO 1: implement load_dataset() in evaluate.py")


# ---------------------------------------------------------------------------
# TODO 2 of 4 -- implement evaluate_response()
# ---------------------------------------------------------------------------
# evaluate_response() scores a single graph result against its golden dataset entry.
#
# Two scoring strategies based on expected_route:
#
#   COMPLEX / OUT_OF_SCOPE  -> Deterministic keyword check
#     These routes produce canned responses. Either the keywords are present or not.
#     Score is 5 if all criteria keywords are found, 1 if any are missing.
#     No LLM call needed.
#
#   SIMPLE  -> LLM-as-judge (1-5 scale)
#     SIMPLE responses vary based on what the agent retrieved or which tools
#     it called. A keyword check alone is too brittle. Call llm_judge() instead.
#
# Pass logic (a response must satisfy ALL three):
#   1. route_correct    -- the agent routed to the expected path
#   2. score >= PASS_SCORE -- judge gave a passing score (SIMPLE only)
#   3. no forbidden content -- none of the must_not_contain strings appeared
#
# Steps:
#
#   1. Get the actual route and response from the graph result:
#        actual_route = result.get("query_type", "UNKNOWN")
#        response     = result.get("response", "")
#
#   2. Route check:
#        route_correct = (actual_route == item["expected_route"])
#
#   3. Get criteria and must_not_contain (use .get() with [] default):
#        criteria = item.get("criteria", [])
#        must_not = item.get("must_not_contain", [])
#
#   4. Case-insensitive criteria check:
#        criteria_met = all(c.lower() in response.lower() for c in criteria)
#
#   5. Forbidden content check (collect the matching strings):
#        forbidden_found = [f for f in must_not if f.lower() in response.lower()]
#
#   6. Score based on expected_route:
#      COMPLEX or OUT_OF_SCOPE:
#        score  = 5 if criteria_met else 1
#        reason = "Canned response criteria met." if criteria_met else "Canned response keyword missing."
#        passed = route_correct and criteria_met and not forbidden_found
#      SIMPLE:
#        score, reason = llm_judge(item["query"], criteria, response)
#        passed = route_correct and score >= PASS_SCORE and not forbidden_found
#
#   7. Return a dict with these keys:
#        id, query, category, expected_route, actual_route, route_correct,
#        score, reason, forbidden_found, passed, response
# ---------------------------------------------------------------------------

def evaluate_response(item: dict, result: dict) -> dict:
    """Score a single graph result against its golden dataset entry."""
    # TODO 2: implement the evaluation logic described above
    raise NotImplementedError("TODO 2: implement evaluate_response() in evaluate.py")


# ---------------------------------------------------------------------------
# TODO 3 of 4 -- implement run_evaluation()
# ---------------------------------------------------------------------------
# run_evaluation() invokes the graph on every dataset item and collects results.
#
# Steps:
#
#   1. Iterate over each item in the dataset:
#        for item in dataset:
#
#   2. Create a unique thread_id for each question so LangGraph's checkpointer
#      gives it a clean conversation history. Without this, question 2 would
#      see question 1's history and respond as if mid-conversation:
#        config = {"configurable": {"thread_id": f"eval-{item['id']}"}}
#
#   3. Invoke the graph and handle errors:
#        try:
#            graph_result = graph.invoke(
#                {"customer_message": item["query"], "response": ""},
#                config=config,
#            )
#        except Exception as e:
#            graph_result = {"query_type": "ERROR", "response": f"Graph error: {e}"}
#
#   4. Score the result and print a one-line progress update:
#        eval_result = evaluate_response(item, graph_result)
#        status = "PASS" if eval_result["passed"] else "FAIL"
#        print(f"  [{status}] {item['id']}: {item['query'][:60]}")
#        results.append(eval_result)
#
#   5. Return the results list.
# ---------------------------------------------------------------------------

def run_evaluation(graph, dataset: list[dict]) -> list[dict]:
    """Invoke the graph on every dataset item and return a list of eval results."""
    # TODO 3: implement the evaluation loop described above
    raise NotImplementedError("TODO 3: implement run_evaluation() in evaluate.py")


# ---------------------------------------------------------------------------
# TODO 4 of 4 -- implement generate_report()
# ---------------------------------------------------------------------------
# generate_report() aggregates evaluation results into a structured report dict.
#
# Returns a dict with:
#   total          : total number of questions evaluated
#   passed         : number that passed
#   failed         : total - passed
#   pass_rate      : passed / total as a float (0.0-1.0)
#   average_score  : mean judge score for SIMPLE questions only
#                    (exclude "complex" and "oos" categories -- their 1/5 scores
#                    are deterministic, not real LLM judgement)
#   by_category    : {category: {total, passed, pass_rate}}
#   failures       : list of {id, query, reason, score, actual_route} for failed items
#
# Steps:
#
#   1. Count totals:
#        total  = len(results)
#        passed = sum(1 for r in results if r["passed"])
#        failed = total - passed
#
#   2. Average score for SIMPLE questions only (score > 0 excludes parse failures):
#        simple_scores = [r["score"] for r in results if r["category"] not in ("complex", "oos") and r["score"] > 0]
#        avg_score = sum(simple_scores) / len(simple_scores) if simple_scores else 0.0
#
#   3. Per-category breakdown (build dict from scratch, no predefined keys):
#        by_category = {}
#        for r in results:
#            cat = r["category"]
#            if cat not in by_category:
#                by_category[cat] = {"total": 0, "passed": 0}
#            by_category[cat]["total"] += 1
#            if r["passed"]:
#                by_category[cat]["passed"] += 1
#        for cat, data in by_category.items():
#            data["pass_rate"] = data["passed"] / data["total"] if data["total"] else 0.0
#
#   4. Collect failures:
#        failures = [{"id": r["id"], "query": r["query"], "reason": r["reason"],
#                     "score": r["score"], "actual_route": r["actual_route"]}
#                    for r in results if not r["passed"]]
#
#   5. Return the report dict.
# ---------------------------------------------------------------------------

def generate_report(results: list[dict]) -> dict:
    """Aggregate evaluation results into a structured report dict."""
    # TODO 4: implement the report aggregation described above
    raise NotImplementedError("TODO 4: implement generate_report() in evaluate.py")


# ---------------------------------------------------------------------------
# print_report (complete -- do not modify)
# ---------------------------------------------------------------------------

def print_report(report: dict) -> None:
    """Print the evaluation report with a bar chart by category."""
    print("\n" + "=" * 60)
    print("  WealthDesk Baseline Evaluation Report")
    print("=" * 60)
    print(f"  Total questions : {report['total']}")
    print(f"  Passed          : {report['passed']}")
    print(f"  Failed          : {report['failed']}")
    print(f"  Pass rate       : {report['pass_rate']:.0%}")
    print(f"  Avg SIMPLE score: {report['average_score']} / 5")
    print()
    print("  By category:")
    for cat, data in sorted(report["by_category"].items()):
        bar = "#" * data["passed"] + "-" * (data["total"] - data["passed"])
        print(f"    {cat:<15} [{bar}] {data['passed']}/{data['total']} ({data['pass_rate']:.0%})")

    if report["failures"]:
        print()
        print(f"  Failed items ({len(report['failures'])}):")
        for f in report["failures"]:
            print(f"    {f['id']}: (route={f['actual_route']}, score={f['score']}) {f['query'][:55]}")
            print(f"         {f['reason']}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point (complete -- do not modify)
# ---------------------------------------------------------------------------

def main() -> None:
    """Load the golden dataset, build the S05 graph, run evaluation, print report."""
    s05_dir = Path(__file__).parent.parent.parent / "s05" / "solution"
    sys.path.insert(0, str(s05_dir))

    from langgraph.checkpoint.memory import MemorySaver
    from wealthdesk.agent import build_graph

    graph = build_graph(checkpointer=MemorySaver())

    dataset = load_dataset(DATASET_PATH)
    print(f"\nRunning evaluation on {len(dataset)} questions...")
    print("-" * 60)

    results = run_evaluation(graph, dataset)
    report  = generate_report(results)
    print_report(report)


if __name__ == "__main__":
    main()
