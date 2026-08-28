"""
data/seed.py
------------
Creates and seeds the BNB SQLite database used throughout the WealthDesk course.

Run once before Session 1:
    python data/seed.py

The script is idempotent -- it drops and recreates all tables on every run.
This means participants can reset to a clean known state at any point in the
course by running it again.

Why SQLite and not hardcoded values in the agent?
  Rates change. If we hardcode "8.5%" in the system prompt, a rate change
  means editing source code and redeploying. Keeping rates in a database means
  a rate change is a one-row UPDATE with no code change at all. This is the
  same reason production banking systems have product catalogs in a database.

Why NOT put rates in the ChromaDB documents?
  Rates in unstructured text cause two problems:
  1. The LLM may retrieve an outdated rate from a document written months ago.
  2. Contradictions between retrieved text and the database lead to hallucinations.
  Rule: structured numbers belong in SQLite. Policy and procedure text belongs in ChromaDB.
"""

import sqlite3
from pathlib import Path

# Use pathlib for all file paths to avoid backslash issues on Windows.
DATA_DIR = Path(__file__).parent
DB_PATH  = DATA_DIR / "bnb_data.db"


def create_tables(conn: sqlite3.Connection) -> None:
    """Drop and recreate all four BNB tables.

    Four tables match BNB's simplified product catalog:
    - loan_products:  each row is one loan type with its current interest rate
    - fd_products:    each row is one FD tenure band with its current interest rate
    - branches:       branch directory (name, city, IFSC, phone)
    - rate_history:   audit log of every rate change (used in S5 eval and S16 prompt versioning)

    Why rate_history as a separate table and not just edited rows in loan_products?
    Regulatory and audit requirements. Changing a rate in loan_products without
    preserving the old value would lose the history. A separate table makes the
    timeline queryable: "what was the home loan rate in Q4 FY24?" is answerable.
    """
    cursor = conn.cursor()
    cursor.executescript("""
        DROP TABLE IF EXISTS loan_products;
        DROP TABLE IF EXISTS fd_products;
        DROP TABLE IF EXISTS branches;
        DROP TABLE IF EXISTS rate_history;

        CREATE TABLE loan_products (
            product_id          TEXT PRIMARY KEY,
            name                TEXT NOT NULL,
            interest_rate       REAL NOT NULL,    -- percent per annum, e.g. 8.5
            tenure_min_years    INTEGER NOT NULL,
            tenure_max_years    INTEGER NOT NULL,
            eligibility_formula TEXT NOT NULL,    -- human-readable rule, e.g. "income x 60"
            processing_fee_info TEXT,             -- plain text, not a number (changes often)
            effective_date      TEXT NOT NULL      -- ISO 8601 date of current rate
        );

        CREATE TABLE fd_products (
            product_id      TEXT PRIMARY KEY,
            tenure_label    TEXT NOT NULL,        -- "1 year", "2 years", etc.
            tenure_months   INTEGER NOT NULL,
            interest_rate   REAL NOT NULL,        -- percent per annum
            senior_rate     REAL NOT NULL,        -- additional percent for 60+ customers
            min_deposit     INTEGER NOT NULL,     -- rupees
            effective_date  TEXT NOT NULL
        );

        CREATE TABLE branches (
            branch_id   TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            city        TEXT NOT NULL,
            address     TEXT NOT NULL,
            ifsc        TEXT NOT NULL,
            phone       TEXT NOT NULL
        );

        CREATE TABLE rate_history (
            history_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id      TEXT NOT NULL,
            product_type    TEXT NOT NULL CHECK (product_type IN ('loan', 'fd')),
            old_rate        REAL NOT NULL,
            new_rate        REAL NOT NULL,
            changed_date    TEXT NOT NULL,        -- ISO 8601
            reason          TEXT
        );
    """)
    conn.commit()


def seed_loan_products(conn: sqlite3.Connection) -> None:
    """Five BNB loan products.

    Rates are from the PRD (US-00 story). The eligibility_formula column stores
    the multiplier rule in plain text so the SQLite query tool (US-04) can
    retrieve it and the agent can use it without an LLM knowing the formula.
    """
    loans = [
        (
            "home_loan",
            "Home Loan",
            8.5,
            5, 30,
            "net monthly income x 60",
            "0.5% of loan amount",
            "2024-04-01",
        ),
        (
            "personal_loan",
            "Personal Loan",
            12.0,
            1, 5,
            "net monthly income x 24",
            "2.0% of loan amount",
            "2024-04-01",
        ),
        (
            "car_loan",
            "Car Loan",
            9.5,
            1, 7,
            "net monthly income x 36",
            "1.0% of loan amount",
            "2024-04-01",
        ),
        (
            "education_loan",
            "Education Loan",
            10.5,
            1, 15,
            "net monthly income x 60 (up to Rs. 25 lakhs)",
            "Nil for loans up to Rs. 4 lakhs",
            "2024-04-01",
        ),
        (
            "gold_loan",
            "Gold Loan",
            11.0,
            1, 3,
            "up to 75% of gold value at current BNB rate",
            "Nil",
            "2024-04-01",
        ),
    ]
    conn.executemany(
        "INSERT INTO loan_products VALUES (?,?,?,?,?,?,?,?)",
        loans,
    )
    conn.commit()


