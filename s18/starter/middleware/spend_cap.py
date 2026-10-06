"""
S18 — Spend Cap Middleware
==========================

TODO 3: Implement the token budget tracker and circuit breaker.

Why spend caps?
  LLM APIs charge per token. A bug, a loop, or a malicious user can generate
  thousands of requests before anyone notices. A spend cap circuit breaker stops
  LLM calls when the budget is exhausted, returning HTTP 503 instead of incurring
  more cost.

  Two budgets:
    Hourly  — catches sudden spikes (stuck loop, automated attack)
    Daily   — enforces the overall cost envelope

Your tasks:
  TODO 3a: Implement SpendCapTracker.__init__ with thread-safe counters.
  TODO 3b: Implement check() — returns (True, "") if budget available,
           (False, reason) if circuit should open.
  TODO 3c: Implement record(tokens) — increments both counters.
  TODO 3d: Implement status() — returns dict for /budget endpoint.
  TODO 3e: Implement estimate_tokens(text) — rough word-count heuristic.

Hint: see solution/middleware/spend_cap.py for the full implementation.
"""

import threading
from datetime import datetime, timezone


class SpendCapTracker:
    def __init__(self, hourly_budget: int, daily_budget: int):
        # TODO 3a: initialise thread lock and counters
        # self._lock         = threading.Lock()
        # self.hourly_budget = hourly_budget
        # self.daily_budget  = daily_budget
        # self._hourly_used  = 0
        # self._daily_used   = 0
        # self._hour_key     = self._current_hour()
        # self._day_key      = self._current_day()
        self._lock         = threading.Lock()
        self.hourly_budget = hourly_budget
        self.daily_budget  = daily_budget
        self._hourly_used  = 0
        self._daily_used   = 0

    @staticmethod
    def _current_hour() -> str:
        now = datetime.now(timezone.utc)
        return f"{now.date()}-{now.hour:02d}"

    @staticmethod
    def _current_day() -> str:
        return str(datetime.now(timezone.utc).date())

    def check(self) -> tuple[bool, str]:
        """TODO 3b: Return (allowed, reason).

        allowed=False means the circuit is open — don't call the LLM.

        Hint:
          with self._lock:
              if self._hourly_used >= self.hourly_budget:
                  return False, "Hourly budget exhausted"
              if self._daily_used >= self.daily_budget:
                  return False, "Daily budget exhausted"
              return True, ""
        """
        # TODO: implement with proper lock and reset logic
        return True, ""  # placeholder — always allows

    def record(self, tokens: int) -> None:
        """TODO 3c: Add tokens to both hourly and daily counters (thread-safe)."""
        # TODO: implement
        pass

    def status(self) -> dict:
        """TODO 3d: Return usage dict for the /budget endpoint."""
        # TODO: implement
        return {
            "hourly": {"used": self._hourly_used, "budget": self.hourly_budget, "pct": 0.0},
            "daily":  {"used": self._daily_used,  "budget": self.daily_budget,  "pct": 0.0},
        }


def estimate_tokens(text: str) -> int:
    """TODO 3e: Return a rough token count for the given text.

    Hint: int(len(text.split()) * 1.3) is accurate within ~15% for English.
    """
    # TODO: implement
    return len(text.split())  # placeholder — slightly under-counts
