"""
restaurant.py (schemas) - restaurants in and out.
Limits match the real restaurants table (name varchar(150), phone varchar(15),
zip_code varchar(10), rating numeric(2,1) between 0 and 5, email unique).
"""
from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

PHONE_PATTERN = r"^[0-9]{10,15}$"
ZIP_PATTERN = r"^[A-Za-z0-9 -]{3,10}$"


class RestaurantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150, examples=["Tandoori Nights"])
    email: EmailStr = Field(max_length=150, examples=["tandoori@foodiehub.com"])
    phone: str = Field(pattern=PHONE_PATTERN, examples=["9333333333"])
    street: str = Field(min_length=3, max_length=255, examples=["7 Curry Lane"])
    city: str = Field(min_length=2, max_length=100, examples=["Mumbai"])
    state: str = Field(min_length=2, max_length=100, examples=["Maharashtra"])
    zip_code: str = Field(pattern=ZIP_PATTERN, examples=["400004"])
    opening_time: time = Field(default=time(9, 0), examples=["10:00:00"])
    closing_time: time = Field(default=time(22, 0), examples=["23:00:00"])


class RestaurantUpdate(BaseModel):
    """All optional (PATCH). is_active=true re-opens a deactivated restaurant."""
    name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    street: str | None = Field(default=None, min_length=3, max_length=255)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=100)
    zip_code: str | None = Field(default=None, pattern=ZIP_PATTERN)
    opening_time: time | None = None
    closing_time: time | None = None
    rating: Decimal | None = Field(default=None, ge=0, le=5, max_digits=2, decimal_places=1)
    is_active: bool | None = None


class RestaurantOut(BaseModel):
    restaurant_id: int
    name: str
    email: str
    phone: str
    street: str
    city: str
    state: str
    zip_code: str
    opening_time: time | None
    closing_time: time | None
    rating: Decimal | None
    is_active: bool | None
    created_at: datetime | None
    updated_at: datetime | None


class RestaurantDetail(RestaurantOut):
    menu_item_count: int
