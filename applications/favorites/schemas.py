# applications/items/favorites/schemas.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


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
    item_id: int
    created_at: datetime
    # Add item details if needed
    # item: ItemSchema


class MessageResponse(BaseModel):
    message: str