from tortoise.contrib.pydantic import pydantic_model_creator
from pydantic import BaseModel, Field, EmailStr, validator, condecimal
from typing import List, Optional
from datetime import datetime
from applications.customer.models import *
from applications.items.models import *
from applications.user.models import *
from applications.user.customer import CustomerShippingAddress
from applications.user.schemas import *
from decimal import Decimal
import re


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

# ==================== Cart Schemas ====================

class CartCreateSchema(BaseModel):
    """Cart Creation Schema"""
    user_id: str


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

class OrderItemCreateSchema(BaseModel):
    """Order Item Schema"""
    cart_id: str

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
class ShippingAddressResponseSchema(BaseModel):
    """Shipping Address Response Schema"""
    id: str
    full_name: str = Field(..., alias="fullName")
    address_line1: str = Field(..., alias="addressLine1")
    address_line2: str = Field(..., alias="addressLine2")
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = Field(None, alias="postalCode")
    country: Optional[str] = None
    phone_number: str = Field(..., alias="phoneNumber")
    is_default: bool = Field(..., alias="isDefault")
    
    class Config:
        populate_by_name = True
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "addr_1234567890",
                "fullName": "John Doe",
                "addressLine1": "123 Main Street",
                "addressLine2": "Apt 4B",
                "city": "New York",
                "state": "NY",
                "postalCode": "10001",
                "country": "USA",
                "phoneNumber": "+1234567890",
                "isDefault": True
            }
        }


class OrderCreateSchema(BaseModel):
    """Order Creation Schema"""
    # user_id: Optional[int] = None
    carts: List[OrderItemCreateSchema]
    # items: List[OrderItemCreateSchema]
    shipping_address: ShippingAddressSchema
    delivery_option: DeliveryOption_Pydantic_In
    payment_method: PaymentMethod_Pydantic_In
    # subtotal: condecimal(max_digits=10, decimal_places=2)
    coupon_code: Optional[str] = None


class OrderUpdateSchema(BaseModel):
    """Order Update Schema"""
    status: Optional[str] = None
    tracking_number: Optional[str] = None
    transaction_id: Optional[str] = None
    estimated_delivery: Optional[datetime] = None


class OrderResponseSchema(BaseModel):
    """Order Response Schema"""
    order_id: str 
    user_id: str
    items: List[CartResponseSchema]
    shipping_address: ShippingAddressResponseSchema
    delivery_option: str
    payment_method: str
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    coupon_code: Optional[str]
    discount: Decimal
    order_date: datetime
    status: str
    transaction_id: Optional[str]
    tracking_number: Optional[str]
    estimated_delivery: Optional[datetime]
    metadata: Optional[dict]

    class Config:
        from_attributes = True




# User Profile Update Schema
class UserProfileUpdateSchema(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    address_1: Optional[str] = None
    address_2: Optional[str] = None
    postal_code: Optional[str] = None



"""
# # ==================== Dashboard Schemas ====================

# class DashboardStatsSchema(BaseModel):
#     Dashboard Statistics Schema
#     total_users: int
#     total_orders: int
#     total_products: int
#     total_revenue: Decimal = 0.0


# # ==================== API Response Schemas ====================

# class ApiResponseSchema(BaseModel):
#     Standard API Response
#     success: bool
#     message: str
#     data: Optional[dict] = None


# class PaginatedResponseSchema(BaseModel):
#     Paginated Response
#     success: bool
#     message: str
#     data: List[dict]
#     total: int
#     page: int
#     page_size: int



"""






