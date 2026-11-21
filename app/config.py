"""
config.py - reads all settings from the .env file.

Every other file imports settings from here, so secrets are read in
ONE place and never hardcoded anywhere else.
"""
import os

from dotenv import load_dotenv

load_dotenv()  # loads the .env file into environment variables


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Add it to your .env file.")
    return value


# Database
DATABASE_URL = _required("DATABASE_URL")

# JWT authentication (used from Step 5)
JWT_SECRET_KEY = _required("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# "development" or "production". In development, forgot-password returns the
# reset token in the response (because we don't send emails yet).
APP_ENV = os.getenv("APP_ENV", "production").lower()
IS_DEVELOPMENT = APP_ENV == "development"

# Password reset links expire after this many minutes
RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("RESET_TOKEN_EXPIRE_MINUTES", "15"))

# Admin users: comma-separated emails, e.g. "a@x.com,b@y.com"
ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("ADMIN_EMAILS", "").split(",")
    if email.strip()
}
