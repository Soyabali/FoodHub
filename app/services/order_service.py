"""
order_service.py - place orders, order history, details, cancel, status flow.

PLACING AN ORDER is one database transaction (all-or-nothing):
  1. Lock the customer (stops double-click double orders)
  2. Read the active cart and lock its food rows (prices can't change mid-way)
  3. Check: cart not empty, every item available, restaurant active,
     address belongs to the customer
  4. INSERT orders          (subtotal, delivery_fee, discount, total_amount)
  5. INSERT order_items     (one row per cart item, at the current price)
  6. UPDATE carts           status = 'ordered'
If ANY step fails, an error is raised and PostgreSQL rolls back steps 4-6,
so we never get an order without items, or a cart ordered twice.

STATUS FLOW (from the CHECK constraint on orders.status):
  pending -> confirmed -> preparing -> out_for_delivery -> delivered
  pending / confirmed -> cancelled
"""
from decimal import Decimal

import psycopg
from fastapi import HTTPException, status

from app.models.enums import OrderStatus
from app.schemas.order import OrderCreate
from app.services import delivery_service, payment_service
from app.services.cart_service import DELIVERY_FEE, find_active_cart

CANCELLABLE = {OrderStatus.pending.value, OrderStatus.confirmed.value}

# Which status can follow which (admin updates)
ALLOWED_NEXT = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"preparing", "cancelled"},
    "preparing": {"out_for_delivery"},
    "out_for_delivery": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}

ORDER_SUMMARY_SELECT = """
    SELECT o.order_id, o.customer_id, o.restaurant_id, r.name AS restaurant_name,
           o.status, o.subtotal, o.delivery_fee, o.discount, o.total_amount,
           o.special_instructions, o.ordered_at, o.delivered_at, o.updated_at,
           o.delivery_address_id,
           (SELECT COALESCE(sum(oi.quantity), 0) FROM order_items oi
            WHERE oi.order_id = o.order_id) AS item_count
    FROM orders o
    LEFT JOIN restaurants r ON r.restaurant_id = o.restaurant_id
"""


# ---------- Place order ----------

