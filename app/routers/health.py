"""
health.py - simple endpoints to check the API and the database are working.
"""
from fastapi import APIRouter

from app.database import DB

router = APIRouter(tags=["Health"])


@router.get("/")
def read_root():
    return {"message": "Welcome to FoodieHub API. Open /docs to try it."}


@router.get("/health/db")
def db_check(conn: DB):
    row = conn.execute(
        "SELECT version() AS version, current_database() AS database"
    ).fetchone()
    tables = conn.execute(
        """
        SELECT count(*) AS total
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    ).fetchone()
    return {
        "connected": True,
        "database": row["database"],
        "postgres_version": row["version"],
        "tables_found": tables["total"],
    }
