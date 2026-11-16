import pytest

from app import guard

TABLES = {"Orders", "Customers", "Order Details", "Products"}


@pytest.mark.parametrize("sql", [
    'SELECT * FROM "Orders"',
    'select count(*) from Customers',
    'SELECT "CustomerID", "City" FROM "Customers" WHERE "Country" = \'UK\'',
    'WITH t AS (SELECT "OrderID" FROM "Orders") SELECT * FROM t',
    'SELECT "ProductID" FROM "Products" UNION SELECT "ProductID" FROM "Order Details"',
    'SELECT * FROM "Orders" WHERE "OrderID" IN (SELECT "OrderID" FROM "Order Details")',
])
def test_accepts_read_only_selects(sql):
    checked = guard.validate(sql, TABLES)
    assert checked.sql.upper().startswith(("SELECT", "WITH"))


@pytest.mark.parametrize("sql", [
    'DROP TABLE "Orders"',
    'DELETE FROM "Orders"',
    'INSERT INTO "Customers" ("CustomerID") VALUES (\'X\')',
    'UPDATE "Products" SET "UnitPrice" = 0',
    'CREATE TABLE evil (a int)',
    'ALTER TABLE "Orders" ADD COLUMN x int',
    'PRAGMA table_info("Orders")',
    'ATTACH DATABASE \'/etc/passwd\' AS x',
    'SELECT 1; DROP TABLE "Orders"',
    'SELECT * FROM "Orders"; SELECT * FROM "Customers"',
    '',
    '   ',
])
def test_rejects_writes_and_multi_statements(sql):
    with pytest.raises(guard.GuardError):
        guard.validate(sql, TABLES)


@pytest.mark.parametrize("sql", [
    'SELECT * FROM sqlite_master',
    'SELECT * FROM "sqlite_schema"',
    'SELECT * FROM Employees',  # real table, but not in the allowlist below
])
def test_rejects_tables_outside_allowlist(sql):
    with pytest.raises(guard.GuardError, match="disallowed table"):
        guard.validate(sql, TABLES)


def test_rejects_dangerous_functions():
    with pytest.raises(guard.GuardError, match="not allowed"):
        guard.validate("SELECT load_extension('x')", TABLES)


def test_adds_limit_when_missing():
    checked = guard.validate('SELECT * FROM "Orders"', TABLES, max_rows=50)
    assert "LIMIT 50" in checked.sql.upper()


def test_keeps_existing_limit():
    checked = guard.validate('SELECT * FROM "Orders" LIMIT 3', TABLES, max_rows=50)
    assert "LIMIT 3" in checked.sql.upper()


def test_parse_error_is_a_guard_error():
    with pytest.raises(guard.GuardError):
        guard.validate("SELEC * FRM", TABLES)
