from fastapi import APIRouter, HTTPException, Query, status, Depends
from typing import List
from applications.customer.schemas import (
    CustomerShippingAddressCreate,
    CustomerShippingAddressUpdate,
    CustomerShippingAddressOut,
)
from applications.customer import services
from app.token import get_current_user


router = APIRouter(prefix="/shipping-address", tags=["Shipping Address"])

@router.post("/", response_model=CustomerShippingAddressOut)
async def create_address(
    payload: CustomerShippingAddressCreate,
    current_user = Depends(get_current_user)
):
    address = await services.create_shipping_address(
        current_user.id,                   # <-- first argument
        payload.dict(exclude_none=True)    # <-- second argument
    )
    return address


@router.put("/{address_id}", response_model=CustomerShippingAddressOut)
async def update_address(address_id: str, payload: CustomerShippingAddressUpdate, current_user = Depends(get_current_user)):
    address = await services.update_shipping_address(address_id, payload.dict(exclude_none=True))
    return address

@router.get("/", response_model=List[CustomerShippingAddressOut])
async def list_addresses(current_user = Depends(get_current_user)):
    addresses = await services.get_shipping_addresses(current_user)
    return addresses


@router.get("/{addressType}", response_model=List[CustomerShippingAddressOut])
async def list_addresses(addressType: str, current_user = Depends(get_current_user)):
    addresses = await services.get_shipping_addresses(addressType)
    return addresses

# @router.get("/HOME", response_model=CustomerShippingAddressOut)
# async def get_default_address(HOME: str):
#     address = await services.get_default_shipping_address(HOME)
#     return address
