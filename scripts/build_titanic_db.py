"""Load Kaggle's Titanic train.csv into data/titanic.db as table "titanic"."""

import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "titanic.db"


def main(src):
    with open(src, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames
        rows = [[(v if v != "" else None) for v in (r[c] for c in cols)] for r in reader]

    OUT.unlink(missing_ok=True)
    conn = sqlite3.connect(OUT)
    # Typed columns: untyped CSV text would compare as strings (e.g. Age < 18 would be wrong).
    int_cols = {"PassengerId", "Survived", "Pclass", "SibSp", "Parch"}
    real_cols = {"Age", "Fare"}
    col_defs = ", ".join(
        f'"{c}" ' + ("INTEGER" if c in int_cols else "REAL" if c in real_cols else "TEXT")
        for c in cols
    )
    conn.execute(f'CREATE TABLE titanic ({col_defs})')
    conn.executemany(
        f'INSERT INTO titanic VALUES ({", ".join("?" for _ in cols)})', rows
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM titanic").fetchone()[0]
    conn.close()
    print(f"Loaded {n} rows into {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
