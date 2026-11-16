"""Introspect the SQLite database and render a compact schema description for the LLM."""

import sqlite3


def load_tables(path):
    """Return {table_name: {"columns": [...], "fks": [...], "sample": [...]}}."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        tables = {}
        for name in names:
            q = name.replace('"', '""')
            cols = [
                {"name": r[1], "type": r[2] or "TEXT", "pk": bool(r[5])}
                for r in conn.execute(f'PRAGMA table_info("{q}")')
            ]
            fks = [
                {"column": r[3], "ref_table": r[2], "ref_column": r[4]}
                for r in conn.execute(f'PRAGMA foreign_key_list("{q}")')
            ]
            cur = conn.execute(f'SELECT * FROM "{q}" LIMIT 2')
            sample_cols = [d[0] for d in cur.description]
            sample = [dict(zip(sample_cols, row)) for row in cur.fetchall()]
            tables[name] = {"columns": cols, "fks": fks, "sample": sample}
        return tables
    finally:
        conn.close()


def render(tables):
    """Render a compact text description suitable for a system prompt."""
    lines = []
    for name, info in tables.items():
        col_parts = []
        for c in info["columns"]:
            flag = " PK" if c["pk"] else ""
            col_parts.append(f'"{c["name"]}" {c["type"]}{flag}')
        lines.append(f'TABLE "{name}" ({", ".join(col_parts)})')
        for fk in info["fks"]:
            lines.append(
                f'  FK: "{name}"."{fk["column"]}" -> "{fk["ref_table"]}"."{fk["ref_column"]}"'
            )
    return "\n".join(lines)
