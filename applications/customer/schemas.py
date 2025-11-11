from tortoise.contrib.pydantic import pydantic_model_creator
from pydantic import BaseModel, Field, EmailStr, validator
from typing import List, Optional
from datetime import datetime
from applications.customer.models import *
from applications.items.models import *
from applications.user.models import *

"""
# ==================== Auto-Generated Pydantic Models ====================

# # User Schemas
# User_Pydantic = pydantic_model_creator(User, name="User", exclude=("password",))
# UserIn_Pydantic = pydantic_model_creator(User, name="UserIn", exclude_readonly=True)

# # Category Schemas
# Category_Pydantic = pydantic_model_creator(Category, name="Category")
# CategoryIn_Pydantic = pydantic_model_creator(Category, name="CategoryIn", exclude_readonly=True)

# # Subcategory Schemas
# Subcategory_Pydantic = pydantic_model_creator(Subcategory, name="Subcategory")
# SubcategoryIn_Pydantic = pydantic_model_creator(Subcategory, name="SubcategoryIn", exclude_readonly=True)

# # Shop Schemas
# Shop_Pydantic = pydantic_model_creator(Shop, name="Shop")
# ShopIn_Pydantic = pydantic_model_creator(Shop, name="ShopIn", exclude_readonly=True)

# # Product Schemas
# Product_Pydantic = pydantic_model_creator(Product, name="Product")
# ProductIn_Pydantic = pydantic_model_creator(Product, name="ProductIn", exclude_readonly=True)

"""

# Cart Schemas
Cart_Pydantic = pydantic_model_creator(Cart, name="Cart")
CartItem_Pydantic = pydantic_model_creator(CartItem, name="CartItem")

# Order Schemas
Order_Pydantic = pydantic_model_creator(Order, name="Order")
OrderItem_Pydantic = pydantic_model_creator(OrderItem, name="OrderItem")



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
    price: str
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
    # delivery_option: DeliveryOptionSchema
    # payment_method: PaymentMethodSchema
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
    # delivery_option: DeliveryOptionSchema
    # payment_method: PaymentMethodSchema
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
# # ==================== Prescription Schemas ====================

# # class MedicineSchema(BaseModel):
# #     Medicine Schema
# #     id: str
# #     name: str
# #     brand: str
# #     dosage: str
# #     quantity: int
# #     price: float
# #     notes: Optional[str] = None
# #     is_available: bool = True
# #     image_path: Optional[str] = None
# #     vendor_id: str


# # class VendorResponseSchema(BaseModel):
# #     Vendor Response Schema
# #     id: str
# #     prescription_id: str
# #     vendor_id: str
# #     vendor_name: str
# #     medicines: List[MedicineSchema]
# #     total_amount: float
# #     status: str
# #     responded_at: datetime
# #     notes: Optional[str] = None

# #     class Config:
# #         from_attributes = True


# # class PrescriptionUploadSchema(BaseModel):
# #     Prescription Upload Schema
# #     user_id: str
# #     image_path: str
# #     file_name: str


# # class PrescriptionResponseSchema(BaseModel):
# #     Prescription Response Schema
# #     id: str
# #     user_id: str
# #     image_path: str
# #     file_name: str
# #     uploaded_at: datetime
# #     status: str
# #     notes: Optional[str]
# #     vendor_responses: List[VendorResponseSchema] = []

# #     class Config:
# #         from_attributes = True


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

