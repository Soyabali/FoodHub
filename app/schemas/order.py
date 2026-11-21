"""
order.py (schemas) - placing orders and showing order history/details.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import OrderStatus


class OrderCreate(BaseModel):
    delivery_address_id: int | None = Field(
        default=None, description="Leave empty to use your default address", examples=[None]
    )
    special_instructions: str | None = Field(default=None, max_length=500, examples=["Less spicy please"])


class OrderStatusUpdate(BaseModel):
    status: OrderStatus = Field(examples=["confirmed"])


class OrderItemOut(BaseModel):
    order_item_id: int
    food_id: int | None
    name: str | None
    quantity: int
    unit_price: Decimal
    total_price: Decimal | None


class OrderAddressOut(BaseModel):
    address_id: int
    address_label: str | None
    street: str
    city: str
    state: str
    zip_code: str
    country: str | None


class OrderSummary(BaseModel):
    order_id: int
    customer_id: int | None
    restaurant_id: int | None
    restaurant_name: str | None
    status: str | None
    item_count: int
    subtotal: Decimal
    delivery_fee: Decimal | None
    discount: Decimal | None
    total_amount: Decimal
    ordered_at: datetime | None
    delivered_at: datetime | None


class OrderDetail(OrderSummary):
    special_instructions: str | None
    updated_at: datetime | None
    delivery_address: OrderAddressOut | None
    items: list[OrderItemOut]
    can_cancel: bool
    payment_status: str | None     # latest payment of this order (None = not paid yet)
