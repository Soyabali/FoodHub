"""
customers.py (router) - the logged-in customer's own profile.

"/customers/me" means "my own account". The customer_id always comes from
the JWT token, never from the URL, so nobody can edit another account.
"""
from fastapi import APIRouter

from app.database import DB
from app.dependencies import CurrentUser
from app.schemas.auth import MessageResponse
from app.schemas.customer import CustomerOut, CustomerProfile, CustomerUpdate
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("/me", response_model=CustomerProfile)
def get_my_profile(customer: CurrentUser, conn: DB):
    return customer_service.get_profile(conn, customer)


@router.patch("/me", response_model=CustomerOut)
def update_my_profile(data: CustomerUpdate, customer: CurrentUser, conn: DB):
    return customer_service.update_profile(conn, customer["customer_id"], data)


@router.delete("/me", response_model=MessageResponse)
def delete_my_account(customer: CurrentUser, conn: DB):
    customer_service.deactivate_account(conn, customer["customer_id"])
    return {"message": "Your account has been deactivated. Your order history has been kept."}
