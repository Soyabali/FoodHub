"""
delivery.py (router)
  Admin:     delivery partners (list, add, edit), assign partner,
             list deliveries, update delivery status
  Customer:  track my order
Delivery partners can't log in (their table has no password), so an admin
updates delivery status on their behalf.
"""
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.database import DB
from app.dependencies import AdminUser, CurrentUser
from app.models.enums import DeliveryStatus
from app.schemas.delivery import (
    DeliveryAssign, DeliveryOut, DeliveryStatusUpdate, PartnerCreate, PartnerOut, PartnerUpdate, TrackingOut,
)
from app.services import delivery_service

router = APIRouter(tags=["Delivery"])


# ---------- Partners (admin) ----------

@router.get("/delivery-partners", response_model=list[PartnerOut])
def list_partners(admin: AdminUser, conn: DB, free_only: bool = False):
    return delivery_service.list_partners(conn, free_only)


@router.get("/delivery-partners/{partner_id}", response_model=PartnerOut)
def get_partner(partner_id: int, admin: AdminUser, conn: DB):
    return delivery_service.get_partner(conn, partner_id)


@router.post("/delivery-partners", response_model=PartnerOut, status_code=status.HTTP_201_CREATED)
def create_partner(data: PartnerCreate, admin: AdminUser, conn: DB):
    return delivery_service.create_partner(conn, data)


@router.patch("/delivery-partners/{partner_id}", response_model=PartnerOut)
def update_partner(partner_id: int, data: PartnerUpdate, admin: AdminUser, conn: DB):
    return delivery_service.update_partner(conn, partner_id, data)


# ---------- Deliveries (admin) ----------

@router.post("/orders/{order_id}/delivery", response_model=DeliveryOut, status_code=status.HTTP_201_CREATED)
def assign_partner(order_id: int, data: DeliveryAssign, admin: AdminUser, conn: DB):
    return delivery_service.assign_partner(conn, order_id, data)


@router.get("/deliveries", response_model=list[DeliveryOut])
def list_deliveries(
    admin: AdminUser,
    conn: DB,
    delivery_status: Annotated[DeliveryStatus | None, Query(alias="status")] = None,
    partner_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return delivery_service.list_deliveries(
        conn, delivery_status.value if delivery_status else None, partner_id, limit, offset
    )


@router.get("/deliveries/{delivery_id}", response_model=DeliveryOut)
def get_delivery(delivery_id: int, admin: AdminUser, conn: DB):
    return delivery_service.get_delivery(conn, delivery_id)


@router.patch("/deliveries/{delivery_id}/status", response_model=DeliveryOut)
def update_delivery_status(delivery_id: int, data: DeliveryStatusUpdate, admin: AdminUser, conn: DB):
    return delivery_service.update_delivery_status(conn, delivery_id, data.status.value, data.delivery_notes)


# ---------- Tracking (customer) ----------

@router.get("/orders/{order_id}/tracking", response_model=TrackingOut)
def track_order(order_id: int, customer: CurrentUser, conn: DB):
    customer_id = None if customer["is_admin"] else customer["customer_id"]
    return delivery_service.track_order(conn, order_id, customer_id)
