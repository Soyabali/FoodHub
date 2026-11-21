"""
customer.py (schemas) - profile data in and out.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.auth import CustomerOut  # same output shape as registration


class CustomerUpdate(BaseModel):
    """All fields are optional: send only what you want to change (PATCH)."""
    full_name: str | None = Field(default=None, min_length=2, max_length=100, examples=["Neha V. Verma"])
    email: EmailStr | None = Field(default=None, max_length=150, examples=["neha.new@example.com"])
    phone: str | None = Field(default=None, pattern=r"^[0-9]{10,15}$", examples=["9876500002"])

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class CustomerProfile(CustomerOut):
    is_admin: bool
    address_count: int
    order_count: int


__all__ = ["CustomerOut", "CustomerUpdate", "CustomerProfile"]
