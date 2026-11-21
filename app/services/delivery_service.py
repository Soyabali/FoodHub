"""
delivery_service.py - delivery partners, assigning deliveries, delivery
status, and order tracking.

A partner is FREE when:  is_active AND is_available AND not on an active delivery.
(The sample data has partners on active deliveries whose is_available is
still true, so we always check for an active delivery too.)

Delivery status flow (from the CHECK constraint on deliveries.status):
  assigned -> picked_up -> on_the_way -> delivered
  (any of these) -> failed

Each delivery change keeps the ORDER in sync, in the same transaction:
  picked_up / on_the_way -> order 'out_for_delivery'
  delivered              -> order 'delivered' (+ delivered_at), partner free again,
                            pending cash payment marked 'completed' (collected)
  failed                 -> partner free again; admin can assign a new partner
"""
import psycopg
from fastapi import HTTPException, status
from psycopg import sql

from app.schemas.delivery import DeliveryAssign, PartnerCreate, PartnerUpdate
from app.services.sql_helpers import build_set_clause

ACTIVE_STATUSES = ("assigned", "picked_up", "on_the_way")

ALLOWED_NEXT = {
    "assigned": {"picked_up", "failed"},
    "picked_up": {"on_the_way", "delivered", "failed"},
    "on_the_way": {"delivered", "failed"},
    "delivered": set(),
    "failed": set(),
}

# Orders in these statuses can get a delivery partner
ASSIGNABLE_ORDER_STATUSES = ("confirmed", "preparing", "out_for_delivery")

PARTNER_SELECT = """
    SELECT p.partner_id, p.full_name, p.email, p.phone, p.vehicle_type, p.vehicle_number,
           p.rating, p.is_available, p.is_active,
           d.delivery_id AS active_delivery_id,
           (p.is_active AND p.is_available AND d.delivery_id IS NULL) AS is_free
    FROM delivery_partners p
    LEFT JOIN LATERAL (
        SELECT delivery_id FROM deliveries
        WHERE partner_id = p.partner_id AND status IN ('assigned', 'picked_up', 'on_the_way')
        ORDER BY assigned_at DESC LIMIT 1
    ) d ON true
"""

DELIVERY_SELECT = """
    SELECT d.delivery_id, d.order_id, o.status AS order_status,
           d.partner_id, p.full_name AS partner_name, p.phone AS partner_phone,
           p.vehicle_type, p.vehicle_number,
           d.status, d.assigned_at, d.picked_up_at, d.delivered_at, d.delivery_notes
    FROM deliveries d
    LEFT JOIN orders o            ON o.order_id = d.order_id
    LEFT JOIN delivery_partners p ON p.partner_id = d.partner_id
"""


# ---------- Partners (admin) ----------

def list_partners(conn, free_only: bool) -> list[dict]:
    rows = conn.execute(f"{PARTNER_SELECT} ORDER BY p.rating DESC NULLS LAST, p.full_name").fetchall()
    return [r for r in rows if r["is_free"]] if free_only else rows


