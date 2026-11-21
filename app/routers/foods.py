"""
foods.py (router)
  Public:      food list (with filters), food details
  Admin only:  create, update, remove
"""
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.database import DB
from app.dependencies import AdminUser, OptionalUser, is_admin
from app.schemas.auth import MessageResponse
from app.schemas.food import FoodCreate, FoodOut, FoodUpdate
from app.services import food_service

router = APIRouter(prefix="/foods", tags=["Food"])


@router.get("", response_model=list[FoodOut])
def list_foods(
    conn: DB,
    user: OptionalUser,
    restaurant_id: int | None = None,
    category_id: int | None = None,
    is_veg: Annotated[bool | None, Query(description="true = veg only, false = non-veg only")] = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    search: Annotated[str | None, Query(description="Part of the food name or description")] = None,
    include_unavailable: Annotated[bool, Query(description="Admins only")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return food_service.list_foods(
        conn, restaurant_id=restaurant_id, category_id=category_id, is_veg=is_veg,
        min_price=min_price, max_price=max_price, search=search,
        include_unavailable=include_unavailable and is_admin(user), limit=limit, offset=offset,
    )


@router.get("/{food_id}", response_model=FoodOut)
def get_food(food_id: int, conn: DB, user: OptionalUser):
    return food_service.get_food(conn, food_id, include_unavailable=is_admin(user))


@router.post("", response_model=FoodOut, status_code=status.HTTP_201_CREATED)
def create_food(data: FoodCreate, admin: AdminUser, conn: DB):
    return food_service.create_food(conn, data)


@router.patch("/{food_id}", response_model=FoodOut)
def update_food(food_id: int, data: FoodUpdate, admin: AdminUser, conn: DB):
    return food_service.update_food(conn, food_id, data)


@router.delete("/{food_id}", response_model=MessageResponse)
def remove_food(food_id: int, admin: AdminUser, conn: DB):
    food_service.remove_food(conn, food_id)
    return {"message": "Food item removed from the menu (marked unavailable)."}
