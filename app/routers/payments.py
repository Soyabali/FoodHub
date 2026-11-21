"""
payments.py (router)
  Customer:  pay for an order, payments of an order, payment history, payment status
  Admin:     everyone's payments, change payment status (cash collected, refund)
"""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.database import DB
from app.dependencies import AdminUser, CurrentUser
from app.models.enums import PaymentStatus
from app.schemas.payment import PaymentCreate, PaymentOut, PaymentStatusUpdate
from app.services import payment_service

router = APIRouter(tags=["Payments"])


def _scope(customer: dict) -> int | None:
    """Admins can see everything (None), customers only their own."""
    return None if customer["is_admin"] else customer["customer_id"]


@router.post("/orders/{order_id}/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def pay_for_order(order_id: int, data: PaymentCreate, customer: CurrentUser, conn: DB):
    return payment_service.pay_for_order(conn, order_id, customer["customer_id"], data)


@router.get("/orders/{order_id}/payments", response_model=list[PaymentOut])
def order_payments(order_id: int, customer: CurrentUser, conn: DB):
    return payment_service.list_order_payments(conn, order_id, _scope(customer))


@router.get("/payments", response_model=list[PaymentOut])
def payment_history(
    customer: CurrentUser,
    conn: DB,
    payment_status: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    all_customers: Annotated[bool, Query(description="Admins only")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if all_customers and not customer["is_admin"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    customer_id = None if all_customers else customer["customer_id"]
    return payment_service.list_payments(
        conn, customer_id, payment_status.value if payment_status else None, limit, offset
    )


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def payment_details(payment_id: int, customer: CurrentUser, conn: DB):
    return payment_service.get_payment(conn, payment_id, _scope(customer))


@router.patch("/payments/{payment_id}/status", response_model=PaymentOut)
def update_payment_status(payment_id: int, data: PaymentStatusUpdate, admin: AdminUser, conn: DB):
    return payment_service.update_status(conn, payment_id, data.payment_status.value)
