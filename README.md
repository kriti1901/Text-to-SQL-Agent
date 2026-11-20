# Text-to-SQL Agent over Northwind and Titanic

## Overview

The Text-to-SQL Agent is a Flask web application that answers natural-language questions about
a relational database. For each question, a large language model (LLM) generates a single
SQLite `SELECT` statement. The statement is validated, executed against a read-only connection,
and the result is returned with a plain-English summary. If validation or execution fails, the
error is returned to the model and generation is retried.

The application ships with two example databases:

- **Northwind**: a sample order-management database containing customers, orders, order details,
  products, categories, suppliers, employees, shippers, territories, and regions.
- **Titanic**: passenger records from the Kaggle Titanic training dataset (891 rows).

## Processing pipeline

1. The user submits a question through the web interface or the `/api/ask` endpoint.
2. The application checks whether the question requests a data modification. If it does, the
   request is refused and no SQL is generated.
3. The LLM (Groq) generates one SQLite `SELECT` statement from the question and the database schema.
4. The statement is validated by the guard (`app/guard.py`):
   - exactly one statement, of type `SELECT`, a set operation, or a `WITH` clause;
   - only tables present in the database (or defined in a CTE) may be referenced;
   - statements such as `INSERT`, `UPDATE`, `DELETE`, `PRAGMA`, and `ATTACH` are rejected;
   - functions that load extensions or access the filesystem are rejected;
   - a `LIMIT` of 200 rows is applied when none is given.
5. The statement runs on a read-only SQLite connection with a 5-second time limit (`app/db.py`).
   Double-quoted string literals are disabled, so an unknown identifier produces an error instead
   of a silent string value.
6. If validation or execution fails, the failed SQL and the error message are sent back to the
   model. A maximum of three attempts is made. A prose reply with no SQL ends the process
   immediately.
7. On success, the first 20 result rows are summarized in one or two sentences by the LLM.

## Installation

Python 3.12 or later is required.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Build the Northwind database (required once):

```bash
.venv/bin/python scripts/build_db.py
```

Build the Titanic database from Kaggle's `train.csv`, which is available from the
[Kaggle Titanic competition](https://www.kaggle.com/c/titanic/data). Provide the path to the file:

```bash
.venv/bin/python scripts/build_titanic_db.py path/to/train.csv
```

The script writes `data/titanic.db`. The CSV file is not included in this repository.

## Authentication

All routes require HTTP Basic Authentication. The server reads the credentials from environment
variables and refuses to start if either one is missing:

| Variable | Description |
|---|---|
| `APP_USERNAME` | Username required to access the application |
| `APP_PASSWORD` | Password required to access the application |

## Usage

Start the web server:

```bash
.venv/bin/python -m app.web
```

The interface is then available at http://127.0.0.1:5000.

The server uses the Northwind database by default. To query the Titanic database, set `TEXT2SQL_DB`:

```bash
TEXT2SQL_DB=data/titanic.db .venv/bin/python -m app.web
```

Example questions:

- *Northwind:* "Which 5 customers spent the most in total?", "How many orders were shipped in 1997?",
  "Which products are discontinued?"
- *Titanic:* "What is the survival rate for female and male passengers?", "What was the average fare
  at each port of embarkation? Ignore missing ports.", "How many passengers were under 18?"

## Configuration

| Variable | Description | Default |
|---|---|---|
| `TEXT2SQL_DB` | Path to the SQLite database to query | `data/northwind.db` |
| `GROQ_API_KEY` | Groq API key; not required where the environment supplies credentials | none |
| `TEXT2SQL_MODEL` | Groq model used to generate SQL | `openai/gpt-oss-120b` |
| `APP_USERNAME` | Login username (required) | none |
| `APP_PASSWORD` | Login password (required) | none |
| `PORT` | Port for the web server | `5000` |

## API reference

`POST /api/ask` accepts a JSON body with a `question` field of up to 500 characters.

```bash
curl -X POST http://127.0.0.1:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How many passengers were under 18?"}'
```

The response contains the following fields:

| Field | Description |
|---|---|
| `ok` | `true` if a query executed successfully |
| `sql` | The final SQL statement |
| `columns`, `rows` | The result set |
| `truncated` | `true` if the result exceeded the row limit |
| `answer` | The plain-English summary |
| `attempts` | A list of each attempt, with its SQL and any error |

A request that is empty or exceeds 500 characters returns HTTP 400. An LLM failure returns HTTP 502.

## Testing

```bash
.venv/bin/python -m pytest -q tests
```

The suite contains 44 tests covering the guard, the read-only database layer, the retry logic, the
web API, and the Titanic dataset. The Titanic tests are skipped until `data/titanic.db` exists.

## Project structure

| Path | Purpose |
|---|---|
| `app/web.py` | Web interface and `/api/ask` endpoint |
| `app/agent.py` | Pipeline: question, SQL generation, validation, execution, retry, summary |
| `app/guard.py` | SQL validation |
| `app/db.py` | Read-only database access with timeout and row limit |
| `app/schema.py` | Schema introspection for the model prompt |
| `app/llm.py` | Groq API client |
| `scripts/` | Database build scripts |
| `tests/` | Test suite |

## Limitations

- **Accuracy depends on the model.** Simple questions are answered reliably. Complex or ambiguous
  questions may produce incorrect SQL, and the application cannot detect a semantically wrong but
  syntactically valid query.
- **Read-only by design.** The application does not modify data.
- **Keyword-based refusal is coarse.** Any question containing a word such as "add" or "update" is
  refused, including harmless uses such as "add up the fares".
- **Rate limits.** Groq's free tier permits roughly 8,000 tokens per minute. Requests are retried
  after the indicated delay, so bursts of questions may be slow.
- **Row cap.** Results are limited to 200 rows.

## Data sources

- **Northwind:** SQLite conversion by JP White, released under the MIT License:
  [github.com/jpwhite3/northwind-SQLite3](https://github.com/jpwhite3/northwind-SQLite3).
- **Titanic:** Kaggle training data. Review the
  [competition rules](https://www.kaggle.com/c/titanic/rules) before redistributing the data.
