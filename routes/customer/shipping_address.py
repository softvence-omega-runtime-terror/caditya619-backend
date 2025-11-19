from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from applications.customer import services
from applications.customer.schemas import (
    CustomerShippingAddressCreate,
    CustomerShippingAddressUpdate,
    CustomerShippingAddressOut,
    AddressTypeEnum
)
from app.token import get_current_user
current_user = Depends(get_current_user)

router = APIRouter(prefix="/shipping-address", tags=["Shipping Address"])


@router.post("/", response_model=CustomerShippingAddressOut, status_code=status.HTTP_201_CREATED)
async def create_address(
    payload: CustomerShippingAddressCreate,
    current_user = Depends(get_current_user)
):
    """
    Create a new shipping address for the current user.
    """
    try:
        address = await services.create_shipping_address(
            current_user.id,
            payload.dict(exclude_none=True)
        )
        return address
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create address: {str(e)}"
        )


@router.put("/{address_id}", response_model=CustomerShippingAddressOut)
async def update_address(
    address_id: str,
    payload: CustomerShippingAddressUpdate,
    current_user = Depends(get_current_user)
):
    """
    Update an existing shipping address.
    """
    try:
        address = await services.update_shipping_address(
            address_id,
            current_user.id,
            payload.dict(exclude_none=True)
        )
        return address
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Address not found or update failed: {str(e)}"
        )


@router.get("/", response_model=List[CustomerShippingAddressOut])
async def list_all_addresses(current_user = Depends(get_current_user)):
    """
    Get all shipping addresses for the current user.
    """
    addresses = await services.get_shipping_addresses(current_user.id)
    return addresses


@router.get("/type/{address_type}", response_model=List[CustomerShippingAddressOut])
async def list_addresses_by_type(
    address_type: AddressTypeEnum,
    current_user = Depends(get_current_user)
):
    """
    Get all shipping addresses of a specific type (HOME, Office, OTHERS).
    """
    addresses = await services.get_shipping_addresses_by_type(
        current_user.id,
        address_type.value
    )
    return addresses


@router.get("/default", response_model=CustomerShippingAddressOut)
async def get_default_address(current_user = Depends(get_current_user)):
    """
    Get the first default address found for the current user.
    """
    address = await services.get_default_shipping_address(current_user.id)
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default address found"
        )
    return address


@router.get("/default/{address_type}", response_model=CustomerShippingAddressOut)
async def get_default_address_by_type(
    address_type: AddressTypeEnum,
    current_user = Depends(get_current_user)
):
    """
    Get the default address for a specific type (HOME, Office, OTHERS).
    """
    address = await services.get_default_shipping_address(
        current_user.id,
        address_type.value
    )
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No default {address_type.value} address found"
        )
    return address


@router.patch("/{address_id}/set-default", response_model=CustomerShippingAddressOut)
async def set_address_as_default(
    address_id: str,
    current_user = Depends(get_current_user)
):
    """
    Set a specific address as the default for its type.
    """
    try:
        address = await services.set_default_address(address_id, current_user.id)
        return address
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Address not found: {str(e)}"
        )


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: str,
    current_user = Depends(get_current_user)
):
    """
    Delete a shipping address.
    """
    deleted = await services.delete_shipping_address(address_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    return None