"""
category_service.py - food categories (Pizza, Burgers, Biryani, ...).

Delete = SOFT delete (is_active = false). A real DELETE would set
category_id to NULL on every food item in that category.
"""
import psycopg
from fastapi import HTTPException, status
from psycopg import sql

from app.schemas.food import CategoryCreate, CategoryUpdate
from app.services.sql_helpers import build_set_clause

CATEGORY_COLUMNS = "category_id, category_name, description, is_active, created_at"


def list_categories(conn, include_inactive: bool) -> list[dict]:
    where = "" if include_inactive else "WHERE is_active = true"
    return conn.execute(f"SELECT {CATEGORY_COLUMNS} FROM categories {where} ORDER BY category_name").fetchall()


def get_category(conn, category_id: int, include_inactive: bool = False) -> dict:
    row = conn.execute(f"SELECT {CATEGORY_COLUMNS} FROM categories WHERE category_id = %s", (category_id,)).fetchone()
    if row is None or (not row["is_active"] and not include_inactive):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return row


def _check_name_free(conn, name: str, exclude_id: int | None = None) -> None:
    taken = conn.execute(
        "SELECT 1 FROM categories WHERE lower(category_name) = lower(%s) AND category_id IS DISTINCT FROM %s",
        (name, exclude_id),
    ).fetchone()
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "A category with this name already exists")


def create_category(conn: psycopg.Connection, data: CategoryCreate) -> dict:
    name = data.category_name.strip()
    _check_name_free(conn, name)
    try:
        return conn.execute(
            f"INSERT INTO categories (category_name, description) VALUES (%s, %s) RETURNING {CATEGORY_COLUMNS}",
            (name, data.description),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "A category with this name already exists")


def update_category(conn: psycopg.Connection, category_id: int, data: CategoryUpdate) -> dict:
    get_category(conn, category_id, include_inactive=True)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Send at least one field to update")
    if "category_name" in changes:
        changes["category_name"] = changes["category_name"].strip()
        _check_name_free(conn, changes["category_name"], exclude_id=category_id)

    set_clause, values = build_set_clause(changes)
    query = sql.SQL("UPDATE categories SET {} WHERE category_id = %s RETURNING " + CATEGORY_COLUMNS).format(set_clause)
    try:
        return conn.execute(query, [*values, category_id]).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "A category with this name already exists")


def deactivate_category(conn: psycopg.Connection, category_id: int) -> None:
    get_category(conn, category_id, include_inactive=True)
    conn.execute("UPDATE categories SET is_active = false WHERE category_id = %s", (category_id,))
