"""
Pre-course setup verification script.
Run this before Session 1 to confirm your environment is ready.

Usage:
    python test_setup.py
"""

import sys
import subprocess
import importlib.util
import os

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []

def check(label, passed, fix=None):
    status = PASS if passed else FAIL
    results.append((label, passed, fix))
    print(f"  {status}  {label}")
    if not passed and fix:
        print(f"       Fix: {fix}")


print("\n" + "="*55)
print("  Agentic AI Engineering -- Pre-Course Setup Check")
print("="*55 + "\n")

# ── Python version ─────────────────────────────────────────
print("Python")
major, minor = sys.version_info[:2]
check(
    f"Python {major}.{minor} (need 3.11+)",
    major == 3 and minor >= 11,
    fix="Download Python 3.11+ from python.org"
)

# ── Required packages ──────────────────────────────────────
print("\nPackages")
packages = {
    "python-dotenv": "dotenv",
    "groq": "groq",
    "langchain": "langchain",
    "langchain-core": "langchain_core",
    "langchain-groq": "langchain_groq",
    "langgraph": "langgraph",
    "chromadb": "chromadb",
    "langchain-huggingface": "langchain_huggingface",
    "streamlit": "streamlit",
}
for pkg_name, import_name in packages.items():
    spec = importlib.util.find_spec(import_name)
    check(
        pkg_name,
        spec is not None,
        fix=f"pip install {pkg_name}"
    )

# ── .env and API key ───────────────────────────────────────
print("\nAPI Keys")
env_exists = os.path.exists(".env")
check(".env file exists", env_exists, fix="Copy .env.example to .env and add your GROQ_API_KEY")

groq_key = os.environ.get("GROQ_API_KEY", "")
if not groq_key:
    from dotenv import load_dotenv
    load_dotenv()
    groq_key = os.environ.get("GROQ_API_KEY", "")

check(
    "GROQ_API_KEY set",
    bool(groq_key and not groq_key.startswith("your_")),
    fix="Get your free key at console.groq.com and add to .env"
)

# ── Groq API live test ─────────────────────────────────────
print("\nGroq API")
if groq_key and not groq_key.startswith("your_"):
    try:
        from groq import Groq
        client = Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": "Reply with exactly: READY"}],
            max_tokens=64,
        )
        choice = response.choices[0]
        reply = (choice.message.content or "").strip()
        if "READY" in reply.upper():
            check("Groq API responds", True)
        else:
            check(
                "Groq API responds",
                False,
                fix=(
                    "Groq returned no expected text "
                    f"(finish_reason={choice.finish_reason!r}, response={reply!r})"
                ),
            )
    except Exception as e:
        check("Groq API responds", False, fix=f"Error: {e}")
else:
    check("Groq API responds", False, fix="Add GROQ_API_KEY to .env first")

# ── Ollama ─────────────────────────────────────────────────
print("\nOllama (local fallback)")
try:
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True, text=True, timeout=10
    )
    ollama_installed = result.returncode == 0
    check("Ollama installed", ollama_installed, fix="Install from ollama.com")
    if ollama_installed:
        has_model = "llama3.2" in result.stdout or "llama" in result.stdout
        check(
            "llama3.2:3b model available",
            has_model,
            fix="Run: ollama pull llama3.2:3b"
        )
except FileNotFoundError:
    check("Ollama installed", False, fix="Install from ollama.com")
except Exception as e:
    check("Ollama installed", False, fix=f"Error: {e}")

# ── LangSmith (Session 9+) ─────────────────────────────────
print("\nLangSmith (needed from Session 9)")
langsmith_key = os.environ.get("LANGSMITH_API_KEY", "")
if not langsmith_key:
    from dotenv import load_dotenv
    load_dotenv()
    langsmith_key = os.environ.get("LANGSMITH_API_KEY", "")
check(
    "LANGSMITH_API_KEY set",
    bool(langsmith_key and not langsmith_key.startswith("your_")),
    fix="Get a free key at smith.langchain.com and add LANGSMITH_API_KEY to .env"
)

# ── Vector store (Session 4+) ──────────────────────────────
print("\nVector store (needed from Session 4)")
vectorstore_path = os.path.join("data", "vectorstore")
check(
    "data/vectorstore/ exists",
    os.path.isdir(vectorstore_path) and bool(os.listdir(vectorstore_path)),
    fix="Run: python data/ingest.py"
)

# ── Git ────────────────────────────────────────────────────
print("\nGit")
try:
    result = subprocess.run(["git", "--version"], capture_output=True, text=True)
    check("Git installed", result.returncode == 0, fix="Install Git from git-scm.com")
except FileNotFoundError:
    check("Git installed", False, fix="Install Git from git-scm.com")

# ── Summary ────────────────────────────────────────────────
passed = sum(1 for _, p, _ in results if p)
total = len(results)
failed = [(label, fix) for label, p, fix in results if not p]

print("\n" + "="*55)
if not failed:
    print(f"\n  {PASS} Setup complete -- you're ready for Session 2!\n")
    print("  See you at the next session. Check WhatsApp for the date and time.\n")
else:
    print(f"\n  {FAIL} {len(failed)} item(s) need attention:\n")
    for label, fix in failed:
        print(f"  • {label}")
        if fix:
            print(f"    → {fix}")
    print(f"\n  Fix the above and run this script again.")
    print(f"  Need help? Post in the WhatsApp group or email ketanvj@gmail.com\n")
print("="*55 + "\n")
