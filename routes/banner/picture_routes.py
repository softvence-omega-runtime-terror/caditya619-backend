# routes/picture_routes.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from applications.banner.schemas import (
    PictureCreate, 
    PictureUpdate, 
    PictureResponse, 
    PictureListResponse,
    PictureQueryParams
)
from applications.banner.services import picture_service
from app.token import get_current_user

router = APIRouter(
    prefix="/pictures",
    tags=["pictures"],
    dependencies=[Depends(get_current_user)]
)

@router.post(
    "/",
    response_model=PictureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new picture",
    description="Create a new picture. Only accessible by admin users."
)
async def create_picture(
    picture: PictureCreate,
    current_user = Depends(get_current_user)
):
    """Create a new picture (Admin only)"""
    try:
        new_picture = await picture_service.create_picture(
            picture_data=picture,
            user_id=current_user.id
        )
        
        return PictureResponse(
            id=new_picture.id,
            title=new_picture.title,
            description=new_picture.description,
            image_url=new_picture.image_url,
            thumbnail_url=new_picture.thumbnail_url,
            tags=new_picture.tags,
            category=new_picture.category,
            uploaded_by_id=new_picture.uploaded_by_id,
            is_active=new_picture.is_active,
            created_at=new_picture.created_at,
            updated_at=new_picture.updated_at
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create picture: {str(e)}"
        )

@router.get(
    "/",
    response_model=PictureListResponse,
    summary="Get all pictures",
    description="Retrieve all pictures with optional filtering and pagination. Only accessible by admin users."
)
async def get_all_pictures(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    search: Optional[str] = Query(None, description="Search in title and description"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user = Depends(get_current_user)
):
    """Get all pictures with filtering (Admin only)"""
    try:
        params = PictureQueryParams(
            page=page,
            limit=limit,
            category=category,
            tags=tags,
            search=search,
            is_active=is_active
        )
        result = await picture_service.get_all_pictures(params=params)
        
        pictures_response = [
            PictureResponse(
                id=pic.id,
                title=pic.title,
                description=pic.description,
                image_url=pic.image_url,
                thumbnail_url=pic.thumbnail_url,
                tags=pic.tags,
                category=pic.category,
                uploaded_by_id=pic.uploaded_by_id,
                is_active=pic.is_active,
                created_at=pic.created_at,
                updated_at=pic.updated_at
            )
            for pic in result["pictures"]
        ]
        
        return PictureListResponse(
            pictures=pictures_response,
            total=result["total"],
            page=result["page"],
            limit=result["limit"],
            total_pages=result["total_pages"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pictures: {str(e)}"
        )

@router.get(
    "/{picture_id}",
    response_model=PictureResponse,
    summary="Get picture by ID",
    description="Retrieve a single picture by its ID. Only accessible by admin users."
)
async def get_picture(
    picture_id: int,
    current_user = Depends(get_current_user)
):
    """Get a single picture by ID (Admin only)"""
    picture = await picture_service.get_picture_by_id(picture_id=picture_id)
    
    if not picture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Picture not found"
        )
    
    return PictureResponse(
        id=picture.id,
        title=picture.title,
        description=picture.description,
        image_url=picture.image_url,
        thumbnail_url=picture.thumbnail_url,
        tags=picture.tags,
        category=picture.category,
        uploaded_by_id=picture.uploaded_by_id,
        is_active=picture.is_active,
        created_at=picture.created_at,
        updated_at=picture.updated_at
    )

@router.put(
    "/{picture_id}",
    response_model=PictureResponse,
    summary="Update picture",
    description="Update a picture by its ID. Only accessible by admin users."
)
async def update_picture(
    picture_id: int,
    picture_update: PictureUpdate,
    current_user = Depends(get_current_user)
):
    """Update a picture (Admin only)"""
    try:
        updated_picture = await picture_service.update_picture(
            picture_id=picture_id,
            picture_data=picture_update
        )
        
        if not updated_picture:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Picture not found"
            )
        
        return PictureResponse(
            id=updated_picture.id,
            title=updated_picture.title,
            description=updated_picture.description,
            image_url=updated_picture.image_url,
            thumbnail_url=updated_picture.thumbnail_url,
            tags=updated_picture.tags,
            category=updated_picture.category,
            uploaded_by_id=updated_picture.uploaded_by_id,
            is_active=updated_picture.is_active,
            created_at=updated_picture.created_at,
            updated_at=updated_picture.updated_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update picture: {str(e)}"
        )

@router.delete(
    "/{picture_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete picture",
    description="Permanently delete a picture by its ID. Only accessible by admin users."
)
async def delete_picture(
    picture_id: int,
    current_user = Depends(get_current_user)
):
    """Delete a picture permanently (Admin only)"""
    deleted = await picture_service.delete_picture(picture_id=picture_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Picture not found"
        )
    
    return {"message": "Picture deleted successfully"}

@router.patch(
    "/{picture_id}/deactivate",
    response_model=PictureResponse,
    summary="Deactivate picture",
    description="Soft delete - mark a picture as inactive. Only accessible by admin users."
)
async def deactivate_picture(
    picture_id: int,
    current_user = Depends(get_current_user)
):
    """Soft delete (deactivate) a picture (Admin only)"""
    picture = await picture_service.deactivate_picture(picture_id=picture_id)
    
    if not picture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Picture not found"
        )
    
    return PictureResponse(
        id=picture.id,
        title=picture.title,
        description=picture.description,
        image_url=picture.image_url,
        thumbnail_url=picture.thumbnail_url,
        tags=picture.tags,
        category=picture.category,
        uploaded_by_id=picture.uploaded_by_id,
        is_active=picture.is_active,
        created_at=picture.created_at,
        updated_at=picture.updated_at
    )

@router.get(
    "/category/{category}",
    response_model=PictureListResponse,
    summary="Get pictures by category",
    description="Retrieve all active pictures in a specific category. Only accessible by admin users."
)
async def get_pictures_by_category(
    category: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user = Depends(get_current_user)
):
    """Get pictures by category (Admin only)"""
    try:
        result = await picture_service.get_pictures_by_category(
            category=category,
            page=page,
            limit=limit
        )
        
        pictures_response = [
            PictureResponse(
                id=pic.id,
                title=pic.title,
                description=pic.description,
                image_url=pic.image_url,
                thumbnail_url=pic.thumbnail_url,
                tags=pic.tags,
                category=pic.category,
                uploaded_by_id=pic.uploaded_by_id,
                is_active=pic.is_active,
                created_at=pic.created_at,
                updated_at=pic.updated_at
            )
            for pic in result["pictures"]
        ]
        
        return PictureListResponse(
            pictures=pictures_response,
            total=result["total"],
            page=result["page"],
            limit=result["limit"],
            total_pages=result["total_pages"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pictures: {str(e)}"
        )