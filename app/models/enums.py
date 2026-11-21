"""
enums.py - allowed values that match the CHECK constraints in the database.

These were copied from the real Neon schema (Step 3 inspection). Using them
in Pydantic schemas means FastAPI rejects bad values with a clear 422 error
BEFORE the query reaches the database.
"""
from enum import Enum


class AddressLabel(str, Enum):
    home = "Home"
    work = "Work"
    other = "Other"


class CartStatus(str, Enum):
    active = "active"
    ordered = "ordered"
    abandoned = "abandoned"


class OrderStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    preparing = "preparing"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    cancelled = "cancelled"


class PaymentMethod(str, Enum):
    cash = "cash"
    card = "card"
    upi = "upi"
    wallet = "wallet"
    net_banking = "net_banking"


class PaymentStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


class DeliveryStatus(str, Enum):
    assigned = "assigned"
    picked_up = "picked_up"
    on_the_way = "on_the_way"
    delivered = "delivered"
    failed = "failed"


class VehicleType(str, Enum):
    bike = "bike"
    scooter = "scooter"
    bicycle = "bicycle"
    car = "car"


class PasswordChangeReason(str, Enum):
    user_request = "user_request"
    reset = "reset"
    admin_force = "admin_force"
