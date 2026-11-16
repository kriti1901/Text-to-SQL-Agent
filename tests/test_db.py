import sqlite3

import pytest

from app.db import ReadOnlyDB
from conftest import DB_PATH


@pytest.fixture
def db():
    return ReadOnlyDB(str(DB_PATH), max_rows=5)


def test_reads_work(db):
    res = db.run('SELECT "CustomerID" FROM "Customers"')
    assert res.columns == ["CustomerID"]
    assert len(res.rows) == 5
    assert res.truncated is True


def test_write_refused_at_connection_level(db):
    # Bypass the guard entirely: the connection itself must refuse writes.
    with pytest.raises(sqlite3.Error):
        db.run('DELETE FROM "Orders"')
    with pytest.raises(sqlite3.Error):
        db.run('CREATE TABLE zzz (a INT)')


def test_timeout_interrupts_long_query():
    # timeout 0 means the deadline has already passed, so the progress handler
    # aborts as soon as it runs (every 10k VM ops) on any non-trivial query.
    slow = ReadOnlyDB(str(DB_PATH), timeout_s=0)
    with pytest.raises(sqlite3.Error, match="interrupted"):
        slow.run(
            'SELECT count(*) FROM "Order Details" a, "Order Details" b'
        )


def test_unknown_double_quoted_column_is_an_error(db):
    with pytest.raises(sqlite3.Error):
        db.run('SELECT "NoSuchColumn" FROM "Customers"')
