"""
food.py (schemas) - categories and food items.
Limits match the real tables: category_name varchar(100) unique,
food name varchar(150), price numeric(8,2) > 0 (so max 999999.99).
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# ---------- Categories ----------

class CategoryCreate(BaseModel):
    category_name: str = Field(min_length=2, max_length=100, examples=["Desserts"])
    description: str | None = Field(default=None, examples=["Sweet treats"])


class CategoryUpdate(BaseModel):
    category_name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None
    is_active: bool | None = None


class CategoryOut(BaseModel):
    category_id: int
    category_name: str
    description: str | None
    is_active: bool | None
    created_at: datetime | None


# ---------- Food items ----------

Price = Decimal  # stored as numeric(8,2)


class FoodCreate(BaseModel):
    restaurant_id: int = Field(examples=[1])
    category_id: int | None = Field(default=None, examples=[3])
    name: str = Field(min_length=2, max_length=150, examples=["Paneer Tikka"])
    description: str | None = Field(default=None, examples=["Grilled cottage cheese with spices"])
    price: Price = Field(gt=0, max_digits=8, decimal_places=2, examples=["249.00"])
    is_veg: bool = True
    is_available: bool = True
    image_url: str | None = Field(default=None, max_length=2000)


class FoodUpdate(BaseModel):
    """All optional (PATCH). restaurant_id can't be changed: create a new item instead."""
    category_id: int | None = None
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    price: Price | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)
    is_veg: bool | None = None
    is_available: bool | None = None
    image_url: str | None = Field(default=None, max_length=2000)


class FoodOut(BaseModel):
    food_id: int
    restaurant_id: int | None
    restaurant_name: str | None
    category_id: int | None
    category_name: str | None
    name: str
    description: str | None
    price: Decimal
    is_veg: bool | None
    is_available: bool | None
    image_url: str | None
    created_at: datetime | None
    updated_at: datetime | None
