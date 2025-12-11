from __future__ import annotations

from tortoise.contrib.pydantic import pydantic_model_creator
from pydantic import BaseModel, Field, EmailStr, validator, condecimal
from typing import List, Optional
from datetime import datetime
from applications.customer.models import Cart, CartItem, Order, OrderItem, DeliveryOption, PaymentMethod
from decimal import Decimal
import re
from enum import Enum
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel
from typing import Optional



class PaymentInitiateSchema(BaseModel):
    order_id: str
class PaymentLinkResponse(BaseModel):
    success: bool
    order_id: str
    cf_order_id: str
    payment_link: str
    message: str



# ============================================================
# Delivery Option Schema
# ============================================================

class DeliveryOptionResponseSchema(BaseModel):
    type: str
    title: Optional[str] = None
    description: Optional[str] = None
    price: float
    
    class Config:
        from_attributes = True


class PaymentCallbackSchema(BaseModel):
    order_id: str
    cf_order_id: str
    payment_status: str
    transaction_id: Optional[str] = None
class PaymentResponseSchema(BaseModel):
    success: bool
    payment_session_id: str
    cf_order_id: str
    payment_url: str
    order_id: str

# Cart Schemas
Cart_Pydantic = pydantic_model_creator(Cart, name="Cart")
CartItem_Pydantic = pydantic_model_creator(CartItem, name="CartItem")

# Order Schemas
Order_Pydantic = pydantic_model_creator(Order, name="Order")
OrderItem_Pydantic = pydantic_model_creator(OrderItem, name="OrderItem")

# Create Pydantic models from Tortoise model
DeliveryOption_Pydantic = pydantic_model_creator(
    DeliveryOption, 
    name="DeliveryOption"
)

DeliveryOption_Pydantic_In = pydantic_model_creator(
    DeliveryOption, 
    name="DeliveryOptionIn",
    exclude_readonly=True  # Excludes id, created_at, updated_at
)

PaymentMethod_Pydantic = pydantic_model_creator(
    PaymentMethod, 
    name="PaymentMethod"
)

PaymentMethod_Pydantic_In = pydantic_model_creator(
    PaymentMethod, 
    name="PaymentMethodIn",
    exclude_readonly=True
)

class OrderSummary(BaseModel):
    """Summary of a single order in a combined payment"""
    order_id: str
    vendor_id: int
    vendor_name: str
    total: float
    items_count: int

class CombinedPaymentLinkResponse(BaseModel):
    """Response for combined payment link across multiple orders"""
    success: bool
    orders: List[OrderSummary]
    cf_payment_id: str
    payment_link: str
    message: str
    total_amount: float
    orders_count: int

class MultiOrderResponseSchema(BaseModel):
    """Response when creating multiple orders in one request"""
    success: bool
    message: str
    data: dict  # Contains: orders, total_amount, payment_status, payment_link, etc.
    
    class Config:
        from_attributes = True

# ==================== Cart Schemas ====================

class CartCreateSchema(BaseModel):
    """Cart Creation Schema"""
    # user_id: str
    pass


class CartItemCreateSchema(BaseModel):
    """Add Item to Cart Schema"""
    item_id: str
    quantity: int = Field(..., gt=0)


class CartItemUpdateSchema(BaseModel):
    """Update Cart Item Schema"""
    quantity: int = Field(..., gt=0)


class CartItemResponseSchema(BaseModel):
    """Cart Item Response"""
    item_id: str
    title: str
    price: Decimal
    quantity: int
    image_path: Optional[str] = None

    class Config:
        from_attributes = True


class CartResponseSchema(BaseModel):
    """Cart Response with Items"""
    items: List[CartItemResponseSchema]

    class Config:
        from_attributes = True


# ==================== Order Schemas ====================

class CartItemsCreateSchema(BaseModel):
    """Order Item Schema"""
    cart_id: str

class AddressTypeEnum(str, Enum):
    HOME = "HOME"
    OFFICE = "Office"
    OTHERS = "OTHERS"


# Enums for address types
AddressType = Literal["HOME", "OFFICE", "OTHERS"]

class ShippingAddressBase(BaseModel):
    full_name: str = Field(..., max_length=255, description="Full name of the recipient")
    address_line1: str = Field(..., max_length=500, description="Primary address line")
    address_line2: Optional[str] = Field(None, max_length=500, description="Secondary address line")
    city: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=255)
    postal_code: Optional[str] = Field(None, max_length=20)
    phone_number: str = Field(..., max_length=50)
    email: str = Field(..., max_length=100)
    addressType: AddressType = Field(default="HOME")

    @validator('addressType')
    def validate_address_type(cls, v):
        if v not in ["HOME", "OFFICE", "OTHERS"]:
            raise ValueError('addressType must be one of HOME, OFFICE, or OTHERS')
        return v

class ShippingAddressCreate(ShippingAddressBase):
    """Schema for creating a new shipping address"""
    make_default: Optional[bool] = Field(default=False, description="Set as default for this address type")

class ShippingAddressUpdate(BaseModel):
    """Schema for updating an existing shipping address"""
    full_name: Optional[str] = Field(None, max_length=255)
    address_line1: Optional[str] = Field(None, max_length=500)
    address_line2: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=255)
    postal_code: Optional[str] = Field(None, max_length=20)
    phone_number: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=100)
    is_default: Optional[bool] = None

