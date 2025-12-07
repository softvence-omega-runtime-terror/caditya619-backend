from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from decimal import Decimal


class CategoryBasic(BaseModel):
    id: int
    name: str
    type: str
    avatar: Optional[str] = None
    
    class Config:
        from_attributes = True


class SubCategoryBasic(BaseModel):
    id: int
    name: str
    avatar: Optional[str] = None
    
    class Config:
        from_attributes = True


class SubSubCategoryBasic(BaseModel):
    id: int
    name: str
    avatar: Optional[str] = None
    
    class Config:
        from_attributes = True


class ItemDetail(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    image: Optional[str] = None
    price: Decimal
    discount: int
    discounted_price: Decimal
    sell_price: Decimal
    ratings: float
    stock: int
    total_sale: int
    popular: bool
    free_delivery: bool
    hot_deals: bool
    flash_sale: bool
    weight: Optional[float] = None
    isOTC: bool
    isSignature: bool
    is_in_stock: bool
    new_arrival: bool
    today_deals: bool
    created_at: datetime
    updated_at: datetime
    
    # Relations
    category: CategoryBasic
    subcategory: Optional[SubCategoryBasic] = None
    sub_subcategory: Optional[SubSubCategoryBasic] = None
    
    class Config:
        from_attributes = True


class FavoriteItemCreate(BaseModel):
    item_id: int


class FavoriteItemResponse(BaseModel):
    id: int
    customer_id: int
    item_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class FavoriteItemWithDetails(BaseModel):
    id: int
    created_at: datetime
    item: ItemDetail
    
    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    message: str