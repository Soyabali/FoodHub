"""
orders.py (router)
  Customer:  place order, order history, order details, cancel
  Admin:     see all orders (all_customers=true), any order's details, update status
"""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.database import DB
from app.dependencies import AdminUser, CurrentUser
from app.models.enums import OrderStatus
from app.schemas.order import OrderCreate, OrderDetail, OrderStatusUpdate, OrderSummary
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=OrderDetail, status_code=status.HTTP_201_CREATED)
def place_order(data: OrderCreate, customer: CurrentUser, conn: DB):
    return order_service.place_order(conn, customer["customer_id"], data)


@router.get("", response_model=list[OrderSummary])
def order_history(
    customer: CurrentUser,
    conn: DB,
    order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
    all_customers: Annotated[bool, Query(description="Admins only: orders of every customer")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if all_customers and not customer["is_admin"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    customer_id = None if all_customers else customer["customer_id"]
    return order_service.list_orders(
        conn, customer_id, order_status.value if order_status else None, limit, offset
    )


@router.get("/{order_id}", response_model=OrderDetail)
def order_details(order_id: int, customer: CurrentUser, conn: DB):
    # Admins can open any order; customers only their own
    customer_id = None if customer["is_admin"] else customer["customer_id"]
    return order_service.get_order(conn, order_id, customer_id)


@router.post("/{order_id}/cancel", response_model=OrderDetail)
def cancel_order(order_id: int, customer: CurrentUser, conn: DB):
    return order_service.cancel_order(conn, order_id, customer["customer_id"])


@router.patch("/{order_id}/status", response_model=OrderDetail)
def update_order_status(order_id: int, data: OrderStatusUpdate, admin: AdminUser, conn: DB):
    return order_service.update_status(conn, order_id, data.status)
