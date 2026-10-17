"""
wealthdesk/state.py
-------------------
The shared state that flows through the LangGraph graph.

Every node reads from this state and writes back a partial update.
Only define the shape here -- no logic.
"""
from typing import TypedDict


# ---------------------------------------------------------------------------
# TODO 3 of 5 -- State definition
# ---------------------------------------------------------------------------
# Define WealthDeskState as a TypedDict with exactly two fields:
#
#   customer_message : str   -- the question the customer typed
#   response         : str   -- the answer WealthDesk will return
#
# Pattern:
#   class WealthDeskState(TypedDict):
#       field_name: type
#
# ---------------------------------------------------------------------------

class WealthDeskState(TypedDict):
    customer_message:str
    response:str


# Guard: raises at import time if the fields haven't been defined yet.
if "customer_message" not in WealthDeskState.__annotations__:
    raise NotImplementedError(
        "TODO 3: define 'customer_message: str' and 'response: str' "
        "in WealthDeskState in wealthdesk/state.py"
    )
