"""
addresses.py (router) - the logged-in customer's delivery addresses.
"""
from fastapi import APIRouter, status

from app.database import DB
from app.dependencies import CurrentUser
from app.schemas.address import AddressCreate, AddressOut, AddressUpdate
from app.services import address_service

router = APIRouter(prefix="/addresses", tags=["Addresses"])


@router.get("", response_model=list[AddressOut])
def list_my_addresses(customer: CurrentUser, conn: DB):
    return address_service.list_addresses(conn, customer["customer_id"])


@router.post("", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def add_address(data: AddressCreate, customer: CurrentUser, conn: DB):
    return address_service.add_address(conn, customer["customer_id"], data)


@router.get("/{address_id}", response_model=AddressOut)
def get_address(address_id: int, customer: CurrentUser, conn: DB):
    return address_service.get_address(conn, customer["customer_id"], address_id)


@router.patch("/{address_id}", response_model=AddressOut)
def update_address(address_id: int, data: AddressUpdate, customer: CurrentUser, conn: DB):
    return address_service.update_address(conn, customer["customer_id"], address_id, data)


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(address_id: int, customer: CurrentUser, conn: DB):
    address_service.delete_address(conn, customer["customer_id"], address_id)
