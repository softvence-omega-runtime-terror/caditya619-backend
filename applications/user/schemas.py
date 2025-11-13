# # applications/user/schemas.py

# from pydantic import BaseModel, Field
# from typing import Optional

# class ShippingAddressBase(BaseModel):
#     full_name: str = ""
#     address_line1: str = ""
#     city: Optional[str] = None
#     state: Optional[str] = None
#     country: Optional[str] = None
#     phone_number: str = ""
#     is_default: bool = False


# class ShippingAddressCreate(ShippingAddressBase):
#     """Schema for creating shipping address"""
#     pass


# class ShippingAddressResponse(ShippingAddressBase):
#     """Schema for response with defaults"""
#     id: str
#     user_id: int
    
#     # Default values from User/CustomerProfile
#     default_full_name: Optional[str] = None
#     default_phone_number: Optional[str] = None
#     default_address_line1: Optional[str] = None

#     class Config:
#         from_attributes = True


# class ShippingAddressUpdate(BaseModel):
#     """Schema for updating - all fields optional"""
#     full_name: Optional[str] = None
#     address_line1: Optional[str] = None
#     city: Optional[str] = None
#     state: Optional[str] = None
#     country: Optional[str] = None
#     phone_number: Optional[str] = None
#     is_default: Optional[bool] = None