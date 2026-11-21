"""
database.py - manages the connection to the Neon PostgreSQL database.

How it works:
- We create a "connection pool": a small set of open connections that are
  reused between requests (opening a new connection to Neon for every
  request would be slow).
- get_db() lends one connection to an API request and takes it back after.
- Rows come back as Python dicts, e.g. {"customer_id": 1, "full_name": "..."}.

Transactions (automatic):
- If the request finishes normally  -> all changes are COMMITTED.
- If any error is raised            -> all changes are ROLLED BACK.
So a multi-step operation (like placing an order) is all-or-nothing.
"""
from typing import Annotated

import psycopg
from fastapi import Depends
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False,                               # opened when the app starts (see main.py)
    kwargs={"row_factory": dict_row},         # return rows as dicts
    check=ConnectionPool.check_connection,    # replace connections Neon closed while idle
)


def open_pool() -> None:
    pool.open()
    pool.wait(timeout=15)  # fail fast if the database can't be reached


def close_pool() -> None:
    pool.close()


def get_db():
    """Gives one database connection to a request (use the DB type below)."""
    with pool.connection() as conn:   # commits on success, rolls back on error
        yield conn


# Use this type in endpoints:   def my_endpoint(conn: DB): ...
# scope="function" makes the COMMIT happen BEFORE the response is sent,
# so the client never sees "success" for data that wasn't saved.
DB = Annotated[psycopg.Connection, Depends(get_db, scope="function")]