class ShippingAddressResponse(BaseModel):
    """Schema for shipping address response"""
    id: str
    user_id: int
    full_name: str
    address_line1: str
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    phone_number: str
    email: str
    addressType: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ShippingAddressListResponse(BaseModel):
    """Schema for list of shipping addresses"""
    addresses: list[ShippingAddressResponse]
    total: int

class SetDefaultRequest(BaseModel):
    """Schema for setting an address as default"""
    address_id: str

class ErrorResponse(BaseModel):
    """Schema for error responses"""
    detail: str
    error_code: Optional[str] = None

class ShippingAddressSchema(BaseModel):
    """Shipping Address Input Schema (ID will be auto-generated)"""
    full_name: str = Field(..., alias="fullName", min_length=1, max_length=255)
    address_line1: str = Field(..., alias="addressLine1", min_length=1, max_length=500)
    address_line2: Optional[str] = Field(None, alias="addressLine2", max_length=500)
    city: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, max_length=255)
    postal_code: Optional[str] = Field(None, alias="postalCode", max_length=20)
    country: Optional[str] = Field(None, max_length=255)
    phone_number: str = Field(..., alias="phoneNumber", max_length=50)
    is_default: bool = Field(False, alias="isDefault")
    
    @validator('phone_number')
    def validate_phone(cls, v):
        if not v or len(v.strip()) < 10:
            raise ValueError('Phone number must be at least 10 characters')
        return v
    
    class Config:
        populate_by_name = True
        from_attributes = True
# ============================================================
# Shipping Address Schema
# ============================================================

class ShippingAddressResponseSchema(BaseModel):
    id: Optional[str] = None  # FIXED: Made optional
    full_name: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str
    phone_number: str
    isDefault: Optional[bool] = Field(default=False, alias="is_default")  # FIXED: Made optional with alias
    
    class Config:
        from_attributes = True
        populate_by_name = True


class OrderItemInputSchema(BaseModel):
    item_id: int
    quantity: int

class OrderCreateSchema(BaseModel):
    items: List[OrderItemInputSchema]
    shipping_address: ShippingAddressSchema
    delivery_option: DeliveryOption_Pydantic_In
    payment_method: PaymentMethod_Pydantic_In
    coupon_code: Optional[str] = None

class OrderUpdateSchema(BaseModel):
    status: Optional[str] = None
    # tracking_number: Optional[str] = None
    # transaction_id: Optional[str] = None
    # estimated_delivery: Optional[datetime] = None
    


# ============================================================
# Order Item Schema
# ============================================================

class OrderItemResponseSchema(BaseModel):
    id: Optional[int] = None  # FIXED: Made optional
    item_id: int
    title: str
    price: str
    quantity: int
    image_path: str
    
    class Config:
        from_attributes = True

# ============================================================
# Vendor Location Schema
# ============================================================

class VendorLocationSchema(BaseModel):
    vendor_id: int
    vendor_name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: bool
    
    class Config:
        from_attributes = True


# ============================================================
# Payment Method Schema
# ============================================================

class PaymentMethodResponseSchema(BaseModel):
    type: str
    name: Optional[str] = None
    
    class Config:
        from_attributes = True

# ============================================================
# SCHEMAS - applications.customer.schemas.py
# ============================================================

class RiderInfoSchema(BaseModel):
    rider_id: Optional[int] = None
    rider_name: Optional[str] = None
    rider_phone: Optional[str] = None
    rider_image: Optional[str] = None
    
    class Config:
        from_attributes = True

# ============================================================
# Order Response Schema
# ============================================================

class OrderResponseSchema(BaseModel):
    order_id: str = Field(..., alias="id")
    user_id: str
    items: List[OrderItemResponseSchema] = []
    shipping_address: Optional[ShippingAddressResponseSchema] = None
    delivery_option: DeliveryOptionResponseSchema
    payment_method: PaymentMethodResponseSchema
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    coupon_code: Optional[str] = None
    discount: Decimal
    order_date: datetime
    status: str
    transaction_id: Optional[str] = None
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    metadata: Optional[dict] = None
    rider_info: Optional[RiderInfoSchema] = None
    payment_link: Optional[str] = None
    payment_status: str = "unpaid"
    vendor_id: Optional[str] = None
     
    @validator('user_id', pre=True)
    def convert_user_id(cls, v):
        if hasattr(v, 'id'):
            return str(v.id)
        return str(v)
    
    @validator('status', pre=True)
    def convert_status_enum(cls, v):
        return v.value if hasattr(v, 'value') else v
    
    class Config:
        from_attributes = True
        populate_by_name = True       
# User Profile Update Schema
class UserProfileUpdateSchema(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    address_1: Optional[str] = None
    address_2: Optional[str] = None
    postal_code: Optional[str] = None

class CustomerProfileSchema(BaseModel):
    """Customer Profile Input Schema"""
    name: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None
    # photo: Optional[str] = Field(None, max_length=255)
    address_1: Optional[str] = Field(None, max_length=100, alias="address1")
    address_2: Optional[str] = Field(None, max_length=100, alias="address2")
    postal_code: Optional[str] = Field(None, max_length=20, alias="postalCode")
    
    class Config:
        populate_by_name = True  # Allow both camelCase and snake_case


class CustomerProfileResponseSchema(BaseModel):
    """Customer Profile Response Schema"""
    success: bool = True
    message: str
    data: dict
    
    class Config:
        from_attributes = True







