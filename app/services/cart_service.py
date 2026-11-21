"""
cart_service.py - the customer's shopping cart.

Tables:
  carts       - one row per cart (customer_id, restaurant_id, status)
  cart_items  - the food in a cart (food_id, quantity, unit_price)

Rules:
- A customer has at most ONE active cart. It is created automatically when
  they add their first item.
- A cart holds food from ONE restaurant (carts.restaurant_id). Adding food
  from another restaurant gives 409, unless replace_cart=true.
- Adding the same food again increases the quantity (no duplicate rows).
- A cart that already has an order is finished, even if its status still
  says 'active' (this handles carts 1 and 3 in the sample data).
- Totals use the CURRENT food price. cart_items.unit_price keeps the price
  at the moment it was added, so we can warn when the price has changed.
"""
from decimal import Decimal

import psycopg
from fastapi import HTTPException, status

from app.schemas.cart import MAX_QUANTITY_PER_ITEM, CartItemAdd

DELIVERY_FEE = Decimal("30.00")  # same as the default of orders.delivery_fee

# "Active cart" = status active AND not already turned into an order
ACTIVE_CART_SQL = """
    SELECT c.cart_id, c.restaurant_id
    FROM carts c
    WHERE c.customer_id = %s
      AND c.status = 'active'
      AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.cart_id = c.cart_id)
    ORDER BY c.cart_id DESC
    LIMIT 1
"""


def _lock_customer(conn, customer_id: int) -> None:
    """Lock this customer's row until the transaction ends. If the same
    customer sends two cart requests at the same moment, the second waits,
    so we never create two active carts or lose a quantity update."""
    conn.execute("SELECT 1 FROM customers WHERE customer_id = %s FOR UPDATE", (customer_id,))


def find_active_cart(conn, customer_id: int) -> dict | None:
    return conn.execute(ACTIVE_CART_SQL, (customer_id,)).fetchone()


def _get_or_create_cart(conn, customer_id: int) -> dict:
    cart = find_active_cart(conn, customer_id)
    if cart:
        return cart
    return conn.execute(
        "INSERT INTO carts (customer_id, status) VALUES (%s, 'active') RETURNING cart_id, restaurant_id",
        (customer_id,),
    ).fetchone()


def _touch(conn, cart_id: int) -> None:
    """Record that the cart changed."""
    conn.execute("UPDATE carts SET updated_at = CURRENT_TIMESTAMP WHERE cart_id = %s", (cart_id,))


def _clear_restaurant_if_empty(conn, cart_id: int) -> None:
    conn.execute(
        """
        UPDATE carts SET restaurant_id = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE cart_id = %s AND NOT EXISTS (SELECT 1 FROM cart_items WHERE cart_id = %s)
        """,
        (cart_id, cart_id),
    )


# ---------- View ----------

def get_cart(conn: psycopg.Connection, customer_id: int) -> dict:
    cart = find_active_cart(conn, customer_id)
    if cart is None:
        return {"cart_id": None, "restaurant_id": None, "restaurant_name": None, "items": [],
                "item_count": 0, "subtotal": Decimal("0.00"), "delivery_fee": Decimal("0.00"),
                "total": Decimal("0.00"), "warnings": []}

    restaurant = conn.execute(
        "SELECT name FROM restaurants WHERE restaurant_id = %s", (cart["restaurant_id"],)
    ).fetchone() if cart["restaurant_id"] else None

    rows = conn.execute(
        """
        SELECT ci.cart_item_id, ci.food_id, ci.quantity, ci.unit_price,
               f.name, f.is_veg, f.price AS current_price,
               (f.is_available AND r.is_active) AS is_available
        FROM cart_items ci
        LEFT JOIN food_items  f ON f.food_id = ci.food_id
        LEFT JOIN restaurants r ON r.restaurant_id = f.restaurant_id
        WHERE ci.cart_id = %s
        ORDER BY ci.added_at, ci.cart_item_id
        """,
        (cart["cart_id"],),
    ).fetchall()

    items, warnings = [], []
    subtotal = Decimal("0.00")
    item_count = 0
    for row in rows:
        available = bool(row["is_available"])
        price_changed = available and row["current_price"] != row["unit_price"]
        line_total = row["current_price"] * row["quantity"] if available else Decimal("0.00")
        if not available:
            warnings.append(f"'{row['name']}' is no longer available. Remove it before ordering.")
        elif price_changed:
            warnings.append(f"Price of '{row['name']}' changed from {row['unit_price']} to {row['current_price']}.")
        subtotal += line_total
        item_count += row["quantity"] if available else 0
        items.append({
            "cart_item_id": row["cart_item_id"], "food_id": row["food_id"], "name": row["name"],
            "is_veg": row["is_veg"], "quantity": row["quantity"], "price_when_added": row["unit_price"],
            "current_price": row["current_price"], "line_total": line_total,
            "price_changed": price_changed, "is_available": available,
        })

    delivery_fee = DELIVERY_FEE if item_count else Decimal("0.00")
    return {
        "cart_id": cart["cart_id"],
        "restaurant_id": cart["restaurant_id"],
        "restaurant_name": restaurant["name"] if restaurant else None,
        "items": items,
        "item_count": item_count,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": subtotal + delivery_fee,
        "warnings": warnings,
    }


