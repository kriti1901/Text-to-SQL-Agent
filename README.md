# Text-to-SQL Agent

Ask a question in plain English and get an answer from a database. The app writes a SQL query,
runs it, and explains the result in a sentence or two. It's a small Flask web app.

It works on two example databases:

- **Northwind**: a sample orders database (customers, orders, products, employees).
- **Titanic**: passenger data from the Kaggle Titanic competition.

## What it does

1. You type a question, for example "Which 5 customers spent the most?"
2. An LLM (Groq) writes one SQL `SELECT` for the question.
3. The app checks the query before running it:
   - Only a single read-only `SELECT` is allowed.
   - Only tables in the database can be used.
   - Results are capped at 200 rows.
4. If the query fails, the error goes back to the LLM and it tries again, up to 3 times.
5. You get the SQL, the result table, and a plain-English answer.

Questions that ask to change data (delete, drop, insert, update, and similar) are refused
without generating any SQL. The database is opened read-only, so writes would fail anyway.

## Setup

You need Python 3.10 or newer.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Build the Northwind database (this step is needed once):

```bash
.venv/bin/python scripts/build_db.py
```

Build the Titanic database from a Kaggle `train.csv` file. Download it from the
[Kaggle Titanic competition](https://www.kaggle.com/c/titanic/data) and pass its path:

```bash
.venv/bin/python scripts/build_titanic_db.py path/to/train.csv
```

This creates `data/titanic.db`. The CSV itself is not included in the repo.

## Running the app

```bash
.venv/bin/python -m app.web
```

Then open http://127.0.0.1:5000 in your browser.

By default the app uses Northwind. To use Titanic instead, set the database path first:

```bash
TEXT2SQL_DB=data/titanic.db .venv/bin/python -m app.web
```

### Settings

| Variable | What it does | Default |
|---|---|---|
| `TEXT2SQL_DB` | Which SQLite database to query | `data/northwind.db` |
| `GROQ_API_KEY` | Groq API key, if your environment doesn't provide one | none |
| `TEXT2SQL_MODEL` | Groq model that writes the SQL | `openai/gpt-oss-120b` |
| `PORT` | Port for the web server | `5000` |

## Example questions

Northwind:
- "Which 5 customers spent the most in total?"
- "How many orders were shipped in 1997?"
- "Which products are discontinued?"

Titanic:
- "What is the survival rate for female and male passengers?"
- "What was the average fare at each port of embarkation? Ignore missing ports."
- "How many passengers were under 18?"

## Using the API

The web page calls a JSON endpoint you can use directly:

```bash
curl -X POST http://127.0.0.1:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How many passengers were under 18?"}'
```

The response includes:
- `ok`: whether a query ran successfully
- `sql`: the final SQL
- `columns` and `rows`: the result
- `answer`: the plain-English summary
- `attempts`: each try, with any error it hit

## Tests

```bash
.venv/bin/python -m pytest -q tests
```

The tests cover the query checker, the read-only database layer, the retry loop, the web API,
and the Titanic data. The Titanic tests are skipped until `data/titanic.db` exists.

## How it's built

| File | Job |
|---|---|
| `app/web.py` | Web page and `/api/ask` endpoint |
| `app/agent.py` | Question → SQL → check → run → retry → answer |
| `app/guard.py` | Checks the SQL before it runs |
| `app/db.py` | Read-only database access with a 5-second time limit |
| `app/schema.py` | Reads table and column names to show the LLM |
| `app/llm.py` | Calls the Groq API |
| `scripts/` | Builds the two example databases |

## Limitations

- **Answers depend on the LLM.** Simple questions work well. Complex or ambiguous ones can get
  the wrong SQL, and the app can't tell when that happens.
- **Read-only.** The app will never change data, by design.
- **Keyword refusal is blunt.** Any question containing a word like "add" or "update" is refused,
  even if it's harmless, such as "add up the fares".
- **Free-tier rate limits.** Groq's free tier allows about 8,000 tokens per minute. The app waits
  and retries when it hits the limit, so bursts of questions can be slow.
- **Results are capped.** Queries return at most 200 rows.

## Data sources

- Northwind: the SQLite conversion by JP White, MIT licensed,
  [github.com/jpwhite3/northwind-SQLite3](https://github.com/jpwhite3/northwind-SQLite3).
- Titanic: Kaggle's training data. Check the
  [competition's terms](https://www.kaggle.com/c/titanic/rules) before redistributing it.
