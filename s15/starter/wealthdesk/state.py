from typing import TypedDict


class WealthDeskState(TypedDict):
    customer_message:  str
    response:          str
    history:           list[dict]
    query_type:        str
    retrieved_docs:    list[str]
    specialist:        str
    compliance_status: str
    blocked_reason:    str   # "" = clean; "injection" or "pii" = blocked by guard
