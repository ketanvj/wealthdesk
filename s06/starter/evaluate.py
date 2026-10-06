"""
WealthDesk -- Session 6: Baseline Evaluation (US-05)
=====================================================

Your task: fill in every section marked TODO.
The LLM judge prompt, judge_llm client, and evaluation runner are provided.
You implement: loading the dataset, parsing the judge output, scoring each
response, and generating the summary report.

Run when you are done (from repo root):
    python s06/starter/evaluate.py
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

MODEL_NAME  = "openai/gpt-oss-20b"
PASS_SCORE  = 3   # minimum judge score (out of 5) for a SIMPLE question to pass

DATA_DIR     = Path(__file__).parent.parent / "data"
DATASET_PATH = DATA_DIR / "golden_dataset.json"

# ---------------------------------------------------------------------------
# LLM judge (provided -- no changes needed)
# ---------------------------------------------------------------------------

judge_llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=MODEL_NAME,
    temperature=0.0,
    max_tokens=100,
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


def llm_judge(question: str, criteria: list[str], response: str) -> tuple[int, str]:
    """Ask the judge LLM to score a SIMPLE response. (Provided -- no changes needed.)"""
    criteria_list = "\n".join(f"  - {c}" for c in criteria) if criteria else "  - (none specified)"
    prompt = JUDGE_PROMPT.format(
        question=question,
        criteria_list=criteria_list,
        response=response,
    )
    try:
        result = judge_llm.invoke([
            SystemMessage(content="You are a strict but fair evaluation judge."),
            HumanMessage(content=prompt),
        ])
        return parse_judge_response(result.content)
    except Exception as e:
        return 0, f"Judge error: {e}"


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"id", "query", "expected_route", "category", "criteria"}


def load_dataset(path: Path) -> list[dict]:
    """Load and validate the golden dataset from a JSON file.

    TODO 1 of 4:

    Steps:
    1. Open the file at `path` for reading (UTF-8 encoding).
    2. Parse the JSON: `dataset = json.load(f)`
    3. Validate each item:
         for i, item in enumerate(dataset):
             missing = REQUIRED_FIELDS - set(item.keys())
             if missing:
                 raise ValueError(
                     f"Golden dataset item {i} (id={item.get('id', '?')}) "
                     f"is missing fields: {missing}"
                 )
    4. Return the dataset list.

    You do NOT need to handle FileNotFoundError -- let it propagate naturally.
    """
    # TODO: implement this function
    pass


# ---------------------------------------------------------------------------
# Judge output parsing
# ---------------------------------------------------------------------------

def parse_judge_response(output: str) -> tuple[int, str]:
    """Extract the integer score and one-line reason from the judge LLM output.

    TODO 2 of 4:

    The judge always replies in this format:
      SCORE: 4
      REASON: The response correctly states the home loan rate.

    Steps:
    1. Start with defaults: score = 0, reason = "Could not parse judge output"
    2. Split output.strip() on newlines, iterate over each line:
         if the line (uppercased) starts with "SCORE:":
             try to parse the integer after the colon
             clamp it: score = max(1, min(5, raw))
         elif the line (uppercased) starts with "REASON:":
             reason = everything after the first colon, stripped
    3. Return (score, reason)

    Use line.split(":", 1)[1].strip() to handle colons in the text safely.
    """
    # TODO: implement this function
    pass


# ---------------------------------------------------------------------------
# Response evaluation
# ---------------------------------------------------------------------------

def evaluate_response(item: dict, result: dict) -> dict:
    """Score a single graph result against its golden dataset entry.

    TODO 3 of 4:

    Steps:
    1. Extract values from result:
         actual_route  = result.get("query_type", "UNKNOWN")
         response      = result.get("response", "")
         route_correct = (actual_route == item["expected_route"])
         criteria      = item.get("criteria", [])
         must_not      = item.get("must_not_contain", [])

    2. Check criteria and forbidden content:
         criteria_met    = all(c.lower() in response.lower() for c in criteria)
         forbidden_found = [f for f in must_not if f.lower() in response.lower()]

    3. Score based on expected_route:
       a) If expected_route is "COMPLEX" or "OUT_OF_SCOPE":
            score  = 5 if criteria_met else 1
            reason = "Canned response criteria met." or "Canned response keyword missing."
            passed = route_correct and criteria_met and not forbidden_found

       b) If expected_route is "SIMPLE":
            score, reason = llm_judge(item["query"], criteria, response)
            passed = route_correct and score >= PASS_SCORE and not forbidden_found

    4. Return a dict with these keys:
         "id", "query", "category", "expected_route", "actual_route",
         "route_correct", "score", "reason", "forbidden_found", "passed", "response"
    """
    # TODO: implement this function
    pass


# ---------------------------------------------------------------------------
# Evaluation runner (provided -- no changes needed)
# ---------------------------------------------------------------------------

def run_evaluation(graph, dataset: list[dict]) -> list[dict]:
    """Invoke the graph on every dataset item and return a list of eval results."""
    results = []
    for item in dataset:
        config = {"configurable": {"thread_id": f"eval-{item['id']}"}}
        try:
            graph_result = graph.invoke(
                {"customer_message": item["query"], "response": ""},
                config=config,
            )
        except Exception as e:
            graph_result = {
                "query_type": "ERROR",
                "response": f"Graph error: {e}",
            }
        eval_result = evaluate_response(item, graph_result)
        status = "PASS" if eval_result["passed"] else "FAIL"
        print(f"  [{status}] {item['id']}: {item['query'][:60]}")
        results.append(eval_result)
    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: list[dict]) -> dict:
    """Aggregate evaluation results into a structured report.

    TODO 4 of 4:

    Steps:
    1. Count totals:
         total  = len(results)
         passed = sum(1 for r in results if r["passed"])
         failed = total - passed

    2. Calculate average score for SIMPLE questions only:
         simple_scores = [r["score"] for r in results
                          if r["category"] not in ("complex", "oos") and r["score"] > 0]
         avg_score = sum(simple_scores) / len(simple_scores) if simple_scores else 0.0

    3. Build by_category dict:
         for each result r:
           - key: r["category"]
           - track "total" (count all) and "passed" (count where r["passed"] is True)
         after the loop: add "pass_rate" = passed / total for each category

    4. Build failures list (items where r["passed"] is False):
         [{"id": r["id"], "query": r["query"], "reason": r["reason"],
           "score": r["score"], "actual_route": r["actual_route"]}
          for r in results if not r["passed"]]

    5. Return:
         {"total": total, "passed": passed, "failed": failed,
          "pass_rate": passed / total if total else 0.0,
          "average_score": round(avg_score, 2),
          "by_category": by_category, "failures": failures}
    """
    # TODO: implement this function
    pass


def print_report(report: dict) -> None:
    """Print the evaluation report to stdout. (Provided -- no changes needed.)"""
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
# Entry point (provided -- no changes needed)
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
