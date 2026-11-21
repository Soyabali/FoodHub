"""
restaurant_service.py - list, view, create, update and deactivate restaurants.

Delete = SOFT delete (is_active = false). A real DELETE would trigger
ON DELETE CASCADE and erase all the restaurant's food items, and set
restaurant_id to NULL on its past orders, so order history would break.
"""
import psycopg
from fastapi import HTTPException, status
from psycopg import sql

from app.schemas.restaurant import RestaurantCreate, RestaurantUpdate
from app.services.sql_helpers import build_set_clause, like_pattern

RESTAURANT_COLUMNS = (
    "restaurant_id, name, email, phone, street, city, state, zip_code, "
    "opening_time, closing_time, rating, is_active, created_at, updated_at"
)


def list_restaurants(conn, city: str | None, search: str | None, include_inactive: bool,
                     limit: int, offset: int) -> list[dict]:
    # Build the WHERE part from the filters that were given
    conditions = []
    params = []
    if not include_inactive:
        conditions.append("is_active = true")
    if city:
        conditions.append("lower(city) = lower(%s)")
        params.append(city.strip())
    if search:
        conditions.append("name ILIKE %s")          # ILIKE = case-insensitive LIKE
        params.append(like_pattern(search.strip()))

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return conn.execute(
        f"""
        SELECT {RESTAURANT_COLUMNS} FROM restaurants
        {where}
        ORDER BY rating DESC NULLS LAST, name
        LIMIT %s OFFSET %s
        """,
        [*params, limit, offset],
    ).fetchall()


def get_restaurant(conn, restaurant_id: int, include_inactive: bool = False) -> dict:
    row = conn.execute(
        f"""
        SELECT {RESTAURANT_COLUMNS},
               (SELECT count(*) FROM food_items f
                WHERE f.restaurant_id = r.restaurant_id AND f.is_available = true) AS menu_item_count
        FROM restaurants r
        WHERE restaurant_id = %s
        """,
        (restaurant_id,),
    ).fetchone()
    if row is None or (not row["is_active"] and not include_inactive):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Restaurant not found")
    return row


def _check_email_free(conn, email: str, exclude_id: int | None = None) -> None:
    taken = conn.execute(
        "SELECT 1 FROM restaurants WHERE lower(email) = %s AND restaurant_id IS DISTINCT FROM %s",
        (email, exclude_id),
    ).fetchone()
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "A restaurant with this email already exists")


def create_restaurant(conn: psycopg.Connection, data: RestaurantCreate) -> dict:
    email = data.email.lower()
    _check_email_free(conn, email)
    try:
        return conn.execute(
            f"""
            INSERT INTO restaurants
                (name, email, phone, street, city, state, zip_code, opening_time, closing_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {RESTAURANT_COLUMNS}
            """,
            (data.name.strip(), email, data.phone, data.street.strip(), data.city.strip(),
             data.state.strip(), data.zip_code.strip(), data.opening_time, data.closing_time),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "A restaurant with this email already exists")


def update_restaurant(conn: psycopg.Connection, restaurant_id: int, data: RestaurantUpdate) -> dict:
    get_restaurant(conn, restaurant_id, include_inactive=True)       # 404 if missing

    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Send at least one field to update")
    if "email" in changes:
        changes["email"] = changes["email"].lower()
        _check_email_free(conn, changes["email"], exclude_id=restaurant_id)

    set_clause, values = build_set_clause(changes)
    query = sql.SQL(
        "UPDATE restaurants SET {}, updated_at = CURRENT_TIMESTAMP "
        "WHERE restaurant_id = %s RETURNING " + RESTAURANT_COLUMNS
    ).format(set_clause)
    try:
        return conn.execute(query, [*values, restaurant_id]).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "A restaurant with this email already exists")


def deactivate_restaurant(conn: psycopg.Connection, restaurant_id: int) -> None:
    get_restaurant(conn, restaurant_id, include_inactive=True)
    conn.execute(
        "UPDATE restaurants SET is_active = false, updated_at = CURRENT_TIMESTAMP WHERE restaurant_id = %s",
        (restaurant_id,),
    )
