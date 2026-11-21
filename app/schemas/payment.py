"""
payment.py (schemas) - payment requests and responses.
Allowed values come from the CHECK constraints on the payments table.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import PaymentMethod, PaymentStatus


class PaymentCreate(BaseModel):
    payment_method: PaymentMethod = Field(examples=["upi"])
    simulate_failure: bool = Field(
        default=False,
        description="Testing only: pretend the online payment was declined",
    )


class PaymentStatusUpdate(BaseModel):
    payment_status: PaymentStatus = Field(examples=["completed"])


class PaymentOut(BaseModel):
    payment_id: int
    order_id: int | None
    customer_id: int | None
    amount: Decimal
    payment_method: str | None
    payment_status: str | None
    transaction_id: str | None
    paid_at: datetime | None
    created_at: datetime | None
    order_status: str | None
