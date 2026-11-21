"""
categories.py (router)
  Public:      list, details
  Admin only:  create, update, deactivate
"""
from fastapi import APIRouter, status

from app.database import DB
from app.dependencies import AdminUser, OptionalUser, is_admin
from app.schemas.auth import MessageResponse
from app.schemas.food import CategoryCreate, CategoryOut, CategoryUpdate
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["Food"])


@router.get("", response_model=list[CategoryOut])
def list_categories(conn: DB, user: OptionalUser, include_inactive: bool = False):
    return category_service.list_categories(conn, include_inactive and is_admin(user))


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(category_id: int, conn: DB, user: OptionalUser):
    return category_service.get_category(conn, category_id, include_inactive=is_admin(user))


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, admin: AdminUser, conn: DB):
    return category_service.create_category(conn, data)


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, data: CategoryUpdate, admin: AdminUser, conn: DB):
    return category_service.update_category(conn, category_id, data)


@router.delete("/{category_id}", response_model=MessageResponse)
def deactivate_category(category_id: int, admin: AdminUser, conn: DB):
    category_service.deactivate_category(conn, category_id)
    return {"message": "Category deactivated."}