"""
# # Prescription Schemas
# Prescription_Pydantic = pydantic_model_creator(Prescription, name="Prescription")
# VendorResponse_Pydantic = pydantic_model_creator(VendorResponse, name="VendorResponse")
# Medicine_Pydantic = pydantic_model_creator(Medicine, name="Medicine")


# ==================== Authentication Schemas ====================

# class UserRegisterSchema(BaseModel):
#     User Registration Schema
#     first_name: str = Field(..., min_length=1, max_length=255)
#     last_name: str = Field(..., min_length=1, max_length=255)
#     email: EmailStr
#     password: str = Field(..., min_length=6)
#     phone_number: Optional[str] = None
#     address_1: Optional[str] = None
#     address_2: Optional[str] = None
#     postal_code: Optional[str] = None


# class UserLoginSchema(BaseModel):
#     User Login Schema
#     email: EmailStr
#     password: str


# class TokenSchema(BaseModel):
#     JWT Token Response
#     access_token: str
#     token_type: str = "bearer"
#     user: dict





# ==================== Category Schemas ====================

# class CategoryCreateSchema(BaseModel):
#     Category Creation Schema
#     id: str
#     name: str = Field(..., min_length=1, max_length=255)
#     description: Optional[str] = None
#     image: Optional[str] = None


# class SubcategoryCreateSchema(BaseModel):
#     Subcategory Creation Schema
#     id: str
#     name: str = Field(..., min_length=1, max_length=255)
#     description: Optional[str] = None
#     category_id: str


# ==================== Shop Schemas ====================

# class SignatureDishSchema(BaseModel):
#     Signature Dish Schema
#     id: str
#     name: str
#     image: Optional[str]
#     description: Optional[str]
#     price: str
#     is_popular: bool = False

#     class Config:
#         from_attributes = True


# class RestaurantCreateSchema(BaseModel):
#     Restaurant Creation Schema
#     id: str
#     name: str
#     image: Optional[str] = None
#     delivery_time: Optional[str] = "30-40 min"
#     rating: float = 4.5
#     address: str
#     is_open: bool = True
#     cuisines: List[str] = []
#     specialties: List[str] = []
#     review_count: int = 0
#     popularity: float = 0.0
#     is_top_rated: bool = False
#     signature_dishes: List[SignatureDishSchema] = []


# class ShopCreateSchema(BaseModel):
#     General Shop Creation Schema
#     id: str
#     name: str
#     image: Optional[str] = None
#     delivery_time: Optional[str] = "30-45 min"
#     rating: float = 4.7
#     address: str
#     is_open: bool = True


# class ShopResponseSchema(BaseModel):
#     Shop Response Schema
#     id: str
#     name: str
#     image: Optional[str]
#     delivery_time: Optional[str]
#     rating: float
#     address: str
#     is_open: bool
#     review_count: int = 0
#     popularity: float = 0.0
#     is_top_rated: bool = False

#     class Config:
#         from_attributes = True


# class RestaurantResponseSchema(ShopResponseSchema):
#     Restaurant Response with Cuisines and Signature Dishes
#     cuisines: List[str] = []
#     specialties: List[str] = []
#     signature_dishes: List[SignatureDishSchema] = []

#     class Config:
#         from_attributes = True


# ==================== Product Schemas ====================

# class ProductCreateSchema(BaseModel):
#     Product Creation Schema
#     id: str
#     title: str = Field(..., min_length=1, max_length=500)
#     description: Optional[str] = None
#     price: str = Field(..., description="Price as string, e.g., '$18'")
#     image_path: str
#     category_id: str
#     subcategory_id: Optional[str] = None
#     shop_id: str
#     rating: float = 0.0
#     weight: Optional[str] = None
#     product_type: Optional[str] = None
#     stock: int = 0
#     is_otc: bool = False

#     @validator('price')
#     def validate_price(cls, v):
#         if not v:
#             raise ValueError('Price is required')
#         return v


# class ProductResponseSchema(BaseModel):
#     Product Response Schema
#     id: str
#     title: str
#     description: Optional[str]
#     price: str
#     image_path: str
#     category_id: str
#     subcategory_id: Optional[str]
#     shop_id: str
#     rating: float
#     weight: Optional[str]
#     product_type: Optional[str]
#     stock: int
#     is_otc: bool

#     class Config:
#         from_attributes = True


# class ProductSearchSchema(BaseModel):
#     Product Search Parameters
#     search: Optional[str] = None
#     category_id: Optional[str] = None
#     subcategory_id: Optional[str] = None
#     shop_id: Optional[str] = None
#     min_price: Optional[float] = None
#     max_price: Optional[float] = None

"""
