from typing import TypedDict


class WealthDeskState(TypedDict):
    customer_message: str
    response:         str
    history:          list[dict]
    query_type:       str
    retrieved_docs:   list[str]
