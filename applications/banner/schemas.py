# schemas/picture.py
from tortoise.contrib.pydantic import pydantic_model_creator
from pydantic import BaseModel, HttpUrl, Field, field_validator
from typing import Optional, List
from datetime import datetime
from applications.banner.models import Picture

# Tortoise-generated Pydantic models
Picture_Pydantic = pydantic_model_creator(Picture, name="Picture")
PictureIn_Pydantic = pydantic_model_creator(Picture, name="PictureIn", exclude_readonly=True, exclude=("uploaded_by",))

# Custom schemas for API operations
class PictureCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    image_url: str = Field(..., max_length=500)
    thumbnail_url: Optional[str] = Field(None, max_length=500)
    tags: List[str] = Field(default_factory=list)
    category: Optional[str] = Field(None, max_length=100)
    is_active: bool = True

    @field_validator('image_url', 'thumbnail_url')
    @classmethod
    def validate_url(cls, v):
        if v and not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

class PictureUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    image_url: Optional[str] = Field(None, max_length=500)
    thumbnail_url: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = None
    category: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None

    @field_validator('image_url', 'thumbnail_url')
    @classmethod
    def validate_url(cls, v):
        if v and not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

class PictureResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    image_url: str
    thumbnail_url: Optional[str] = None
    tags: List[str]
    category: Optional[str] = None
    uploaded_by_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PictureListResponse(BaseModel):
    pictures: List[PictureResponse]
    total: int
    page: int
    limit: int
    total_pages: int

class PictureQueryParams(BaseModel):
    page: int = Field(1, ge=1)
    limit: int = Field(10, ge=1, le=100)
    category: Optional[str] = None
    tags: Optional[str] = None  # comma-separated
    search: Optional[str] = None
    is_active: Optional[bool] = None