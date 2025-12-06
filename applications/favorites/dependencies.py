# applications/items/favorites/dependencies.py
from fastapi import Depends, HTTPException, status
from applications.user.models import User
from applications.user.customer import CustomerProfile
from applications.favorites.models import CustomerFavoriteItem
from app.token import get_current_user

async def get_customer_profile(
    current_user: User = Depends(get_current_user)
) -> CustomerProfile:
    """Get the customer profile for the current authenticated user"""
    try:
        customer = await CustomerProfile.get(user=current_user)
        return customer
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer profile not found"
        )


async def verify_favorite_ownership(
    favorite_id: int,
    customer: CustomerProfile = Depends(get_customer_profile)
) -> CustomerFavoriteItem:
    """Verify that the favorite item belongs to the current customer"""
    favorite = await CustomerFavoriteItem.filter(
        id=favorite_id, 
        customer=customer
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite item not found or access denied"
        )
    
    return favorite