def place_order(conn: psycopg.Connection, customer_id: int, data: OrderCreate) -> dict:
    # 1. One order at a time per customer
    conn.execute("SELECT 1 FROM customers WHERE customer_id = %s FOR UPDATE", (customer_id,))

    # 2. The cart and its items. FOR SHARE locks the food rows, so an admin
    #    can't change a price while we are copying it into the order.
    cart = find_active_cart(conn, customer_id)
    if cart is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your cart is empty")

    items = conn.execute(
        """
        SELECT ci.food_id, ci.quantity, f.name, f.price,
               f.is_available, f.restaurant_id, r.is_active AS restaurant_active
        FROM cart_items ci
        JOIN food_items  f ON f.food_id = ci.food_id
        JOIN restaurants r ON r.restaurant_id = f.restaurant_id
        WHERE ci.cart_id = %s
        ORDER BY ci.cart_item_id
        FOR SHARE OF f, r
        """,
        (cart["cart_id"],),
    ).fetchall()
    if not items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your cart is empty")

    # 3a. Every item must still be orderable
    unavailable = [i["name"] for i in items if not i["is_available"] or not i["restaurant_active"]]
    if unavailable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"These items are no longer available, remove them from your cart: {', '.join(unavailable)}",
        )
    restaurant_id = items[0]["restaurant_id"]

    # 3b. Delivery address: the one given, or the customer's default
    if data.delivery_address_id is not None:
        address = conn.execute(
            "SELECT address_id FROM addresses WHERE address_id = %s AND customer_id = %s",
            (data.delivery_address_id, customer_id),
        ).fetchone()
        if address is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Delivery address not found")
    else:
        address = conn.execute(
            """
            SELECT address_id FROM addresses WHERE customer_id = %s
            ORDER BY is_default DESC, created_at DESC LIMIT 1
            """,
            (customer_id,),
        ).fetchone()
        if address is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add a delivery address first (POST /addresses)")

    # 3c. Money: always calculated on the server from current prices
    subtotal = sum((i["price"] * i["quantity"] for i in items), Decimal("0.00"))
    discount = Decimal("0.00")
    total_amount = subtotal + DELIVERY_FEE - discount

    # 4. The order
    order = conn.execute(
        """
        INSERT INTO orders
            (customer_id, restaurant_id, delivery_address_id, cart_id, status,
             subtotal, delivery_fee, discount, total_amount, special_instructions)
        VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s)
        RETURNING order_id
        """,
        (customer_id, restaurant_id, address["address_id"], cart["cart_id"],
         subtotal, DELIVERY_FEE, discount, total_amount, data.special_instructions),
    ).fetchone()

    # 5. The order items. executemany() runs the same INSERT once per item.
    #    total_price is NOT inserted: it is a GENERATED column in your database
    #    (total_price = quantity * unit_price), so PostgreSQL calculates it.
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO order_items (order_id, food_id, quantity, unit_price)
            VALUES (%s, %s, %s, %s)
            """,
            [(order["order_id"], i["food_id"], i["quantity"], i["price"]) for i in items],
        )

    # 6. The cart is finished
    conn.execute(
        "UPDATE carts SET status = 'ordered', updated_at = CURRENT_TIMESTAMP WHERE cart_id = %s",
        (cart["cart_id"],),
    )

    return get_order(conn, order["order_id"], customer_id)


# ---------- Read ----------

def list_orders(conn, customer_id: int | None, order_status: str | None, limit: int, offset: int) -> list[dict]:
    """customer_id=None means all customers (admin)."""
    conditions, params = [], []
    if customer_id is not None:
        conditions.append("o.customer_id = %s")
        params.append(customer_id)
    if order_status:
        conditions.append("o.status = %s")
        params.append(order_status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return conn.execute(
        f"{ORDER_SUMMARY_SELECT} {where} ORDER BY o.ordered_at DESC, o.order_id DESC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    ).fetchall()


def get_order(conn, order_id: int, customer_id: int | None) -> dict:
    """customer_id=None means any customer's order (admin)."""
    order = conn.execute(f"{ORDER_SUMMARY_SELECT} WHERE o.order_id = %s", (order_id,)).fetchone()
    if order is None or (customer_id is not None and order["customer_id"] != customer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    order["items"] = conn.execute(
        """
        SELECT oi.order_item_id, oi.food_id, f.name, oi.quantity, oi.unit_price, oi.total_price
        FROM order_items oi
        LEFT JOIN food_items f ON f.food_id = oi.food_id
        WHERE oi.order_id = %s
        ORDER BY oi.order_item_id
        """,
        (order_id,),
    ).fetchall()

    order["delivery_address"] = conn.execute(
        """
        SELECT address_id, address_label, street, city, state, zip_code, country
        FROM addresses WHERE address_id = %s
        """,
        (order["delivery_address_id"],),
    ).fetchone() if order["delivery_address_id"] else None

    order["can_cancel"] = order["status"] in CANCELLABLE
    order["payment_status"] = payment_service.latest_payment_status(conn, order_id)
    return order


# ---------- Change status ----------

def _lock_order(conn, order_id: int, customer_id: int | None) -> dict:
    order = conn.execute(
        "SELECT order_id, customer_id, status FROM orders WHERE order_id = %s FOR UPDATE",
        (order_id,),
    ).fetchone()
    if order is None or (customer_id is not None and order["customer_id"] != customer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def cancel_order(conn: psycopg.Connection, order_id: int, customer_id: int) -> dict:
    order = _lock_order(conn, order_id, customer_id)
    if order["status"] not in CANCELLABLE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"An order that is '{order['status']}' can't be cancelled. "
            "Orders can only be cancelled while pending or confirmed.",
        )
    conn.execute(
        "UPDATE orders SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE order_id = %s",
        (order_id,),
    )
    payment_service.handle_order_cancelled(conn, order_id)   # refund (same transaction)
    delivery_service.handle_order_cancelled(conn, order_id)  # stop delivery, free partner
    return get_order(conn, order_id, customer_id)


def update_status(conn: psycopg.Connection, order_id: int, new_status: OrderStatus) -> dict:
    order = _lock_order(conn, order_id, None)
    current = order["status"] or "pending"
    if new_status.value not in ALLOWED_NEXT.get(current, set()):
        allowed = ", ".join(sorted(ALLOWED_NEXT.get(current, set()))) or "none (final status)"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Can't change status from '{current}' to '{new_status.value}'. Allowed next: {allowed}",
        )
    conn.execute(
        """
        UPDATE orders
        SET status = %s,
            delivered_at = CASE WHEN %s = 'delivered' THEN CURRENT_TIMESTAMP ELSE delivered_at END,
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = %s
        """,
        (new_status.value, new_status.value, order_id),
    )
    if new_status == OrderStatus.cancelled:
        payment_service.handle_order_cancelled(conn, order_id)
        delivery_service.handle_order_cancelled(conn, order_id)
    return get_order(conn, order_id, None)
