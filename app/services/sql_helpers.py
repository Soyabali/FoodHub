"""
sql_helpers.py - small helper for PATCH (partial update) queries.

For a PATCH we only update the fields the client actually sent, so the
SET part of the UPDATE changes per request, e.g.:
    UPDATE customers SET "full_name" = %s, "phone" = %s WHERE ...

Column names can't be %s placeholders, so we use psycopg's sql.Identifier,
which quotes them safely. The column names also only ever come from our
Pydantic schema fields (never from raw user text), and the VALUES still go
through %s placeholders.
"""
from psycopg import sql


def like_pattern(text: str) -> str:
    """Turns a search word into a safe ILIKE pattern: "pizza" -> "%pizza%".
    % and _ are wildcards in LIKE, so we escape them in the user's text."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def build_set_clause(fields: dict) -> tuple[sql.Composed, list]:
    """{"full_name": "A", "phone": "1"} -> ('"full_name" = %s, "phone" = %s', ["A", "1"])"""
    parts = [sql.SQL("{} = %s").format(sql.Identifier(column)) for column in fields]
    return sql.SQL(", ").join(parts), list(fields.values())
