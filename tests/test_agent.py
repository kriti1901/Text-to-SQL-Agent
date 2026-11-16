from app import agent, schema
from app.db import ReadOnlyDB
from conftest import DB_PATH


class ScriptedLLM:
    """Returns scripted replies in order; records what it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        if not self.replies:
            raise AssertionError("LLM called more times than scripted")
        return self.replies.pop(0)


def _setup():
    tables = schema.load_tables(str(DB_PATH))
    return tables, schema.render(tables), ReadOnlyDB(str(DB_PATH), max_rows=10)


def test_retries_after_database_error_and_succeeds():
    tables, schema_text, db = _setup()
    llm = ScriptedLLM([
        '```sql\nSELECT "NoSuchColumn" FROM "Customers"\n```',   # DB error
        '```sql\nSELECT COUNT(*) AS n FROM "Customers"\n```',    # fixed
        'There are 93 customers.',                               # summary
    ])
    res = agent.answer_question("How many customers?", db=db, llm=llm,
                                tables=tables, schema_text=schema_text)
    assert res.ok is True
    assert len(res.attempts) == 2
    assert "Database error" in res.attempts[0].error
    assert res.attempts[1].error == ""
    assert res.rows == [[93]]
    assert res.answer == "There are 93 customers."
    # The retry prompt must carry the failed SQL's error back to the model.
    retry_user_msg = llm.calls[1][-1]["content"]
    assert "NoSuchColumn" in retry_user_msg or "no such column" in retry_user_msg.lower()


def test_guard_rejection_is_fed_back_and_gives_up():
    tables, schema_text, db = _setup()
    llm = ScriptedLLM(['DELETE FROM "Orders"'] * 3)
    res = agent.answer_question("Show me all the orders", db=db, llm=llm,
                                tables=tables, schema_text=schema_text)
    assert res.ok is False
    assert len(res.attempts) == 3
    assert all("Rejected by guardrail" in a.error for a in res.attempts)
    assert res.rows == []
    # Nothing was deleted.
    assert db.run('SELECT COUNT(*) FROM "Orders"').rows == [[830]]


def test_end_to_end_real_db_without_summary():
    tables, schema_text, db = _setup()
    llm = ScriptedLLM(['```sql\nSELECT COUNT(*) FROM "Orders";\n```'])
    res = agent.answer_question("How many orders?", db=db, llm=llm, tables=tables,
                                schema_text=schema_text, summarize=False)
    assert res.ok is True
    assert res.rows == [[830]]
    assert res.answer == ""


def test_prose_refusal_stops_early_without_retrying():
    tables, schema_text, db = _setup()
    llm = ScriptedLLM(["I'm sorry, but I can't help with that."])  # only one reply scripted
    res = agent.answer_question("What is the weather today?", db=db, llm=llm,
                                tables=tables, schema_text=schema_text)
    assert res.ok is False
    assert res.attempts == []
    assert "can't help" in res.answer


def test_extract_sql_handles_fences_and_bare_sql():
    assert agent.extract_sql("```sql\nSELECT 1;\n```") == "SELECT 1"
    assert agent.extract_sql("SELECT 2") == "SELECT 2"
