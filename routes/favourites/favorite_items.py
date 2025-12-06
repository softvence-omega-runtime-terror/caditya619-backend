from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from applications.favorites.schemas import (
    FavoriteItemCreate,
    FavoriteItemResponse,
    FavoriteItemWithDetails,
    MessageResponse
)
from applications.favorites.models import CustomerFavoriteItem
from applications.favorites.dependencies import (
    get_customer_profile,
    verify_favorite_ownership
)
from applications.favorites.utils import serialize_item
from applications.user.customer import CustomerProfile
from applications.items.models import Item


router = APIRouter(
    prefix="/favorites",
    tags=["Customer Favorites"]
)


@router.post(
    "/",
    response_model=FavoriteItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add item to favorites"
)
async def add_favorite_item(
    data: FavoriteItemCreate,
    customer: CustomerProfile = Depends(get_customer_profile)
):
    """
    Add an item to the customer's favorite list.
    Customer ID is automatically extracted from the authenticated user.
    """
    # Verify item exists
    item = await Item.filter(id=data.item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    # Check if already favorited
    existing = await CustomerFavoriteItem.filter(
        customer=customer,
        item=item
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item already in favorites"
        )
    
    # Create favorite
    favorite = await CustomerFavoriteItem.create(
        customer=customer,
        item=item
    )
    
    return FavoriteItemResponse(
        id=favorite.id,
        customer_id=customer.id,
        item_id=item.id,
        created_at=favorite.created_at
    )


@router.get(
    "/",
    response_model=List[FavoriteItemWithDetails],
    summary="Get all favorite items with full details"
)
async def get_favorite_items(
    customer: CustomerProfile = Depends(get_customer_profile)
):
    """
    Get all favorite items for the authenticated customer with complete item details.
    Only the customer can see their own favorites.
    Returns all item fields including category, price, stock, ratings, etc.
    """
    favorites = await CustomerFavoriteItem.filter(
        customer=customer
    ).prefetch_related(
        "item",
        "item__category",
        "item__subcategory",
        "item__sub_subcategory"
    ).order_by("-created_at")
    
    result = []
    for fav in favorites:
        item_detail = await serialize_item(fav.item)
        result.append(
            FavoriteItemWithDetails(
                id=fav.id,
                created_at=fav.created_at,
                item=item_detail
            )
        )
    
    return result


@router.get(
    "/{item_id}",
    response_model=FavoriteItemWithDetails,
    summary="Get specific favorite item with full details"
)
async def get_favorite_item(
    item_id: int,
    customer: CustomerProfile = Depends(get_customer_profile)
):
    """
    Get a specific favorite item by item_id for the authenticated customer.
    Returns complete item details.
    """
    favorite = await CustomerFavoriteItem.filter(
        customer=customer,
        item_id=item_id
    ).prefetch_related(
        "item",
        "item__category",
        "item__subcategory",
        "item__sub_subcategory"
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite item not found"
        )
    
    item_detail = await serialize_item(favorite.item)
    
    return FavoriteItemWithDetails(
        id=favorite.id,
        created_at=favorite.created_at,
        item=item_detail
    )


@router.delete(
    "/{item_id}",
    response_model=MessageResponse,
    summary="Remove item from favorites"
)
async def delete_favorite_item(
    item_id: int,
    customer: CustomerProfile = Depends(get_customer_profile)
):
    """
    Remove an item from favorites by item_id.
    Only the owner can delete their own favorite items.
    """
    favorite = await CustomerFavoriteItem.filter(
        customer=customer,
        item_id=item_id
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite item not found"
        )
    
    await favorite.delete()
    
    return MessageResponse(message="Item removed from favorites successfully")


@router.delete(
    "/",
    response_model=MessageResponse,
    summary="Clear all favorites"
)
async def clear_all_favorites(
    customer: CustomerProfile = Depends(get_customer_profile)
):
    """
    Remove all items from the customer's favorite list.
    """
    deleted_count = await CustomerFavoriteItem.filter(
        customer=customer
    ).delete()
    
    return MessageResponse(
        message=f"Removed {deleted_count} items from favorites"
    )