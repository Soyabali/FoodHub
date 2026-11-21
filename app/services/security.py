"""
security.py - password hashing and JWT tokens.

Passwords:
- We NEVER store the real password. We store a bcrypt "hash": a one-way
  scrambled version. To check a login, we hash the typed password the same
  way and compare. bcrypt adds a random "salt", so two users with the same
  password still get different hashes.

JWT (JSON Web Token):
- After login, the client gets a signed token like "eyJhbGciOi...".
- It contains the customer_id and an expiry time, signed with JWT_SECRET_KEY.
- The client sends it back in every request header:
      Authorization: Bearer <token>
- Nobody can change the token without the secret key, so we can trust it.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET_KEY


# ---------- Passwords ----------

def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")          # 60-character string like "$2b$12$..."


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # The stored hash is not a valid bcrypt hash (e.g. the sample data's
        # placeholder hashes). Treat it as a wrong password.
        return False


# ---------- JWT tokens ----------

def create_access_token(customer_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(customer_id),            # "subject" = who this token belongs to
        "email": email,
        "iat": now,                         # issued at
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),  # expires at
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Returns the token's data, or None if it is invalid or expired."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
