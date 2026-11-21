"""
delivery.py (schemas) - delivery partners, deliveries and order tracking.
Allowed values come from the CHECK constraints on deliveries.status and
delivery_partners.vehicle_type; rating is numeric(2,1) between 0 and 5.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import DeliveryStatus, VehicleType

PHONE_PATTERN = r"^[0-9]{10,15}$"


# ---------- Delivery partners ----------

class PartnerCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100, examples=["Kiran Patil"])
    email: EmailStr = Field(max_length=150, examples=["kiran@delivery.com"])
    phone: str = Field(pattern=PHONE_PATTERN, examples=["9700000005"])
    vehicle_type: VehicleType = VehicleType.bike
    vehicle_number: str | None = Field(default=None, max_length=20, examples=["MH12XY9876"])


class PartnerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    vehicle_type: VehicleType | None = None
    vehicle_number: str | None = Field(default=None, max_length=20)
    rating: Decimal | None = Field(default=None, ge=0, le=5, max_digits=2, decimal_places=1)
    is_available: bool | None = None
    is_active: bool | None = None


class PartnerOut(BaseModel):
    partner_id: int
    full_name: str
    email: str
    phone: str
    vehicle_type: str | None
    vehicle_number: str | None
    rating: Decimal | None
    is_available: bool | None
    is_active: bool | None
    active_delivery_id: int | None      # the delivery they are on right now, if any
    is_free: bool                       # active + available + not on a delivery


# ---------- Deliveries ----------

class DeliveryAssign(BaseModel):
    partner_id: int | None = Field(
        default=None, description="Leave empty to auto-pick the best-rated free partner"
    )
    delivery_notes: str | None = Field(default=None, max_length=500, examples=["Call on arrival"])


class DeliveryStatusUpdate(BaseModel):
    status: DeliveryStatus = Field(examples=["picked_up"])
    delivery_notes: str | None = Field(default=None, max_length=500)


class DeliveryOut(BaseModel):
    delivery_id: int
    order_id: int | None
    order_status: str | None
    partner_id: int | None
    partner_name: str | None
    partner_phone: str | None
    vehicle_type: str | None
    vehicle_number: str | None
    status: str | None
    assigned_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    delivery_notes: str | None


# ---------- Tracking ----------

class TrackingStep(BaseModel):
    step: str
    done: bool
    time: datetime | None


class TrackingOut(BaseModel):
    order_id: int
    order_status: str | None
    restaurant_name: str | None
    total_amount: Decimal
    payment_status: str | None
    delivery: DeliveryOut | None
    timeline: list[TrackingStep]
    message: str
