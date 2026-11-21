"""
dependencies.py - reusable "who is calling?" checks for protected endpoints.

Usage in any router:
    def my_endpoint(customer: CurrentUser): ...     # any logged-in customer
    def admin_endpoint(admin: AdminUser): ...       # only emails in ADMIN_EMAILS
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import ADMIN_EMAILS
from app.database import DB
from app.services.security import decode_access_token

# Reads the header "Authorization: Bearer <token>".
# In Swagger: click "Authorize" and paste the access_token from /auth/login.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the access_token you got from POST /auth/login",
)

Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def _customer_from_token(conn, token: str) -> dict:
    not_authenticated = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or expired token. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None or not str(payload.get("sub", "")).isdigit():
        raise not_authenticated

    # Load the customer fresh from the database, so a deactivated
    # account is blocked immediately even if its token hasn't expired.
    customer = conn.execute(
        """
        SELECT customer_id, full_name, email, phone, is_active, created_at
        FROM customers WHERE customer_id = %s
        """,
        (int(payload["sub"]),),
    ).fetchone()

    if customer is None or not customer["is_active"]:
        raise not_authenticated

    customer["is_admin"] = customer["email"].lower() in ADMIN_EMAILS
    return customer


def get_current_customer(conn: DB, credentials: Credentials) -> dict:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated. Log in with POST /auth/login, then click Authorize and paste the token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _customer_from_token(conn, credentials.credentials)


def require_admin(customer: Annotated[dict, Depends(get_current_customer)]) -> dict:
    if not customer["is_admin"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return customer


def get_optional_customer(conn: DB, credentials: Credentials) -> dict | None:
    """For public endpoints: returns the customer if a valid token was sent, else None.
    Used so admins can see extra data (e.g. inactive restaurants) on public lists."""
    if credentials is None:
        return None
    try:
        return _customer_from_token(conn, credentials.credentials)
    except HTTPException:
        return None


def is_admin(customer: dict | None) -> bool:
    return bool(customer and customer["is_admin"])


CurrentUser = Annotated[dict, Depends(get_current_customer)]
AdminUser = Annotated[dict, Depends(require_admin)]
OptionalUser = Annotated[dict | None, Depends(get_optional_customer)]
