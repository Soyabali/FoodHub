"""
address.py (schemas) - delivery addresses in and out.

Field limits match the real columns in the addresses table:
street varchar(255), city/state/country varchar(100), zip_code varchar(10),
address_label must be Home, Work or Other (CHECK constraint).
"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AddressLabel

ZIP_PATTERN = r"^[A-Za-z0-9 -]{3,10}$"


class AddressCreate(BaseModel):
    address_label: AddressLabel = AddressLabel.home
    street: str = Field(min_length=3, max_length=255, examples=["221 Linking Road"])
    city: str = Field(min_length=2, max_length=100, examples=["Mumbai"])
    state: str = Field(min_length=2, max_length=100, examples=["Maharashtra"])
    zip_code: str = Field(pattern=ZIP_PATTERN, examples=["400050"])
    country: str = Field(default="India", min_length=2, max_length=100)
    is_default: bool = False


class AddressUpdate(BaseModel):
    """All fields optional: send only what you want to change (PATCH)."""
    address_label: AddressLabel | None = None
    street: str | None = Field(default=None, min_length=3, max_length=255)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=100)
    zip_code: str | None = Field(default=None, pattern=ZIP_PATTERN)
    country: str | None = Field(default=None, min_length=2, max_length=100)
    is_default: bool | None = None


class AddressOut(BaseModel):
    address_id: int
    customer_id: int | None
    address_label: str | None
    street: str
    city: str
    state: str
    zip_code: str
    country: str | None
    is_default: bool | None
    created_at: datetime | None
