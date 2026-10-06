"""
s15/tests/conftest.py
---------------------
Shared fixtures for S15 tests.
Adds s15/solution/ to sys.path so wealthdesk can be imported directly.
"""
import sys
from pathlib import Path

SOLUTION_DIR = Path(__file__).parent.parent / "solution"
sys.path.insert(0, str(SOLUTION_DIR))
