"""Run the agent against the Kaggle Titanic dataset (data/titanic.db)."""

import pytest

from app import agent, schema
from app.db import ReadOnlyDB
from conftest import ROOT

TITANIC = ROOT / "data" / "titanic.db"
pytestmark = pytest.mark.skipif(not TITANIC.exists(), reason="run scripts/build_titanic_db.py first")


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, **kwargs):
        return self.replies.pop(0)


def _ask(sql_reply, question):
    tables = schema.load_tables(str(TITANIC))
    llm = ScriptedLLM([f"```sql\n{sql_reply}\n```", "summary"])
    return agent.answer_question(question, db=ReadOnlyDB(str(TITANIC)), llm=llm,
                                 tables=tables, schema_text=schema.render(tables))


def test_row_and_survivor_counts():
    res = _ask('SELECT COUNT(*) AS n, SUM("Survived") AS survivors FROM titanic',
               "How many passengers and survivors?")
    assert res.ok and res.rows == [[891, 342]]


def test_under_18_count():
    res = _ask('SELECT COUNT(*) FROM titanic WHERE "Age" < 18', "How many under 18?")
    assert res.rows == [[113]]


def test_survival_rate_by_sex():
    res = _ask('SELECT "Sex", ROUND(AVG("Survived"), 3) FROM titanic GROUP BY "Sex" ORDER BY "Sex"',
               "Survival rate by sex?")
    assert res.rows == [["female", 0.742], ["male", 0.189]]


def test_missing_embarked_excluded_from_fare_average():
    res = _ask('SELECT "Embarked", ROUND(AVG("Fare"), 2) FROM titanic '
               'WHERE "Embarked" IS NOT NULL GROUP BY "Embarked" ORDER BY "Embarked"',
               "Average fare by port?")
    assert [r[0] for r in res.rows] == ["C", "Q", "S"]


def test_guard_blocks_northwind_tables_on_titanic_db():
    res = _ask('SELECT * FROM "Orders"', "Orders?")
    assert res.ok is False
    assert "disallowed table" in res.attempts[0].error


def test_write_request_refused_without_calling_llm():
    tables = schema.load_tables(str(TITANIC))
    llm = ScriptedLLM([])  # any LLM call would raise IndexError
    res = agent.answer_question("Delete all passengers who did not survive.",
                                db=ReadOnlyDB(str(TITANIC)), llm=llm,
                                tables=tables, schema_text=schema.render(tables))
    assert res.ok is False
    assert res.attempts == [] and res.sql == ""
    assert "read-only" in res.answer