def seed_fd_products(conn: sqlite3.Connection) -> None:
    """Five FD tenure bands.

    senior_rate is the additional interest given to customers aged 60+.
    For example, if the standard rate is 6.8 and senior_rate is 0.5,
    senior customers earn 7.3% p.a.

    The 5-year FD is also BNB's tax-saving FD (Section 80C eligible).
    That policy detail is in bnb_policy.md and fd_guide.md -- it does
    not belong in this table because it is not a number.
    """
    fds = [
        ("fd_3month", "3 months",   3, 5.5, 0.5, 10_000, "2024-04-01"),
        ("fd_6month", "6 months",   6, 6.0, 0.5, 10_000, "2024-04-01"),
        ("fd_1year",  "1 year",    12, 6.8, 0.5, 10_000, "2024-04-01"),
        ("fd_2year",  "2 years",   24, 7.1, 0.5, 10_000, "2024-04-01"),
        ("fd_5year",  "5 years",   60, 7.3, 0.5, 10_000, "2024-04-01"),
    ]
    conn.executemany(
        "INSERT INTO fd_products VALUES (?,?,?,?,?,?,?)",
        fds,
    )
    conn.commit()


def seed_branches(conn: sqlite3.Connection) -> None:
    """Eight BNB branches across four cities.

    Two branches per city is enough variety to demonstrate city-based routing
    in Session 4 without an unrealistically large dataset.
    """
    branches = [
        ("BNB001", "BNB Koramangala",     "Bengaluru",  "12th Main, Koramangala 5th Block, Bengaluru 560095", "BNBI0001001", "080-41234567"),
        ("BNB002", "BNB Indiranagar",     "Bengaluru",  "100 Feet Road, Indiranagar, Bengaluru 560038",       "BNBI0001002", "080-41234568"),
        ("BNB003", "BNB Andheri West",    "Mumbai",     "SV Road, Andheri West, Mumbai 400058",               "BNBI0002001", "022-41234567"),
        ("BNB004", "BNB Bandra West",     "Mumbai",     "Linking Road, Bandra West, Mumbai 400050",           "BNBI0002002", "022-41234568"),
        ("BNB005", "BNB Anna Nagar",      "Chennai",    "2nd Avenue, Anna Nagar, Chennai 600040",             "BNBI0003001", "044-41234567"),
        ("BNB006", "BNB T. Nagar",        "Chennai",    "Usman Road, T. Nagar, Chennai 600017",               "BNBI0003002", "044-41234568"),
        ("BNB007", "BNB Hitech City",     "Hyderabad",  "Cyber Towers Road, Hitech City, Hyderabad 500081",  "BNBI0004001", "040-41234567"),
        ("BNB008", "BNB Connaught Place", "Delhi",      "Block A, Connaught Place, New Delhi 110001",         "BNBI0005001", "011-41234567"),
    ]
    conn.executemany(
        "INSERT INTO branches VALUES (?,?,?,?,?,?)",
        branches,
    )
    conn.commit()


def seed_rate_history(conn: sqlite3.Connection) -> None:
    """Sample rate changes for the audit log.

    Used in Session 6 (eval) and Session 16 (advanced eval + prompt versioning)
    to demonstrate that the agent correctly reports the *current* rate, not a
    historical one retrieved from ChromaDB documents.
    """
    history = [
        ("home_loan",     "loan", 8.9, 8.5, "2024-04-01", "RBI repo rate reduction passed on to customers"),
        ("personal_loan", "loan", 13.0, 12.0, "2024-04-01", "Competitive rate revision aligned with market"),
        ("fd_1year",      "fd",   6.5, 6.8, "2024-04-01",   "Deposit rate revision to attract retail deposits"),
        ("fd_2year",      "fd",   6.8, 7.1, "2024-04-01",   "Deposit rate revision to attract retail deposits"),
    ]
    conn.executemany(
        "INSERT INTO rate_history (product_id, product_type, old_rate, new_rate, changed_date, reason)"
        " VALUES (?,?,?,?,?,?)",
        history,
    )
    conn.commit()


def print_summary(conn: sqlite3.Connection) -> None:
    """Print a quick sanity check so the instructor can confirm the seed worked."""
    # The table name is taken from a hardcoded list, NOT from user input.
    # This f-string in SQL is safe ONLY because of that constraint.
    # In agent tool functions (Session 5), always use parameterised queries
    # with ? placeholders -- never build SQL from user-supplied strings.
    tables = ["loan_products", "fd_products", "branches", "rate_history"]
    print("\nDatabase contents:")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:20s}: {count} rows")

    print("\nLoan products:")
    for row in conn.execute("SELECT name, interest_rate, tenure_min_years, tenure_max_years FROM loan_products"):
        print(f"  {row[0]:20s}: {row[1]:.1f}% p.a., {row[2]}-{row[3]} years")

    print("\nFD products:")
    for row in conn.execute("SELECT tenure_label, interest_rate, senior_rate FROM fd_products"):
        print(f"  {row[0]:12s}: {row[1]:.1f}% (seniors: {row[1]+row[2]:.1f}%)")


def main() -> None:
    print(f"Creating BNB database at: {DB_PATH}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        create_tables(conn)
        seed_loan_products(conn)
        seed_fd_products(conn)
        seed_branches(conn)
        seed_rate_history(conn)
        print_summary(conn)

    print(f"\nDone. Run 'python data/ingest.py' to rebuild the vectorstore if needed.")


if __name__ == "__main__":
    main()
