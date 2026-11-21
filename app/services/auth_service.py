"""
auth_service.py - business logic and SQL for registration and login.

All SQL uses %s placeholders ("parameterized queries"). psycopg sends the
values separately from the SQL text, so user input can never change the
query. That is what protects against SQL injection.
NEVER build SQL with f-strings or + using user input.
"""
import secrets

import psycopg
from fastapi import HTTPException, status

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.schemas.auth import RegisterRequest
from app.services.security import create_access_token, hash_password, verify_password

MAX_LOGIN_ATTEMPTS = 5

CUSTOMER_COLUMNS = "customer_id, full_name, email, phone, is_active, created_at"


def register_customer(conn: psycopg.Connection, data: RegisterRequest) -> dict:
    email = data.email.lower()

    # 1. Is the email or phone already used?
    existing = conn.execute(
        """
        SELECT email, phone FROM customers
        WHERE lower(email) = %s OR phone = %s
        """,
        (email, data.phone),
    ).fetchone()
    if existing:
        field = "Email" if existing["email"].lower() == email else "Phone number"
        raise HTTPException(status.HTTP_409_CONFLICT, f"{field} is already registered")

    try:
        # 2. Create the customer (profile)
        customer = conn.execute(
            f"""
            INSERT INTO customers (full_name, email, phone)
            VALUES (%s, %s, %s)
            RETURNING {CUSTOMER_COLUMNS}
            """,
            (data.full_name, email, data.phone),
        ).fetchone()

        # 3. Save the login credentials (hashed password only)
        conn.execute(
            """
            INSERT INTO login (customer_id, email, password_hash)
            VALUES (%s, %s, %s)
            """,
            (customer["customer_id"], email, hash_password(data.password)),
        )

        # 4. Record the registration (token kept for future email verification)
        conn.execute(
            """
            INSERT INTO registration (customer_id, email, verification_token)
            VALUES (%s, %s, %s)
            """,
            (customer["customer_id"], email, secrets.token_urlsafe(32)),
        )
    except psycopg.errors.UniqueViolation:
        # Two people registered the same email/phone at the same moment.
        # Raising here rolls back steps 2-4 together.
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or phone number is already registered")

    return customer


def login_customer(conn: psycopg.Connection, email: str, password: str) -> dict:
    wrong_credentials = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Find the login row together with the customer's profile
    user = conn.execute(
        """
        SELECT l.login_id, l.password_hash, l.login_attempts, l.is_locked,
               c.customer_id, c.full_name, c.email, c.phone, c.is_active, c.created_at
        FROM login l
        JOIN customers c ON c.customer_id = l.customer_id
        WHERE lower(l.email) = %s
        """,
        (email.lower(),),
    ).fetchone()

    if user is None:
        raise wrong_credentials           # same message: don't reveal which emails exist

    if user["is_locked"]:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Account locked after too many failed logins. Reset your password to unlock it.",
        )
    if not user["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    # 2. Wrong password: count the attempt, lock after MAX_LOGIN_ATTEMPTS
    if not verify_password(password, user["password_hash"]):
        conn.execute(
            """
            UPDATE login
            SET login_attempts = COALESCE(login_attempts, 0) + 1,
                is_locked = (COALESCE(login_attempts, 0) + 1 >= %s),
                updated_at = CURRENT_TIMESTAMP
            WHERE login_id = %s
            """,
            (MAX_LOGIN_ATTEMPTS, user["login_id"]),
        )
        # Commit NOW: raising the error below would otherwise roll this back.
        conn.commit()
        raise wrong_credentials

    # 3. Correct password: reset the counter and record the login time
    conn.execute(
        """
        UPDATE login
        SET login_attempts = 0, last_login = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE login_id = %s
        """,
        (user["login_id"],),
    )

    customer = {key: user[key] for key in ("customer_id", "full_name", "email", "phone", "is_active", "created_at")}
    return {
        "access_token": create_access_token(customer["customer_id"], customer["email"]),
        "token_type": "bearer",
        "expires_in_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
        "customer": customer,
    }
