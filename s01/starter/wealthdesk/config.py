"""
wealthdesk/config.py
--------------------
All constants and prompts for WealthDesk.
Nothing here makes API calls -- it's pure configuration.
"""

# ---------------------------------------------------------------------------
# Model settings (provided -- no changes needed)
# ---------------------------------------------------------------------------

MODEL_NAME  = "openai/gpt-oss-20b"
TEMPERATURE = 0.3
MAX_TOKENS  = 300

# ---------------------------------------------------------------------------
# TODO 2 of 5 -- System prompt
# ---------------------------------------------------------------------------
# Write the system prompt that tells WealthDesk who it is and what it knows.
#
# Use the four-component structure:
#
#   1. Persona          Who WealthDesk is and what tone it uses
#   2. Domain knowledge BNB products, rates, and eligibility formulas
#   3. Rules            What to always do, never do, and how to handle edge cases
#   4. Output format    Response length and sign-off line (put this LAST)
#
# Rates to include:
#   Home Loan      : from 8.5% p.a., tenure 5–30 years
#   Personal Loan  : from 12.0% p.a., tenure 1–5 years
#   Car Loan       : from 9.5% p.a., tenure 1–7 years
#   Education Loan : from 10.5% p.a., tenure 1–15 years
#   Gold Loan      : from 11.0% p.a., tenure 1–3 years
#   FD 1 year      : 6.8% p.a. (senior citizens: 7.3%)
#   FD 2 years     : 7.1% p.a. (senior citizens: 7.6%)
#   FD 5 years     : 7.3% p.a. (senior citizens: 7.8%) -- tax-saving under 80C
#
# Eligibility formulas:
#   Home Loan     : max loan = monthly income × 60
#   Personal Loan : max loan = monthly income × 24
#
# Hint: use a triple-quoted string -- SYSTEM_PROMPT = """..."""
#
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
TODO: Write the WealthDesk system prompt here.
"""
