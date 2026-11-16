# Northwind Text-to-SQL

Ask plain-English questions about the Northwind sample database. The assistant writes a SQLite
`SELECT`, checks it with guardrails, runs it read-only, and retries with the error message if it fails.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_db.py    # builds data/northwind.db from data/northwind_create.sql
```

The LLM is Groq's OpenAI-compatible API. Set `GROQ_API_KEY` if the environment does not inject one.
Override the model with `TEXT2SQL_MODEL` (default `openai/gpt-oss-120b`).

## Run

```bash
.venv/bin/python -m app.web          # http://127.0.0.1:5000  (PORT=... to change)
.venv/bin/python -m pytest -q tests
```

## How it works

1. `app/schema.py` introspects tables, columns, and foreign keys for the system prompt.
2. `app/llm.py` asks the model for one SQLite `SELECT` in a ```sql block.
3. `app/guard.py` parses the SQL with sqlglot. It allows a single SELECT or set operation, only tables
   in the schema (or CTEs), and rejects DML, DDL, PRAGMA, ATTACH, and dangerous functions. It adds
   `LIMIT 200` when none is given.
4. `app/db.py` opens SQLite with `mode=ro`, sets `query_only`, disables double-quoted string literals,
   and enforces a 5 s timeout and a row cap.
5. `app/agent.py` retries up to 3 times, feeding the failed SQL and error back to the model. If the
   model replies in prose (e.g. a refusal), it stops without retrying. On success it writes a short
   plain-English answer from the first 20 rows.

Data: the schema and rows come from JP White's Northwind SQLite conversion (MIT),
github.com/jpwhite3/northwind-SQLite3.
