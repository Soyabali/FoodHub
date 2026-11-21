"""
password_service.py - forgot, reset and change password.

Tables used:
  forgot_password  - one row per reset request (token, expiry, is_used)
  login            - where the password hash lives
  change_password  - history of every password change (old hash, new hash, reason)

Security notes:
- The reset token is a long random string. We store only its SHA-256 hash,
  so someone who reads the database can't use the tokens.
- Each token works once (is_used) and expires after 15 minutes.
- forgot-password always gives the same answer, so nobody can use it to
  find out which emails are registered.
"""
import hashlib
import secrets

import psycopg
from fastapi import HTTPException, status

from app.config import IS_DEVELOPMENT, RESET_TOKEN_EXPIRE_MINUTES
from app.services.security import hash_password, verify_password

GENERIC_FORGOT_MESSAGE = "If this email is registered, a password reset link has been sent."


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _save_new_password(conn, login_id: int, customer_id: int, old_hash: str, new_password: str, reason: str):
    """Update login with the new hash and record the change in change_password."""
    new_hash = hash_password(new_password)

    conn.execute(
        """
        UPDATE login
        SET password_hash = %s,
            login_attempts = 0,
            is_locked = false,              -- a password reset also unlocks the account
            updated_at = CURRENT_TIMESTAMP
        WHERE login_id = %s
        """,
        (new_hash, login_id),
    )
    conn.execute(
        """
        INSERT INTO change_password (customer_id, old_password_hash, new_password_hash, change_reason)
        VALUES (%s, %s, %s, %s)
        """,
        (customer_id, old_hash, new_hash, reason),
    )


def forgot_password(conn: psycopg.Connection, email: str) -> dict:
    email = email.lower()
    response = {"message": GENERIC_FORGOT_MESSAGE}

    customer = conn.execute(
        "SELECT customer_id, email FROM customers WHERE lower(email) = %s AND is_active = true",
        (email,),
    ).fetchone()
    if customer is None:
        return response                       # same answer as success (no email enumeration)

    # Cancel any older unused tokens, so only the newest one works
    conn.execute(
        "UPDATE forgot_password SET is_used = true WHERE customer_id = %s AND is_used = false",
        (customer["customer_id"],),
    )

    token = secrets.token_urlsafe(32)         # e.g. "q3Zt...": sent to the user
    conn.execute(
        """
        INSERT INTO forgot_password (customer_id, email, reset_token, token_expiry)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP + make_interval(mins => %s))
        """,
        (customer["customer_id"], customer["email"], _hash_token(token), RESET_TOKEN_EXPIRE_MINUTES),
    )

    # A real app would EMAIL the token here. Until then, in development we
    # return it in the response so you can test with Swagger.
    if IS_DEVELOPMENT:
        response["reset_token"] = token
        response["expires_in_minutes"] = RESET_TOKEN_EXPIRE_MINUTES
    return response


def reset_password(conn: psycopg.Connection, token: str, new_password: str) -> None:
    # Find a token that is unused AND not expired. FOR UPDATE locks the row,
    # so the same token can't be used twice at the same moment.
    row = conn.execute(
        """
        SELECT f.forgot_id, f.customer_id, l.login_id, l.password_hash
        FROM forgot_password f
        JOIN login l ON l.customer_id = f.customer_id
        JOIN customers c ON c.customer_id = f.customer_id
        WHERE f.reset_token = %s
          AND f.is_used = false
          AND f.token_expiry > CURRENT_TIMESTAMP
          AND c.is_active = true
        FOR UPDATE OF f
        """,
        (_hash_token(token),),
    ).fetchone()

    if row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    # All three changes happen in ONE transaction: all succeed or none do.
    conn.execute("UPDATE forgot_password SET is_used = true WHERE forgot_id = %s", (row["forgot_id"],))
    _save_new_password(conn, row["login_id"], row["customer_id"], row["password_hash"], new_password, "reset")


def change_password(conn: psycopg.Connection, customer_id: int, current_password: str, new_password: str) -> None:
    row = conn.execute(
        "SELECT login_id, password_hash FROM login WHERE customer_id = %s",
        (customer_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Login record not found")

    if not verify_password(current_password, row["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")

    if verify_password(new_password, row["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different from the current password")

    _save_new_password(conn, row["login_id"], customer_id, row["password_hash"], new_password, "user_request")
