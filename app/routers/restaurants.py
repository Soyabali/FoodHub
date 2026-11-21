"""
restaurants.py (router)
  Public (no login):  list, details, menu
  Admin only:         create, update, deactivate
"""
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.database import DB
from app.dependencies import AdminUser, OptionalUser, is_admin
from app.schemas.auth import MessageResponse
from app.schemas.food import FoodOut
from app.schemas.restaurant import RestaurantCreate, RestaurantDetail, RestaurantOut, RestaurantUpdate
from app.services import food_service, restaurant_service

router = APIRouter(prefix="/restaurants", tags=["Restaurants"])


@router.get("", response_model=list[RestaurantOut])
def list_restaurants(
    conn: DB,
    user: OptionalUser,
    city: str | None = None,
    search: Annotated[str | None, Query(description="Part of the restaurant name")] = None,
    include_inactive: Annotated[bool, Query(description="Admins only")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return restaurant_service.list_restaurants(
        conn, city, search, include_inactive and is_admin(user), limit, offset
    )


@router.get("/{restaurant_id}", response_model=RestaurantDetail)
def get_restaurant(restaurant_id: int, conn: DB, user: OptionalUser):
    return restaurant_service.get_restaurant(conn, restaurant_id, include_inactive=is_admin(user))


@router.get("/{restaurant_id}/menu", response_model=list[FoodOut])
def get_menu(
    restaurant_id: int,
    conn: DB,
    user: OptionalUser,
    is_veg: bool | None = None,
    category_id: int | None = None,
):
    restaurant_service.get_restaurant(conn, restaurant_id, include_inactive=is_admin(user))  # 404 check
    return food_service.list_foods(
        conn, restaurant_id=restaurant_id, is_veg=is_veg, category_id=category_id,
        include_unavailable=is_admin(user), limit=100,
    )


@router.post("", response_model=RestaurantOut, status_code=status.HTTP_201_CREATED)
def create_restaurant(data: RestaurantCreate, admin: AdminUser, conn: DB):
    return restaurant_service.create_restaurant(conn, data)


@router.patch("/{restaurant_id}", response_model=RestaurantOut)
def update_restaurant(restaurant_id: int, data: RestaurantUpdate, admin: AdminUser, conn: DB):
    return restaurant_service.update_restaurant(conn, restaurant_id, data)


@router.delete("/{restaurant_id}", response_model=MessageResponse)
def deactivate_restaurant(restaurant_id: int, admin: AdminUser, conn: DB):
    restaurant_service.deactivate_restaurant(conn, restaurant_id)
    return {"message": "Restaurant deactivated. Re-open it with PATCH {\"is_active\": true}."}
