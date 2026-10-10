"""
WealthDesk package -- Session 1: Basic Conversational Agent (US-01)
====================================================================

This file runs automatically when Python imports the wealthdesk package.
Use it to set up the environment before any other module loads.
"""
import os

os.environ.setdefault("HF_HUB_VERBOSITY", "error")

# ---------------------------------------------------------------------------
# TODO 1 of 5 -- Environment setup
# ---------------------------------------------------------------------------
# Your .env file contains GROQ_API_KEY=your_key_here.
# Python cannot read it automatically -- you have to call load_dotenv().
#
# Step 1: Import the function
from dotenv import load_dotenv

#
# Step 2: Call it (before anything else reads os.environ)
load_dotenv()
#
# Why here? This file is the first thing imported when `wealthdesk` loads,
# so your key is available to every other module (config.py, tools.py, etc.)
# by the time they need it.
#
# ---------------------------------------------------------------------------
