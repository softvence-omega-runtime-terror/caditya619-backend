# services/picture_service.py
from tortoise.expressions import Q
from tortoise.queryset import QuerySet
from typing import Dict, Optional
from applications.banner.models import Picture
from applications.banner.schemas import PictureCreate, PictureUpdate, PictureQueryParams
import math

class PictureService:
    
    @staticmethod
    async def create_picture(picture_data: PictureCreate, user_id: int) -> Picture:
        """Create a new picture"""
        picture = await Picture.create(
            **picture_data.model_dump(),
            uploaded_by_id=user_id
        )
        await picture.fetch_related('uploaded_by')
        return picture
    
    @staticmethod
    async def get_all_pictures(params: PictureQueryParams) -> Dict:
        """Get all pictures with filtering and pagination"""
        query = Picture.all()
        
        # Apply filters
        filters = Q()
        
        if params.category:
            filters &= Q(category=params.category)
        
        if params.tags:
            tag_list = [tag.strip() for tag in params.tags.split(',')]
            # Check if any of the tags exist in the tags JSON field
            for tag in tag_list:
                filters &= Q(tags__contains=tag)
        
        if params.search:
            search_filter = Q(title__icontains=params.search) | Q(description__icontains=params.search)
            filters &= search_filter
        
        if params.is_active is not None:
            filters &= Q(is_active=params.is_active)
        
        query = query.filter(filters)
        
        # Get total count
        total = await query.count()
        
        # Apply pagination
        skip = (params.page - 1) * params.limit
        pictures = await query.offset(skip).limit(params.limit).prefetch_related('uploaded_by')
        
        total_pages = math.ceil(total / params.limit) if total > 0 else 0
        
        return {
            "pictures": pictures,
            "total": total,
            "page": params.page,
            "limit": params.limit,
            "total_pages": total_pages
        }
    
    @staticmethod
    async def get_picture_by_id(picture_id: int) -> Optional[Picture]:
        """Get a single picture by ID"""
        try:
            picture = await Picture.get(id=picture_id).prefetch_related('uploaded_by')
            return picture
        except Exception:
            return None
    
    @staticmethod
    async def update_picture(picture_id: int, picture_data: PictureUpdate) -> Optional[Picture]:
        """Update a picture"""
        try:
            picture = await Picture.get(id=picture_id)
            
            # Update only provided fields
            update_data = picture_data.model_dump(exclude_unset=True)
            await picture.update_from_dict(update_data)
            await picture.save()
            await picture.fetch_related('uploaded_by')
            
            return picture
        except Exception:
            return None
    
    @staticmethod
    async def delete_picture(picture_id: int) -> bool:
        """Delete a picture permanently"""
        try:
            picture = await Picture.get(id=picture_id)
            await picture.delete()
            return True
        except Exception:
            return False
    
    @staticmethod
    async def deactivate_picture(picture_id: int) -> Optional[Picture]:
        """Soft delete - mark picture as inactive"""
        try:
            picture = await Picture.get(id=picture_id)
            picture.is_active = False
            await picture.save()
            await picture.fetch_related('uploaded_by')
            return picture
        except Exception:
            return None
    
    @staticmethod
    async def get_pictures_by_category(category: str, page: int = 1, limit: int = 10) -> Dict:
        """Get pictures by category"""
        query = Picture.filter(category=category, is_active=True)
        
        total = await query.count()
        skip = (page - 1) * limit
        pictures = await query.offset(skip).limit(limit).prefetch_related('uploaded_by')
        
        total_pages = math.ceil(total / limit) if total > 0 else 0
        
        return {
            "pictures": pictures,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages
        }

picture_service = PictureService()