"""
customer_service.py - view, update and deactivate the customer's own profile.

The email is stored in 3 tables (customers, login, registration). When the
customer changes their email, we update all three in ONE transaction so
they never get out of sync.
"""
import psycopg
from fastapi import HTTPException, status
from psycopg import sql

from app.schemas.customer import CustomerUpdate
from app.services.sql_helpers import build_set_clause

CUSTOMER_COLUMNS = "customer_id, full_name, email, phone, is_active, created_at"


def get_profile(conn: psycopg.Connection, customer: dict) -> dict:
    counts = conn.execute(
        """
        SELECT
            (SELECT count(*) FROM addresses WHERE customer_id = %(id)s) AS address_count,
            (SELECT count(*) FROM orders    WHERE customer_id = %(id)s) AS order_count
        """,
        {"id": customer["customer_id"]},          # named placeholders: reuse one value
    ).fetchone()
    return {**customer, **counts}


def update_profile(conn: psycopg.Connection, customer_id: int, data: CustomerUpdate) -> dict:
    # Only the fields the client actually sent (and that aren't null)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Send at least one field to update")

    if "email" in changes:
        changes["email"] = changes["email"].lower()

    # 1. Make sure the new email / phone isn't used by ANOTHER customer
    if "email" in changes or "phone" in changes:
        taken = conn.execute(
            """
            SELECT email, phone FROM customers
            WHERE customer_id <> %s AND (lower(email) = %s OR phone = %s)
            """,
            (customer_id, changes.get("email"), changes.get("phone")),
        ).fetchone()
        if taken:
            field = "Email" if changes.get("email") and taken["email"].lower() == changes["email"] else "Phone number"
            raise HTTPException(status.HTTP_409_CONFLICT, f"{field} is already used by another account")

    try:
        # 2. Update the customers table
        set_clause, values = build_set_clause(changes)
        query = sql.SQL(
            "UPDATE customers SET {}, updated_at = CURRENT_TIMESTAMP "
            "WHERE customer_id = %s RETURNING " + CUSTOMER_COLUMNS
        ).format(set_clause)
        updated = conn.execute(query, [*values, customer_id]).fetchone()

        # 3. Keep the email in login and registration in sync
        if "email" in changes:
            conn.execute(
                "UPDATE login SET email = %s, updated_at = CURRENT_TIMESTAMP WHERE customer_id = %s",
                (changes["email"], customer_id),
            )
            conn.execute(
                "UPDATE registration SET email = %s WHERE customer_id = %s",
                (changes["email"], customer_id),
            )
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or phone number is already used by another account")

    return updated


def deactivate_account(conn: psycopg.Connection, customer_id: int) -> None:
    """Soft delete: the row stays (so order and payment history is kept),
    but the account can no longer log in or use its token."""
    conn.execute(
        "UPDATE customers SET is_active = false, updated_at = CURRENT_TIMESTAMP WHERE customer_id = %s",
        (customer_id,),
    )
    # An active cart has no use any more
    conn.execute(
        """
        UPDATE carts SET status = 'abandoned', updated_at = CURRENT_TIMESTAMP
        WHERE customer_id = %s AND status = 'active'
        """,
        (customer_id,),
    )