# ---------- Change ----------

def add_item(conn: psycopg.Connection, customer_id: int, data: CartItemAdd) -> dict:
    # 1. The food must exist, be available, and its restaurant must be open for business
    food = conn.execute(
        """
        SELECT f.food_id, f.name, f.price, f.restaurant_id, r.name AS restaurant_name
        FROM food_items f
        JOIN restaurants r ON r.restaurant_id = f.restaurant_id
        WHERE f.food_id = %s AND f.is_available = true AND r.is_active = true
        """,
        (data.food_id,),
    ).fetchone()
    if food is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Food item not found or not available")

    _lock_customer(conn, customer_id)
    cart = _get_or_create_cart(conn, customer_id)

    has_items = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM cart_items WHERE cart_id = %s) AS has_items", (cart["cart_id"],)
    ).fetchone()["has_items"]

    # 2. One restaurant per cart
    if has_items and cart["restaurant_id"] != food["restaurant_id"]:
        if not data.replace_cart:
            current = conn.execute(
                "SELECT name FROM restaurants WHERE restaurant_id = %s", (cart["restaurant_id"],)
            ).fetchone()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Your cart has food from '{current['name'] if current else 'another restaurant'}'. "
                f"Send replace_cart=true to empty it and add from '{food['restaurant_name']}'.",
            )
        conn.execute("DELETE FROM cart_items WHERE cart_id = %s", (cart["cart_id"],))
        has_items = False

    if not has_items:
        conn.execute(
            "UPDATE carts SET restaurant_id = %s, updated_at = CURRENT_TIMESTAMP WHERE cart_id = %s",
            (food["restaurant_id"], cart["cart_id"]),
        )

    # 3. Same food already in the cart? Increase its quantity. Otherwise insert.
    existing = conn.execute(
        "SELECT cart_item_id, quantity FROM cart_items WHERE cart_id = %s AND food_id = %s",
        (cart["cart_id"], food["food_id"]),
    ).fetchone()

    if existing:
        new_quantity = existing["quantity"] + data.quantity
        if new_quantity > MAX_QUANTITY_PER_ITEM:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"You can have at most {MAX_QUANTITY_PER_ITEM} of one item (you already have {existing['quantity']})",
            )
        conn.execute(
            "UPDATE cart_items SET quantity = %s, unit_price = %s WHERE cart_item_id = %s",
            (new_quantity, food["price"], existing["cart_item_id"]),
        )
    else:
        conn.execute(
            "INSERT INTO cart_items (cart_id, food_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
            (cart["cart_id"], food["food_id"], data.quantity, food["price"]),
        )

    _touch(conn, cart["cart_id"])
    return get_cart(conn, customer_id)


def _get_own_item(conn, customer_id: int, cart_item_id: int) -> dict:
    cart = find_active_cart(conn, customer_id)
    item = None
    if cart:
        item = conn.execute(
            "SELECT ci.cart_item_id, ci.food_id, ci.cart_id FROM cart_items ci WHERE ci.cart_item_id = %s AND ci.cart_id = %s",
            (cart_item_id, cart["cart_id"]),
        ).fetchone()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cart item not found")
    return item


def update_quantity(conn: psycopg.Connection, customer_id: int, cart_item_id: int, quantity: int) -> dict:
    _lock_customer(conn, customer_id)
    item = _get_own_item(conn, customer_id, cart_item_id)
    # Refresh the price too, so the customer sees and agrees to the current price
    conn.execute(
        """
        UPDATE cart_items ci
        SET quantity = %s,
            unit_price = COALESCE((SELECT f.price FROM food_items f WHERE f.food_id = ci.food_id), ci.unit_price)
        WHERE ci.cart_item_id = %s
        """,
        (quantity, item["cart_item_id"]),
    )
    _touch(conn, item["cart_id"])
    return get_cart(conn, customer_id)


def remove_item(conn: psycopg.Connection, customer_id: int, cart_item_id: int) -> dict:
    _lock_customer(conn, customer_id)
    item = _get_own_item(conn, customer_id, cart_item_id)
    conn.execute("DELETE FROM cart_items WHERE cart_item_id = %s", (item["cart_item_id"],))
    _clear_restaurant_if_empty(conn, item["cart_id"])
    return get_cart(conn, customer_id)


def clear_cart(conn: psycopg.Connection, customer_id: int) -> dict:
    _lock_customer(conn, customer_id)
    cart = find_active_cart(conn, customer_id)
    if cart:
        conn.execute("DELETE FROM cart_items WHERE cart_id = %s", (cart["cart_id"],))
        _clear_restaurant_if_empty(conn, cart["cart_id"])
    return get_cart(conn, customer_id)
