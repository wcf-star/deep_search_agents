import pytest

from utils.sql_safety import ensure_readonly, quote_identifier


def test_quote_identifier_normal():
    assert quote_identifier("drugs") == "`drugs`"


def test_quote_identifier_strips_backticks():
    assert quote_identifier("`drugs`") == "`drugs`"


@pytest.mark.parametrize("bad", [
    "drugs; DROP TABLE users",
    "drugs` or 1=1",
    "a-b",
    "",
    "   ",
])
def test_quote_identifier_rejects_injection(bad):
    with pytest.raises(ValueError):
        quote_identifier(bad)


@pytest.mark.parametrize("ok", [
    "SELECT * FROM drugs",
    "select id, name from drugs limit 10",
    "SHOW TABLES",
    "DESCRIBE drugs",
    "WITH x AS (SELECT 1) SELECT * FROM x",
])
def test_ensure_readonly_allows(ok):
    assert ensure_readonly(ok) == ok


@pytest.mark.parametrize("bad", [
    "UPDATE drugs SET name='x'",
    "DELETE FROM drugs",
    "DROP TABLE drugs",
    "INSERT INTO drugs VALUES (1)",
    "TRUNCATE TABLE drugs",
    "ALTER TABLE drugs ADD COLUMN x INT",
])
def test_ensure_readonly_rejects_write(bad):
    with pytest.raises(ValueError):
        ensure_readonly(bad)
