"""Rebuild data/northwind.db from data/northwind_create.sql and verify row counts.

Source: the Northwind SQLite conversion by JP White (MIT), github.com/jpwhite3/northwind-SQLite3.
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "northwind_create.sql"
OUT = ROOT / "data" / "northwind.db"

EXPECTED = {"Orders": 830, "Customers": 93, "Products": 77, "Order Details": 2155}


def main():
    if OUT.exists():
        OUT.unlink()
    conn = sqlite3.connect(OUT)
    conn.executescript(SRC.read_text(encoding="utf-8", errors="replace"))
    conn.commit()
    failures = []
    for table, want in EXPECTED.items():
        got = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        status = "ok" if got == want else "MISMATCH"
        print(f"{table:15} {got:>8}  expected {want:>8}  {status}")
        if got != want:
            failures.append(table)
    conn.close()
    if failures:
        sys.exit(f"Row count mismatch for: {', '.join(failures)}")
    print(f"Built {OUT}")


if __name__ == "__main__":
    main()
