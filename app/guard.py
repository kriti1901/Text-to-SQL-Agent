"""SQL guardrails: accept only a single read-only SELECT over known tables.

This is the first of two layers. The second is the read-only SQLite connection
in app/db.py, which must reject writes even if this validator were bypassed.
"""

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

DEFAULT_LIMIT = 200

# Functions that touch the filesystem or load code inside SQLite.
DENIED_FUNCTIONS = {
    "load_extension",
    "readfile",
    "writefile",
    "edit",
    "fts3_tokenizer",
}

# Statement node types that must never appear anywhere in the tree.
FORBIDDEN_NODES = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Create", "Drop", "Alter",
        "Merge", "Command", "TruncateTable", "Transaction", "Commit", "Pragma",
    )
    if hasattr(exp, name)
)


class GuardError(ValueError):
    """Raised when SQL is rejected by the guard. The message is safe to show the LLM."""


@dataclass(frozen=True)
class Checked:
    sql: str  # normalized SQL, safe to execute
    tables: frozenset


def validate(raw_sql: str, allowed_tables: set, max_rows: int = DEFAULT_LIMIT) -> Checked:
    if not raw_sql or not raw_sql.strip():
        raise GuardError("The query is empty.")

    try:
        statements = [s for s in sqlglot.parse(raw_sql, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as e:
        message = re.sub(r"\x1b\[[0-9;]*m", "", str(e))  # sqlglot embeds ANSI color codes
        raise GuardError(f"SQL could not be parsed: {message}") from e

    if len(statements) != 1:
        raise GuardError("Exactly one SQL statement is allowed.")
    root = statements[0]

    if not isinstance(root, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise GuardError(
            f"Only SELECT queries are allowed (got {type(root).__name__})."
        )

    for node in root.walk():
        node = node[0] if isinstance(node, tuple) else node
        if isinstance(node, FORBIDDEN_NODES):
            raise GuardError(f"Statement type not allowed: {type(node).__name__}.")
        if isinstance(node, exp.Func):
            fname = (node.name or "").lower()
            if fname in DENIED_FUNCTIONS:
                raise GuardError(f"Function not allowed: {fname}().")

    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
    allowed = {t.lower() for t in allowed_tables}
    used = set()
    for table in root.find_all(exp.Table):
        name = table.name
        if not name:
            # Table-valued function or subquery alias, not a real table reference.
            continue
        lname = name.lower()
        if lname in cte_names:
            continue
        if lname not in allowed:
            raise GuardError(
                f"Unknown or disallowed table: {name!r}. "
                f"Allowed tables: {', '.join(sorted(allowed_tables))}."
            )
        used.add(name)

    if root.args.get("limit") is None:
        root = root.limit(max_rows)

    return Checked(sql=root.sql(dialect="sqlite"), tables=frozenset(used))
