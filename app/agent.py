"""Question -> SQL -> guard -> execute, with error-driven retries."""

import json
import re
from dataclasses import dataclass, field

from . import guard
from .db import ReadOnlyDB

MAX_ATTEMPTS = 3
SUMMARY_ROWS = 20

SYSTEM_TEMPLATE = """You translate plain-English questions into a single SQLite SELECT query.

Rules:
- Use only the tables and columns listed in the schema below.
- Output exactly one SELECT (a WITH clause is fine). No INSERT, UPDATE, DELETE, DDL, PRAGMA, or ATTACH.
- Double-quote every table and column name, e.g. "Order Details" and "UnitPrice".
- Return the SQL inside a ```sql fenced block and nothing else.

Schema:
{schema}
"""

SUMMARY_TEMPLATE = (
    "Question: {question}\n"
    "Columns: {columns}\n"
    "Total rows returned: {total}\n"
    "Rows (first {n}, JSON): {rows}\n"
    "Answer the question in one or two plain sentences based only on these rows. "
    "If the rows are empty, say no matching data was found."
)


@dataclass
class Attempt:
    number: int
    sql: str
    error: str = ""


@dataclass
class Answer:
    ok: bool
    question: str
    sql: str = ""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    truncated: bool = False
    answer: str = ""
    attempts: list = field(default_factory=list)


_SQL_START = re.compile(
    r"^\s*(select|with|insert|update|delete|drop|create|alter|pragma|attach)\b", re.I
)


def _looks_like_sql(text: str) -> bool:
    """True if the reply is SQL (fenced, or starting with a SQL keyword), not prose."""
    return "```sql" in text.lower() or bool(_SQL_START.match(text.strip("` \n\t")))


def extract_sql(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    sql = match.group(1) if match else text
    return sql.strip().rstrip(";").strip()


READ_ONLY_REFUSAL = (
    "This assistant is read-only. It can't delete, insert, update, or drop data. "
    "Ask a question about the data instead, such as how many passengers did not survive."
)
_WRITE_INTENT = re.compile(
    r"\b(delete|remove|erase|wipe|drop|truncate|insert|add|update|alter|create|modify)\b",
    re.I,
)


def answer_question(question, *, db: ReadOnlyDB, llm, tables, schema_text,
                    max_attempts=MAX_ATTEMPTS, summarize=True):
    if _WRITE_INTENT.search(question):
        # Refuse before calling the model, so no query is generated for a write request.
        return Answer(ok=False, question=question, answer=READ_ONLY_REFUSAL)

    allowed = set(tables.keys())
    messages = [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(schema=schema_text)},
        {"role": "user", "content": question},
    ]
    result = Answer(ok=False, question=question)

    for n in range(1, max_attempts + 1):
        raw = llm.chat(messages)
        if not _looks_like_sql(raw):
            # The model answered in prose (e.g. declined). Retrying won't help, so stop.
            result.answer = raw.strip()
            result.sql = ""
            return result
        candidate = extract_sql(raw)
        attempt = Attempt(number=n, sql=candidate)

        try:
            checked = guard.validate(candidate, allowed, max_rows=db.max_rows)
            qr = db.run(checked.sql)
        except guard.GuardError as e:
            attempt.error = f"Rejected by guardrail: {e}"
        except Exception as e:  # sqlite errors, timeouts, etc.
            attempt.error = f"Database error: {e}"
        else:
            result.attempts.append(attempt)
            result.ok = True
            result.sql = checked.sql
            result.columns = qr.columns
            result.rows = qr.rows
            result.truncated = qr.truncated
            if summarize:
                result.answer = _summarize(question, llm, qr)
            return result

        result.attempts.append(attempt)
        # Feed the failed SQL and the error back so the model can correct itself.
        messages.append({"role": "assistant", "content": f"```sql\n{candidate}\n```"})
        messages.append({
            "role": "user",
            "content": (
                f"That query failed. {attempt.error}\n"
                "Fix the problem and return a corrected single SELECT in a ```sql block."
            ),
        })

    result.sql = result.attempts[-1].sql if result.attempts else ""
    return result


def _summarize(question, llm, qr):
    preview = qr.rows[:SUMMARY_ROWS]
    prompt = SUMMARY_TEMPLATE.format(
        question=question,
        columns=", ".join(qr.columns),
        total=len(qr.rows) if not qr.truncated else f"{len(qr.rows)}+ (truncated)",
        n=SUMMARY_ROWS,
        rows=json.dumps(preview, default=str),
    )
    try:
        return llm.chat([{"role": "user", "content": prompt}], max_tokens=300).strip()
    except Exception:
        return ""
