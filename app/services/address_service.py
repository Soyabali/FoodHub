"""
address_service.py - a customer's delivery addresses.

Rules:
- Every query includes "AND customer_id = %s", so a customer can only ever
  see or change THEIR OWN addresses. Someone else's address_id gives 404.
- Only one address per customer can be the default. Before setting a new
  default, we unset the old one (same transaction).
- The first address a customer adds becomes the default automatically.
- An address used by a past order can't be deleted: the database would set
  orders.delivery_address_id to NULL and the order would lose its address.
"""
import psycopg
from fastapi import HTTPException, status
from psycopg import sql

from app.schemas.address import AddressCreate, AddressUpdate
from app.services.sql_helpers import build_set_clause

ADDRESS_COLUMNS = (
    "address_id, customer_id, address_label, street, city, state, "
    "zip_code, country, is_default, created_at"
)


def _get_own_address(conn, customer_id: int, address_id: int) -> dict:
    address = conn.execute(
        f"SELECT {ADDRESS_COLUMNS} FROM addresses WHERE address_id = %s AND customer_id = %s",
        (address_id, customer_id),
    ).fetchone()
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Address not found")
    return address


def _clear_default(conn, customer_id: int) -> None:
    conn.execute(
        "UPDATE addresses SET is_default = false WHERE customer_id = %s AND is_default = true",
        (customer_id,),
    )


def list_addresses(conn: psycopg.Connection, customer_id: int) -> list[dict]:
    return conn.execute(
        f"""
        SELECT {ADDRESS_COLUMNS} FROM addresses
        WHERE customer_id = %s
        ORDER BY is_default DESC, created_at, address_id
        """,
        (customer_id,),
    ).fetchall()


def get_address(conn: psycopg.Connection, customer_id: int, address_id: int) -> dict:
    return _get_own_address(conn, customer_id, address_id)


def add_address(conn: psycopg.Connection, customer_id: int, data: AddressCreate) -> dict:
    has_any = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM addresses WHERE customer_id = %s) AS has_any",
        (customer_id,),
    ).fetchone()["has_any"]

    make_default = data.is_default or not has_any      # first address -> default
    if make_default:
        _clear_default(conn, customer_id)

    return conn.execute(
        f"""
        INSERT INTO addresses
            (customer_id, address_label, street, city, state, zip_code, country, is_default)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING {ADDRESS_COLUMNS}
        """,
        (customer_id, data.address_label.value, data.street.strip(), data.city.strip(),
         data.state.strip(), data.zip_code.strip(), data.country.strip(), make_default),
    ).fetchone()


def update_address(conn: psycopg.Connection, customer_id: int, address_id: int, data: AddressUpdate) -> dict:
    _get_own_address(conn, customer_id, address_id)      # 404 if not theirs

    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Send at least one field to update")
    if "address_label" in changes:
        changes["address_label"] = changes["address_label"].value

    if changes.get("is_default") is True:
        _clear_default(conn, customer_id)

    set_clause, values = build_set_clause(changes)
    query = sql.SQL(
        "UPDATE addresses SET {} WHERE address_id = %s AND customer_id = %s RETURNING " + ADDRESS_COLUMNS
    ).format(set_clause)
    return conn.execute(query, [*values, address_id, customer_id]).fetchone()


def delete_address(conn: psycopg.Connection, customer_id: int, address_id: int) -> None:
    address = _get_own_address(conn, customer_id, address_id)

    used = conn.execute(
        "SELECT count(*) AS n FROM orders WHERE delivery_address_id = %s",
        (address_id,),
    ).fetchone()["n"]
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This address is used by {used} order(s) and can't be deleted, "
            "so your order history keeps its delivery address.",
        )

    conn.execute("DELETE FROM addresses WHERE address_id = %s AND customer_id = %s", (address_id, customer_id))

    # If we deleted the default, make the newest remaining address the default
    if address["is_default"]:
        conn.execute(
            """
            UPDATE addresses SET is_default = true
            WHERE address_id = (
                SELECT address_id FROM addresses
                WHERE customer_id = %s
                ORDER BY created_at DESC, address_id DESC
                LIMIT 1
            )
            """,
            (customer_id,),
        )
