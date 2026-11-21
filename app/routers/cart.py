"""
cart.py (router) - the logged-in customer's cart. Every response returns
the full, recalculated cart, so the app can simply redraw it.
"""
from fastapi import APIRouter, status

from app.database import DB
from app.dependencies import CurrentUser
from app.schemas.cart import CartItemAdd, CartItemUpdate, CartOut
from app.services import cart_service

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get("", response_model=CartOut)
def view_cart(customer: CurrentUser, conn: DB):
    return cart_service.get_cart(conn, customer["customer_id"])


@router.post("/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def add_to_cart(data: CartItemAdd, customer: CurrentUser, conn: DB):
    return cart_service.add_item(conn, customer["customer_id"], data)


@router.patch("/items/{cart_item_id}", response_model=CartOut)
def update_cart_item(cart_item_id: int, data: CartItemUpdate, customer: CurrentUser, conn: DB):
    return cart_service.update_quantity(conn, customer["customer_id"], cart_item_id, data.quantity)


@router.delete("/items/{cart_item_id}", response_model=CartOut)
def remove_cart_item(cart_item_id: int, customer: CurrentUser, conn: DB):
    return cart_service.remove_item(conn, customer["customer_id"], cart_item_id)


@router.delete("", response_model=CartOut)
def clear_cart(customer: CurrentUser, conn: DB):
    return cart_service.clear_cart(conn, customer["customer_id"])
