"""Read-only SQLite access with a row cap and a wall-clock timeout."""

import sqlite3
import time
from dataclasses import dataclass, field

DEFAULT_MAX_ROWS = 200
DEFAULT_TIMEOUT_S = 5.0


@dataclass
class QueryResult:
    columns: list
    rows: list = field(default_factory=list)
    truncated: bool = False


class ReadOnlyDB:
    def __init__(self, path, max_rows=DEFAULT_MAX_ROWS, timeout_s=DEFAULT_TIMEOUT_S):
        self.path = path
        self.max_rows = max_rows
        self.timeout_s = timeout_s

    def _connect(self):
        # mode=ro makes SQLite open the file read-only at the OS level.
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")  # belt and braces: no writes on this connection
        # Without this, SQLite treats an unknown "double-quoted" name as a string literal,
        # so a bad column silently returns text instead of raising an error the retry loop can use.
        conn.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, False)
        conn.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DDL, False)
        deadline = time.monotonic() + self.timeout_s

        def stop_if_late():
            return 1 if time.monotonic() > deadline else 0  # nonzero aborts the query

        conn.set_progress_handler(stop_if_late, 10_000)
        return conn

    def run(self, sql: str) -> QueryResult:
        conn = self._connect()
        try:
            cur = conn.execute(sql)
            columns = [d[0] for d in cur.description or []]
            fetched = cur.fetchmany(self.max_rows + 1)
            truncated = len(fetched) > self.max_rows
            rows = [list(r) for r in fetched[: self.max_rows]]
            return QueryResult(columns=columns, rows=rows, truncated=truncated)
        finally:
            conn.close()
