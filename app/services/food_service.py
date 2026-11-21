"""
food_service.py - browse, create, update and remove food items.

Customers only see food that is:
  - available (food_items.is_available = true), AND
  - from an active restaurant (restaurants.is_active = true).
Admins can see everything with include_unavailable=true.

Delete = SOFT delete (is_available = false). A real DELETE would
CASCADE-delete it from carts and set food_id to NULL in past order_items.
"""
from decimal import Decimal

import psycopg
from fastapi import HTTPException, status
from psycopg import sql

from app.schemas.food import FoodCreate, FoodUpdate
from app.services.sql_helpers import build_set_clause, like_pattern

# JOINs add the restaurant and category NAMES, so the client doesn't need
# extra requests. LEFT JOIN keeps food whose category_id is NULL.
FOOD_SELECT = """
    SELECT f.food_id, f.restaurant_id, r.name AS restaurant_name,
           f.category_id, c.category_name,
           f.name, f.description, f.price, f.is_veg, f.is_available,
           f.image_url, f.created_at, f.updated_at
    FROM food_items f
    LEFT JOIN restaurants r ON r.restaurant_id = f.restaurant_id
    LEFT JOIN categories  c ON c.category_id   = f.category_id
"""


def list_foods(conn, *, restaurant_id: int | None = None, category_id: int | None = None,
               is_veg: bool | None = None, min_price: Decimal | None = None,
               max_price: Decimal | None = None, search: str | None = None,
               include_unavailable: bool = False, limit: int = 20, offset: int = 0) -> list[dict]:
    conditions = []
    params = []
    if not include_unavailable:
        conditions.append("f.is_available = true AND r.is_active = true")
    if restaurant_id is not None:
        conditions.append("f.restaurant_id = %s")
        params.append(restaurant_id)
    if category_id is not None:
        conditions.append("f.category_id = %s")
        params.append(category_id)
    if is_veg is not None:
        conditions.append("f.is_veg = %s")
        params.append(is_veg)
    if min_price is not None:
        conditions.append("f.price >= %s")
        params.append(min_price)
    if max_price is not None:
        conditions.append("f.price <= %s")
        params.append(max_price)
    if search:
        conditions.append("(f.name ILIKE %s OR f.description ILIKE %s)")
        pattern = like_pattern(search.strip())
        params.extend([pattern, pattern])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return conn.execute(
        f"{FOOD_SELECT} {where} ORDER BY r.name, c.category_name NULLS LAST, f.name LIMIT %s OFFSET %s",
        [*params, limit, offset],
    ).fetchall()


def get_food(conn, food_id: int, include_unavailable: bool = False) -> dict:
    row = conn.execute(
        f"{FOOD_SELECT} WHERE f.food_id = %s",
        (food_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Food item not found")
    if not include_unavailable:
        restaurant_active = conn.execute(
            "SELECT is_active FROM restaurants WHERE restaurant_id = %s", (row["restaurant_id"],)
        ).fetchone()
        if not row["is_available"] or not (restaurant_active and restaurant_active["is_active"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Food item not found")
    return row


def _check_restaurant_and_category(conn, restaurant_id: int | None, category_id: int | None) -> None:
    """Give a clear error instead of a foreign-key crash."""
    if restaurant_id is not None:
        if not conn.execute("SELECT 1 FROM restaurants WHERE restaurant_id = %s", (restaurant_id,)).fetchone():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Restaurant {restaurant_id} does not exist")
    if category_id is not None:
        if not conn.execute(
            "SELECT 1 FROM categories WHERE category_id = %s AND is_active = true", (category_id,)
        ).fetchone():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Category {category_id} does not exist or is inactive")


def create_food(conn: psycopg.Connection, data: FoodCreate) -> dict:
    _check_restaurant_and_category(conn, data.restaurant_id, data.category_id)
    new_id = conn.execute(
        """
        INSERT INTO food_items
            (restaurant_id, category_id, name, description, price, is_veg, is_available, image_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING food_id
        """,
        (data.restaurant_id, data.category_id, data.name.strip(), data.description,
         data.price, data.is_veg, data.is_available, data.image_url),
    ).fetchone()["food_id"]
    return get_food(conn, new_id, include_unavailable=True)


def update_food(conn: psycopg.Connection, food_id: int, data: FoodUpdate) -> dict:
    get_food(conn, food_id, include_unavailable=True)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Send at least one field to update")
    _check_restaurant_and_category(conn, None, changes.get("category_id"))

    set_clause, values = build_set_clause(changes)
    query = sql.SQL("UPDATE food_items SET {}, updated_at = CURRENT_TIMESTAMP WHERE food_id = %s").format(set_clause)
    conn.execute(query, [*values, food_id])
    return get_food(conn, food_id, include_unavailable=True)


def remove_food(conn: psycopg.Connection, food_id: int) -> None:
    get_food(conn, food_id, include_unavailable=True)
    conn.execute(
        "UPDATE food_items SET is_available = false, updated_at = CURRENT_TIMESTAMP WHERE food_id = %s",
        (food_id,),
    )