def get_partner(conn, partner_id: int) -> dict:
    row = conn.execute(f"{PARTNER_SELECT} WHERE p.partner_id = %s", (partner_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery partner not found")
    return row


def _check_partner_unique(conn, email: str | None, phone: str | None, exclude_id: int | None = None) -> None:
    taken = conn.execute(
        """
        SELECT email, phone FROM delivery_partners
        WHERE partner_id IS DISTINCT FROM %s AND (lower(email) = %s OR phone = %s)
        """,
        (exclude_id, email, phone),
    ).fetchone()
    if taken:
        field = "Email" if email and taken["email"].lower() == email else "Phone number"
        raise HTTPException(status.HTTP_409_CONFLICT, f"{field} is already used by another partner")


def create_partner(conn: psycopg.Connection, data: PartnerCreate) -> dict:
    email = data.email.lower()
    _check_partner_unique(conn, email, data.phone)
    try:
        new = conn.execute(
            """
            INSERT INTO delivery_partners (full_name, email, phone, vehicle_type, vehicle_number)
            VALUES (%s, %s, %s, %s, %s) RETURNING partner_id
            """,
            (data.full_name.strip(), email, data.phone, data.vehicle_type.value, data.vehicle_number),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or phone is already used by another partner")
    return get_partner(conn, new["partner_id"])


def update_partner(conn: psycopg.Connection, partner_id: int, data: PartnerUpdate) -> dict:
    get_partner(conn, partner_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Send at least one field to update")
    if "email" in changes:
        changes["email"] = changes["email"].lower()
    if "vehicle_type" in changes:
        changes["vehicle_type"] = changes["vehicle_type"].value
    if "email" in changes or "phone" in changes:
        _check_partner_unique(conn, changes.get("email"), changes.get("phone"), exclude_id=partner_id)

    set_clause, values = build_set_clause(changes)
    query = sql.SQL(
        "UPDATE delivery_partners SET {}, updated_at = CURRENT_TIMESTAMP WHERE partner_id = %s"
    ).format(set_clause)
    try:
        conn.execute(query, [*values, partner_id])
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or phone is already used by another partner")
    return get_partner(conn, partner_id)


def _set_partner_available(conn, partner_id: int | None, available: bool) -> None:
    if partner_id is not None:
        conn.execute(
            "UPDATE delivery_partners SET is_available = %s, updated_at = CURRENT_TIMESTAMP WHERE partner_id = %s",
            (available, partner_id),
        )


# ---------- Deliveries ----------

def get_delivery(conn, delivery_id: int) -> dict:
    row = conn.execute(f"{DELIVERY_SELECT} WHERE d.delivery_id = %s", (delivery_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
    return row


def latest_delivery_for_order(conn, order_id: int) -> dict | None:
    return conn.execute(
        f"{DELIVERY_SELECT} WHERE d.order_id = %s ORDER BY d.assigned_at DESC, d.delivery_id DESC LIMIT 1",
        (order_id,),
    ).fetchone()


def list_deliveries(conn, delivery_status: str | None, partner_id: int | None, limit: int, offset: int) -> list[dict]:
    conditions, params = [], []
    if delivery_status:
        conditions.append("d.status = %s")
        params.append(delivery_status)
    if partner_id is not None:
        conditions.append("d.partner_id = %s")
        params.append(partner_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return conn.execute(
        f"{DELIVERY_SELECT} {where} ORDER BY d.assigned_at DESC, d.delivery_id DESC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    ).fetchall()


def assign_partner(conn: psycopg.Connection, order_id: int, data: DeliveryAssign) -> dict:
    # 1. Lock the order and check it is ready for delivery
    order = conn.execute("SELECT order_id, status FROM orders WHERE order_id = %s FOR UPDATE", (order_id,)).fetchone()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order["status"] not in ASSIGNABLE_ORDER_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Can't assign a partner to an order that is '{order['status']}'. "
            "The order must be confirmed or preparing.",
        )

    # 2. Only one active (or finished) delivery per order. After 'failed' we may reassign.
    existing = conn.execute(
        "SELECT delivery_id, status FROM deliveries WHERE order_id = %s AND status <> 'failed' LIMIT 1",
        (order_id,),
    ).fetchone()
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This order already has delivery {existing['delivery_id']} ({existing['status']})",
        )

    # 3. Choose the partner: the one asked for, or the best-rated free one.
    #    FOR UPDATE stops two orders grabbing the same partner at the same moment.
    if data.partner_id is not None:
        partner = conn.execute(
            "SELECT partner_id FROM delivery_partners WHERE partner_id = %s FOR UPDATE", (data.partner_id,)
        ).fetchone()
        if partner is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery partner not found")
        if not get_partner(conn, data.partner_id)["is_free"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "This delivery partner is not free right now")
        partner_id = data.partner_id
    else:
        partner = conn.execute(
            """
            SELECT p.partner_id FROM delivery_partners p
            WHERE p.is_active AND p.is_available
              AND NOT EXISTS (SELECT 1 FROM deliveries d
                              WHERE d.partner_id = p.partner_id
                                AND d.status IN ('assigned', 'picked_up', 'on_the_way'))
            ORDER BY p.rating DESC NULLS LAST, p.partner_id
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        ).fetchone()
        if partner is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "No delivery partner is free right now. Try again soon.")
        partner_id = partner["partner_id"]

    # 4. Create the delivery and mark the partner busy
    new = conn.execute(
        """
        INSERT INTO deliveries (order_id, partner_id, status, delivery_notes)
        VALUES (%s, %s, 'assigned', %s) RETURNING delivery_id
        """,
        (order_id, partner_id, data.delivery_notes),
    ).fetchone()
    _set_partner_available(conn, partner_id, False)
    return get_delivery(conn, new["delivery_id"])


def update_delivery_status(conn: psycopg.Connection, delivery_id: int, new_status: str, notes: str | None) -> dict:
    delivery = conn.execute(
        "SELECT delivery_id, order_id, partner_id, status FROM deliveries WHERE delivery_id = %s FOR UPDATE",
        (delivery_id,),
    ).fetchone()
    if delivery is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")

    current = delivery["status"] or "assigned"
    if new_status not in ALLOWED_NEXT.get(current, set()):
        allowed = ", ".join(sorted(ALLOWED_NEXT.get(current, set()))) or "none (final status)"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Can't change delivery from '{current}' to '{new_status}'. Allowed next: {allowed}",
        )

    # 1. The delivery itself.
    #    %(s)s is used 3 times. "::text" tells PostgreSQL its type explicitly;
    #    without it, PostgreSQL sees varchar in one place and text in another
    #    and refuses the query ("inconsistent types deduced for parameter").
    conn.execute(
        """
        UPDATE deliveries
        SET status = %(s)s::text,
            picked_up_at   = CASE WHEN %(s)s::text = 'picked_up' THEN CURRENT_TIMESTAMP ELSE picked_up_at END,
            delivered_at   = CASE WHEN %(s)s::text = 'delivered' THEN CURRENT_TIMESTAMP ELSE delivered_at END,
            delivery_notes = COALESCE(%(notes)s::text, delivery_notes)
        WHERE delivery_id = %(id)s
        """,
        {"s": new_status, "notes": notes, "id": delivery_id},
    )

    order_id = delivery["order_id"]

    # 2. Keep the order in sync
    if new_status in ("picked_up", "on_the_way"):
        conn.execute(
            """
            UPDATE orders SET status = 'out_for_delivery', updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s AND status IN ('confirmed', 'preparing')
            """,
            (order_id,),
        )
    elif new_status == "delivered":
        conn.execute(
            """
            UPDATE orders SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
            """,
            (order_id,),
        )
        # Cash on delivery has now been collected
        conn.execute(
            """
            UPDATE payments SET payment_status = 'completed', paid_at = CURRENT_TIMESTAMP
            WHERE order_id = %s AND payment_method = 'cash' AND payment_status = 'pending'
            """,
            (order_id,),
        )

    # 3. Partner is free again when the delivery ends
    if new_status in ("delivered", "failed"):
        _set_partner_available(conn, delivery["partner_id"], True)

    return get_delivery(conn, delivery_id)


def handle_order_cancelled(conn: psycopg.Connection, order_id: int) -> None:
    """Called when an order is cancelled: stop its active delivery, free the partner."""
    active = conn.execute(
        "SELECT delivery_id, partner_id FROM deliveries WHERE order_id = %s AND status IN ('assigned','picked_up','on_the_way')",
        (order_id,),
    ).fetchall()
    for d in active:
        conn.execute(
            """
            UPDATE deliveries
            SET status = 'failed', delivery_notes = COALESCE(delivery_notes || ' | ', '') || 'Order cancelled'
            WHERE delivery_id = %s
            """,
            (d["delivery_id"],),
        )
        _set_partner_available(conn, d["partner_id"], True)


# ---------- Tracking (customer) ----------

def track_order(conn, order_id: int, customer_id: int | None) -> dict:
    order = conn.execute(
        """
        SELECT o.order_id, o.customer_id, o.status, o.total_amount, o.ordered_at, o.delivered_at,
               r.name AS restaurant_name
        FROM orders o LEFT JOIN restaurants r ON r.restaurant_id = o.restaurant_id
        WHERE o.order_id = %s
        """,
        (order_id,),
    ).fetchone()
    if order is None or (customer_id is not None and order["customer_id"] != customer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    delivery = latest_delivery_for_order(conn, order_id)
    payment = conn.execute(
        "SELECT payment_status FROM payments WHERE order_id = %s ORDER BY created_at DESC, payment_id DESC LIMIT 1",
        (order_id,),
    ).fetchone()

    flow = ["pending", "confirmed", "preparing", "out_for_delivery", "delivered"]
    reached = flow.index(order["status"]) if order["status"] in flow else -1
    d = delivery or {}
    timeline = [
        {"step": "Order placed",         "done": True,         "time": order["ordered_at"]},
        {"step": "Confirmed",            "done": reached >= 1, "time": None},
        {"step": "Preparing",            "done": reached >= 2, "time": None},
        {"step": "Partner assigned",     "done": bool(delivery) and d.get("status") != "failed", "time": d.get("assigned_at")},
        {"step": "Picked up",            "done": d.get("picked_up_at") is not None, "time": d.get("picked_up_at")},
        {"step": "Delivered",            "done": order["status"] == "delivered",
         "time": order["delivered_at"] or d.get("delivered_at")},
    ]

    messages = {
        "pending": "Waiting for the restaurant to confirm your order.",
        "confirmed": "Your order is confirmed.",
        "preparing": "The restaurant is preparing your food.",
        "out_for_delivery": "Your food is on the way!",
        "delivered": "Delivered. Enjoy your meal!",
        "cancelled": "This order was cancelled.",
    }
    message = messages.get(order["status"], "")
    if delivery and delivery["status"] in ACTIVE_STATUSES and delivery["partner_name"]:
        message += f" Delivery partner: {delivery['partner_name']} ({delivery['vehicle_type']})."

    return {
        "order_id": order["order_id"],
        "order_status": order["status"],
        "restaurant_name": order["restaurant_name"],
        "total_amount": order["total_amount"],
        "payment_status": payment["payment_status"] if payment else None,
        "delivery": delivery,
        "timeline": timeline,
        "message": message,
    }
