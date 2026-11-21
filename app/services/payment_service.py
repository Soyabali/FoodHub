"""
payment_service.py - record payments, payment status, payment history.

There is no real payment gateway (Razorpay, Stripe, ...) yet, so online
payments are SIMULATED:
  cash                              -> 'pending'   (collected on delivery)
  card / upi / wallet / net_banking -> 'completed' with a fake transaction_id
                                       (or 'failed' if simulate_failure=true)

Rules:
- The amount is ALWAYS orders.total_amount. The client never sends it.
- An order can't be paid twice: blocked if it has a 'completed' or
  'pending' payment. After a 'failed' payment the customer can try again.
- A cancelled order can't be paid.
- A completed online payment confirms a 'pending' order automatically.

Payment status flow (admin):
  pending   -> completed (cash collected) | failed
  completed -> refunded
"""
import secrets
from datetime import datetime, timezone

import psycopg
from fastapi import HTTPException, status

from app.schemas.payment import PaymentCreate

ALLOWED_NEXT = {
    "pending": {"completed", "failed"},
    "completed": {"refunded"},
    "failed": set(),
    "refunded": set(),
}

PAYMENT_SELECT = """
    SELECT p.payment_id, p.order_id, p.customer_id, p.amount, p.payment_method,
           p.payment_status, p.transaction_id, p.paid_at, p.created_at,
           o.status AS order_status
    FROM payments p
    LEFT JOIN orders o ON o.order_id = p.order_id
"""


def _new_transaction_id(method: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"TXN_{method.upper()}_{stamp}_{secrets.token_hex(4).upper()}"   # e.g. TXN_UPI_20261121014500_9F3A1C2B


def _get_order_for_customer(conn, order_id: int, customer_id: int | None, lock: bool = False) -> dict:
    lock_sql = "FOR UPDATE" if lock else ""
    order = conn.execute(
        f"SELECT order_id, customer_id, status, total_amount FROM orders WHERE order_id = %s {lock_sql}",
        (order_id,),
    ).fetchone()
    if order is None or (customer_id is not None and order["customer_id"] != customer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


# ---------- Create ----------

def pay_for_order(conn: psycopg.Connection, order_id: int, customer_id: int, data: PaymentCreate) -> dict:
    # Lock the order, so two payment requests at the same moment can't both succeed
    order = _get_order_for_customer(conn, order_id, customer_id, lock=True)

    if order["status"] == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "This order was cancelled and can't be paid")

    existing = conn.execute(
        """
        SELECT payment_status, payment_method FROM payments
        WHERE order_id = %s AND payment_status IN ('completed', 'pending')
        LIMIT 1
        """,
        (order_id,),
    ).fetchone()
    if existing:
        if existing["payment_status"] == "completed":
            raise HTTPException(status.HTTP_409_CONFLICT, "This order is already paid")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This order already has a pending {existing['payment_method']} payment",
        )

    method = data.payment_method.value
    if method == "cash":
        payment_status, transaction_id = "pending", None
    elif data.simulate_failure:
        payment_status, transaction_id = "failed", _new_transaction_id(method)
    else:
        payment_status, transaction_id = "completed", _new_transaction_id(method)

    payment = conn.execute(
        """
        INSERT INTO payments (order_id, customer_id, amount, payment_method, payment_status, transaction_id, paid_at)
        VALUES (%s, %s, %s, %s, %s, %s,
                CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END)
        RETURNING payment_id
        """,
        (order_id, customer_id, order["total_amount"], method, payment_status, transaction_id, payment_status),
    ).fetchone()

    # Paid online -> the restaurant can start: pending order becomes confirmed
    if payment_status == "completed" and order["status"] == "pending":
        conn.execute(
            "UPDATE orders SET status = 'confirmed', updated_at = CURRENT_TIMESTAMP WHERE order_id = %s",
            (order_id,),
        )

    return get_payment(conn, payment["payment_id"], None)


# ---------- Read ----------

def get_payment(conn, payment_id: int, customer_id: int | None) -> dict:
    row = conn.execute(f"{PAYMENT_SELECT} WHERE p.payment_id = %s", (payment_id,)).fetchone()
    if row is None or (customer_id is not None and row["customer_id"] != customer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return row


def list_order_payments(conn, order_id: int, customer_id: int | None) -> list[dict]:
    _get_order_for_customer(conn, order_id, customer_id)      # 404 if not theirs
    return conn.execute(
        f"{PAYMENT_SELECT} WHERE p.order_id = %s ORDER BY p.created_at, p.payment_id",
        (order_id,),
    ).fetchall()


def list_payments(conn, customer_id: int | None, payment_status: str | None, limit: int, offset: int) -> list[dict]:
    """customer_id=None means every customer (admin)."""
    conditions, params = [], []
    if customer_id is not None:
        conditions.append("p.customer_id = %s")
        params.append(customer_id)
    if payment_status:
        conditions.append("p.payment_status = %s")
        params.append(payment_status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return conn.execute(
        f"{PAYMENT_SELECT} {where} ORDER BY p.created_at DESC, p.payment_id DESC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    ).fetchall()


def latest_payment_status(conn, order_id: int) -> str | None:
    row = conn.execute(
        "SELECT payment_status FROM payments WHERE order_id = %s ORDER BY created_at DESC, payment_id DESC LIMIT 1",
        (order_id,),
    ).fetchone()
    return row["payment_status"] if row else None


# ---------- Change status ----------

def update_status(conn: psycopg.Connection, payment_id: int, new_status: str) -> dict:
    payment = conn.execute(
        "SELECT payment_id, payment_status FROM payments WHERE payment_id = %s FOR UPDATE",
        (payment_id,),
    ).fetchone()
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")

    current = payment["payment_status"] or "pending"
    if new_status not in ALLOWED_NEXT.get(current, set()):
        allowed = ", ".join(sorted(ALLOWED_NEXT.get(current, set()))) or "none (final status)"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Can't change payment from '{current}' to '{new_status}'. Allowed next: {allowed}",
        )

    conn.execute(
        """
        UPDATE payments
        SET payment_status = %s,
            paid_at = CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE paid_at END
        WHERE payment_id = %s
        """,
        (new_status, new_status, payment_id),
    )
    return get_payment(conn, payment_id, None)


def handle_order_cancelled(conn: psycopg.Connection, order_id: int) -> None:
    """Called when an order is cancelled (in the same transaction):
    money already taken is refunded, and cash that was never collected fails."""
    conn.execute(
        "UPDATE payments SET payment_status = 'refunded' WHERE order_id = %s AND payment_status = 'completed'",
        (order_id,),
    )
    conn.execute(
        "UPDATE payments SET payment_status = 'failed' WHERE order_id = %s AND payment_status = 'pending'",
        (order_id,),
    )
