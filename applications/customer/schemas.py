from tortoise.contrib.pydantic import pydantic_model_creator
from pydantic import BaseModel, Field, EmailStr, validator, condecimal
from typing import List, Optional
from datetime import datetime
from applications.customer.models import *
from applications.items.models import *
from applications.user.models import *


# Cart Schemas
Cart_Pydantic = pydantic_model_creator(Cart, name="Cart")
CartItem_Pydantic = pydantic_model_creator(CartItem, name="CartItem")

# Order Schemas
Order_Pydantic = pydantic_model_creator(Order, name="Order")
OrderItem_Pydantic = pydantic_model_creator(OrderItem, name="OrderItem")

# DeliveryType Schemas
DeliveryType_Pydantic = pydantic_model_creator(
    DeliveryType, 
    name="DeliveryType"
)

DeliveryTypeIn_Pydantic = pydantic_model_creator(
    DeliveryType, 
    name="DeliveryTypeIn",
    exclude_readonly=True,
    exclude=("id",)
)

# PaymentMethod Schemas
PaymentMethodType_Pydantic = pydantic_model_creator(
    PaymentMethodType, 
    name="PaymentMethodType"
)

PaymentMethodIn_Pydantic = pydantic_model_creator(
    PaymentMethodType, 
    name="PaymentMethodIn",
    exclude_readonly=True,
    exclude=("id",)
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
    id: str
    item_id: str
    quantity: int
    added_at: datetime

    class Config:
        from_attributes = True


class CartResponseSchema(BaseModel):
    """Cart Response with Items"""
    id: str
    user_id: str
    items: List[CartItemResponseSchema]
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Order Schemas ====================

class OrderItemCreateSchema(BaseModel):
    """Order Item Schema"""
    item_id: str
    title: str
    price: condecimal(max_digits=10, decimal_places=2) 
    quantity: int = Field(..., gt=0)
    image_path: str


class ShippingAddressSchema(BaseModel):
    """Shipping Address Schema"""
    id: str
    full_name: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str
    phone_number: str
    is_default: bool = False



class OrderCreateSchema(BaseModel):
    """Order Creation Schema"""
    user_id: str
    items: List[OrderItemCreateSchema]
    shipping_address: ShippingAddressSchema
    # DeliveryType_Pydantic: Optional[str] = DeliveryType.STANDARD.value
    # payment_method: Optional[str] = PaymentMethodType.RAZORPAY.value
    subtotal: condecimal(max_digits=10, decimal_places=2)
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
    items: List[OrderItemCreateSchema]
    shipping_address: ShippingAddressSchema
    # delivery_option: str
    # payment_method: str
    subtotal: float
    delivery_fee: float
    total: float
    coupon_code: Optional[str]
    discount: float
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
#     total_revenue: float = 0.0


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






