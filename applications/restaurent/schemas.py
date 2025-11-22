from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


# ============== Vendor (Restaurant) Schemas ==============
class VendorRestaurantBase(BaseModel):
    business_name: Optional[str] = None
    image: Optional[str] = None
    delivery_time: str = "30-40 min"
    address: Optional[str] = None
    is_open: bool = True
    cuisines: List[str] = []
    specialties: List[str] = []


class VendorRestaurantResponse(VendorRestaurantBase):
    id: int
    user_id: int
    type: str
    rating: float
    review_count: int
    popularity: float
    is_top_rated: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VendorRestaurantUpdate(BaseModel):
    business_name: Optional[str] = None
    image: Optional[str] = None
    delivery_time: Optional[str] = None
    address: Optional[str] = None
    is_open: Optional[bool] = None
    cuisines: Optional[List[str]] = None
    specialties: Optional[List[str]] = None


# ============== Signature Dish Schemas ==============
class SignatureDishBase(BaseModel):
    name: str
    image: Optional[str] = None
    description: Optional[str] = None
    specialty_type: str
    is_popular: bool = False
    display_order: int = 0


class SignatureDishCreate(SignatureDishBase):
    vendor_id: int
    item_id: Optional[int] = None


class SignatureDishResponse(SignatureDishBase):
    id: int
    vendor_id: int
    item_id: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VendorRestaurantDetailResponse(VendorRestaurantResponse):
    signature_dishes: List[SignatureDishResponse] = []


# ============== Food Vendor List Query ==============
class FoodVendorListQuery(BaseModel):
    specialty: Optional[str] = None  # e.g., "food_biryani", "food_pizza"
    is_top_rated: Optional[bool] = None
    min_rating: Optional[float] = None
    cuisine: Optional[str] = None
    is_open: Optional[bool] = None
    search: Optional[str] = None
    limit: int = Field(default=25, le=100)
    offset: int = Field(default=0, ge=0)


# ============== Vendor Items (Food Items) Schemas ==============
class VendorItemResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    image: Optional[str]
    price: Decimal
    discount: int
    sell_price: Decimal
    discounted_price: Decimal
    ratings: float
    stock: int
    popular: bool
    free_delivery: bool
    hot_deals: bool
    flash_sale: bool
    is_in_stock: bool
    new_arrival: bool
    today_deals: bool
    category_name: Optional[str] = None
    subcategory_name: Optional[str] = None
    sub_subcategory_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class VendorItemsQuery(BaseModel):
    vendor_id: int
    category: Optional[str] = "All"  # "All", "Appetizers", "Biryani", "Main Course", "Breads"
    specialty: Optional[str] = None  # Additional filter
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    is_popular: Optional[bool] = None
    search: Optional[str] = None
    limit: int = Field(default=20, le=100)
    offset: int = Field(default=0, ge=0)


# ============== Popular Items by Specialty ==============
class PopularItemsBySpecialty(BaseModel):
    specialty_type: str  # "biryani", "pizza", "burger", etc.
    specialty_label: str  # "Biryani", "Pizza", "Burger", etc.
    items: List[VendorItemResponse]


# ============== Vendor Review Schemas ==============
class VendorReviewBase(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


class VendorReviewCreate(VendorReviewBase):
    vendor_id: int


class VendorReviewResponse(VendorReviewBase):
    id: int
    vendor_id: int
    customer_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============== Food Category Page Response ==============
class FoodCategoryPageResponse(BaseModel):
    popular_items: List[PopularItemsBySpecialty]
    top_restaurants: List[VendorRestaurantDetailResponse]
    all_food_items: List[VendorItemResponse]
    total_restaurants: int
    total_items: int