"""
auth.py (schemas) - the shape of data going IN and OUT of the auth APIs.

Pydantic checks every request automatically. If a field is missing or
invalid, FastAPI returns 422 with a clear message and our code never runs.
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


def validate_password_rules(value: str) -> str:
    """Shared password rules for register, reset and change password."""
    if len(value.encode("utf-8")) > 72:            # bcrypt's limit
        raise ValueError("Password must be at most 72 bytes long")
    if not any(c.isdigit() for c in value) or not any(c.isalpha() for c in value):
        raise ValueError("Password must contain at least one letter and one number")
    return value


# ---------- Registration / Login (Step 5) ----------

class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100, examples=["Neha Verma"])
    email: EmailStr = Field(max_length=150, examples=["neha@example.com"])
    phone: str = Field(pattern=r"^[0-9]{10,15}$", examples=["9876500001"])
    password: str = Field(min_length=8, examples=["Neha@1234"])

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password_rules(value)


class LoginRequest(BaseModel):
    email: EmailStr = Field(examples=["neha@example.com"])
    password: str = Field(min_length=1, examples=["Neha@1234"])


class CustomerOut(BaseModel):
    customer_id: int
    full_name: str
    email: str
    phone: str
    is_active: bool | None
    created_at: datetime | None


class RegisterResponse(BaseModel):
    message: str
    customer: CustomerOut


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    customer: CustomerOut


class CurrentCustomer(CustomerOut):
    is_admin: bool


# ---------- Password management (Step 6) ----------

class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(examples=["neha@example.com"])


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None        # only filled in development mode
    expires_in_minutes: int | None = None


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(min_length=10, examples=["paste-the-token-here"])
    new_password: str = Field(min_length=8, examples=["NewPass@123"])

    @field_validator("new_password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password_rules(value)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(examples=["Neha@1234"])
    new_password: str = Field(min_length=8, examples=["Neha@5678"])

    @field_validator("new_password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password_rules(value)


class MessageResponse(BaseModel):
    message: str
