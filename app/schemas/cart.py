"""
cart.py (schemas) - cart requests and the cart summary response.
"""
from decimal import Decimal

from pydantic import BaseModel, Field

MAX_QUANTITY_PER_ITEM = 20


class CartItemAdd(BaseModel):
    food_id: int = Field(examples=[1])
    quantity: int = Field(default=1, ge=1, le=MAX_QUANTITY_PER_ITEM, examples=[2])
    replace_cart: bool = Field(
        default=False,
        description="Set true to empty the cart when adding food from a different restaurant",
    )


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=MAX_QUANTITY_PER_ITEM, examples=[3])


class CartItemOut(BaseModel):
    cart_item_id: int
    food_id: int | None
    name: str | None
    is_veg: bool | None
    quantity: int
    price_when_added: Decimal      # cart_items.unit_price
    current_price: Decimal | None  # food_items.price right now
    line_total: Decimal            # quantity x current_price (0 if unavailable)
    price_changed: bool
    is_available: bool


class CartOut(BaseModel):
    cart_id: int | None
    restaurant_id: int | None
    restaurant_name: str | None
    items: list[CartItemOut]
    item_count: int                # total quantity of available items
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    warnings: list[str]
