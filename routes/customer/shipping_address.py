from fastapi import APIRouter, Depends, status, HTTPException
from typing import Optional
from applications.customer.schemas import (
    ShippingAddressCreate,
    ShippingAddressUpdate,
    ShippingAddressResponse,
    ShippingAddressListResponse,
    SetDefaultRequest,
    ErrorResponse
)
from applications.user.models import User
from applications.customer.services import ShippingAddressService
from app.token import get_current_user


router = APIRouter(
    prefix="/shipping-addresses",
    tags=["Shipping Addresses"]
)

@router.post(
    "/",
    response_model=ShippingAddressResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Address limit exceeded"},
        401: {"description": "Unauthorized"}
    }
)
async def create_shipping_address(
    address_data: ShippingAddressCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new shipping address for the authenticated user.
    
    - Maximum 3 addresses total
    - Each address type (HOME, OFFICE, OTHERS) can only be added once
    - If make_default is True, it becomes the default for its type
    """
    # Convert to dict and exclude unset values
    data_dict = address_data.dict(exclude_unset=True)
    
    address = await ShippingAddressService.create_address(
        current_user=current_user,
        address_data=data_dict
    )
    return address

@router.get(
    "/",
    response_model=ShippingAddressListResponse,
    responses={401: {"description": "Unauthorized"}}
)
async def get_shipping_addresses(
    address_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get all shipping addresses for the authenticated user.
    
    - Optional filter by address_type (HOME, OFFICE, OTHERS)
    """
    addresses = await ShippingAddressService.get_user_addresses(
        current_user=current_user,
        address_type=address_type
    )
    
    return ShippingAddressListResponse(
        addresses=addresses,
        total=len(addresses)
    )

@router.get(
    "/{address_id}",
    response_model=ShippingAddressResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Address not found"},
        401: {"description": "Unauthorized"}
    }
)
async def get_shipping_address(
    address_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific shipping address by ID.
    """
    address = await ShippingAddressService.get_address_by_id(
        address_id=address_id,
        current_user=current_user
    )
    return address

@router.get(
    "/{address_type}",
    response_model=ShippingAddressResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Address not found"},
        401: {"description": "Unauthorized"}
    }
)

@router.put(
    "/{address_id}",
    response_model=ShippingAddressResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Address not found"},
        401: {"description": "Unauthorized"}
    }
)
async def update_shipping_address(
    address_id: str,
    address_data: ShippingAddressUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing shipping address.
    
    - Cannot change addressType (delete and create new instead)
    - Setting is_default=True will unset other defaults for that type
    """
    address = await ShippingAddressService.update_address(
        address_id=address_id,
        current_user=current_user,
        update_data=address_data.dict(exclude_unset=True)
    )
    return address

@router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"model": ErrorResponse, "description": "Address not found"},
        401: {"description": "Unauthorized"}
    }
)
async def delete_shipping_address(
    address_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a shipping address.
    
    - If the deleted address was default, another address of the same type (if any) becomes default
    """
    await ShippingAddressService.delete_address(
        address_id=address_id,
        current_user=current_user
    )
    return None

@router.post(
    "/{address_id}/set-default",
    response_model=ShippingAddressResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Address not found"},
        401: {"description": "Unauthorized"}
    }
)
async def set_default_address(
    address_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Set a shipping address as the default for its address type.
    
    - Only one address per type can be default
    - Other addresses of the same type will have is_default set to False
    """
    address = await ShippingAddressService.set_default_address(
        address_id=address_id,
        current_user=current_user
    )
    return address

@router.get(
    "/default/{address_type}",
    response_model=ShippingAddressResponse,
    responses={
        404: {"model": ErrorResponse, "description": "No default address found"},
        401: {"description": "Unauthorized"}
    }
)
async def get_default_address(
    address_type: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get the default shipping address for a specific type.
    
    - address_type must be one of: HOME, OFFICE, OTHERS
    """
    if address_type not in ["HOME", "OFFICE", "OTHERS"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid address type. Must be HOME, OFFICE, or OTHERS"
        )
    
    address = await ShippingAddressService.get_default_address(
        current_user=current_user,
        address_type=address_type
    )
    return address

