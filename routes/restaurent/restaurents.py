# ============================================
# ROUTES (API Endpoints)
# ============================================
from typing import List, Optional
from decimal import Decimal
from applications.user.models import User
from applications.restaurent.models import SignatureDish
from app.token import get_current_user
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from decimal import Decimal

from applications.restaurent.schemas import (
    VendorRestaurantResponse,
    VendorRestaurantDetailResponse,
    VendorRestaurantUpdate,
    VendorItemResponse,
    SignatureDishCreate,
    SignatureDishResponse,
    FoodCategoryPageResponse,
    VendorReviewCreate,
    VendorReviewResponse
)
from applications.restaurent.services import (
    FoodVendorService,
    VendorItemService,
    FoodCategoryService,
    SignatureDishService,
    VendorReviewService
)

router = APIRouter(prefix="/api/food", tags=["Food & Restaurants"])


# ============== Food Category Page (Home - Image 5 → 3) ==============
@router.get("/category", response_model=FoodCategoryPageResponse)
async def get_food_category_page():
    """
    Get food category page data - When customer clicks "Food" category icon
    Returns:
    - Popular items by specialty (Biryani, Pizza, Burger, Sandwich, Pasta, Breads)
    - Top 25 restaurants (food vendors)
    - All food items
    
    Used in: Image 3, 4, 5
    """
    data = await FoodCategoryService.get_food_category_page_data()
    return data


# ============== Restaurant (Food Vendor) List APIs ==============
@router.get("/restaurants", response_model=List[VendorRestaurantDetailResponse])
async def get_food_restaurants(
    specialty: Optional[str] = Query(None, description="Filter by specialty: food_biryani, food_pizza, etc."),
    is_top_rated: Optional[bool] = None,
    min_rating: Optional[float] = Query(None, ge=0, le=5),
    cuisine: Optional[str] = None,
    is_open: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = Query(25, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get list of food restaurants (vendors with type='food') with filters
    
    Query Parameters:
    - specialty: food_biryani, food_pizza, food_burger, food_sandwich, food_pasta, food_breads
    - is_top_rated: Filter top rated restaurants
    - min_rating: Minimum rating (0-5)
    - cuisine: Filter by cuisine type
    - is_open: Filter by open/closed status
    - search: Search by business name or address
    
    Used in: Image 3 & 4 (Top 25 Restaurants section)
    """
    vendors, total = await FoodVendorService.get_food_vendors(
        specialty=specialty,
        is_top_rated=is_top_rated,
        min_rating=min_rating,
        cuisine=cuisine,
        is_open=is_open,
        search=search,
        limit=limit,
        offset=offset
    )
    return vendors


@router.get("/restaurants/top-rated", response_model=List[VendorRestaurantDetailResponse])
async def get_top_rated_restaurants(limit: int = Query(25, le=100)):
    """
    Get top rated food restaurants (vendors)
    
    Used in: Image 3 & 4 (Top 25 Restaurants section)
    """
    vendors = await FoodVendorService.get_top_food_vendors(limit=limit)
    return vendors


@router.get("/restaurants/{vendor_id}", response_model=VendorRestaurantDetailResponse)
async def get_restaurant_detail(vendor_id: int):
    """
    Get restaurant (food vendor) details by vendor user ID
    Returns vendor profile with signature dishes
    
    Used when: Customer clicks on a restaurant card
    """
    vendor = await FoodVendorService.get_vendor_by_id(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return vendor


# ============== Restaurant Items APIs (Image 1 & 2) ==============
@router.get("/restaurants/{vendor_id}/items", response_model=List[VendorItemResponse])
async def get_restaurant_items(
    vendor_id: int,
    category: str = Query("All", description="Filter by category: All, Appetizers, Biryani, Main Course, Breads"),
    specialty: Optional[str] = Query(None, description="Additional filter by specialty"),
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    is_popular: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get food items for a specific restaurant (vendor)
    
    This is the main endpoint for displaying restaurant menu with category filters
    
    Query Parameters:
    - category: All, Appetizers, Biryani, Main Course, Breads (matches category tabs in UI)
    - specialty: Additional specialty filter
    - min_price/max_price: Price range filter
    - is_popular: Show only popular items
    - search: Search items by title or description
    
    Used in: Image 1 & 2 (Restaurant menu view with category tabs)
    
    Example:
    - All items: /api/food/restaurants/3/items?category=All
    - Only Breads: /api/food/restaurants/3/items?category=Breads
    - Only Biryani: /api/food/restaurants/3/items?category=Biryani
    """
    # Verify vendor exists and is a food vendor
    vendor = await FoodVendorService.get_vendor_by_id(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    items, total = await VendorItemService.get_vendor_items(
        vendor_id=vendor_id,
        category=category,
        specialty=specialty,
        min_price=min_price,
        max_price=max_price,
        is_popular=is_popular,
        search=search,
        limit=limit,
        offset=offset
    )
    
    return items


# ============== All Food Items API ==============
@router.get("/items", response_model=List[VendorItemResponse])
async def get_all_food_items(
    specialty: Optional[str] = Query(None, description="Filter by specialty: Biryani, Pizza, Burger, etc."),
    search: Optional[str] = None,
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get all food items across all food restaurants
    
    Used in: Image 3, 4, 5 (All Food section)
    """
    items, total = await VendorItemService.get_all_food_items(
        specialty=specialty,
        search=search,
        limit=limit,
        offset=offset
    )
    return items


# ============== Popular Items by Specialty ==============
@router.get("/items/popular-by-specialty")
async def get_popular_items_by_specialty():
    """
    Get popular items grouped by specialty
    Returns items grouped by: Biryani, Pizza, Burger, Sandwich, Pasta, Breads
    
    Used in: Image 3, 4 (Popular Items section with circular specialty icons)
    """
    items = await VendorItemService.get_popular_items_by_specialty()
    return items


# ============== Signature Dishes APIs ==============
@router.post("/restaurants/{vendor_id}/signature-dishes", response_model=SignatureDishResponse, status_code=201)
async def create_signature_dish(
    vendor_id: int,
    dish: SignatureDishCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create a signature dish for restaurant (vendor only)
    
    Requires: Vendor authentication
    """
    # Verify vendor exists and user is the vendor
    vendor = await FoodVendorService.get_vendor_by_id(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    if vendor.user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    dish_data = dish.model_dump()
    new_dish = await SignatureDishService.create_signature_dish(dish_data)
    return new_dish


@router.get("/restaurants/{vendor_id}/signature-dishes", response_model=List[SignatureDishResponse])
async def get_restaurant_signature_dishes(vendor_id: int):
    """
    Get all signature dishes for a restaurant (public)
    """
    dishes = await SignatureDishService.get_dishes_by_vendor(vendor_id)
    return dishes


@router.put("/signature-dishes/{dish_id}", response_model=SignatureDishResponse)
async def update_signature_dish(
    dish_id: int,
    dish_data: SignatureDishCreate,
    current_user: User = Depends(get_current_user)
):
    """Update signature dish (vendor only)"""
    
    existing_dish = await SignatureDish.get_or_none(id=dish_id).select_related("vendor")
    if not existing_dish:
        raise HTTPException(status_code=404, detail="Signature dish not found")
    
    if existing_dish.vendor_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    update_data = dish_data.model_dump(exclude_unset=True)
    updated_dish = await SignatureDishService.update_signature_dish(dish_id, update_data)
    
    return updated_dish


@router.delete("/signature-dishes/{dish_id}", status_code=204)
async def delete_signature_dish(
    dish_id: int,
    current_user: User = Depends(get_current_user)
):
    """Delete signature dish (vendor only)"""
    
    existing_dish = await SignatureDish.get_or_none(id=dish_id).select_related("vendor")
    if not existing_dish:
        raise HTTPException(status_code=404, detail="Signature dish not found")
    
    if existing_dish.vendor_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await SignatureDishService.delete_signature_dish(dish_id)
    return {"message": "Signature dish deleted"}


# ============== Vendor Profile Update (Vendor Only) ==============
@router.put("/restaurants/{vendor_id}/profile", response_model=VendorRestaurantResponse)
async def update_restaurant_profile(
    vendor_id: int,
    profile_data: VendorRestaurantUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update restaurant (vendor) profile
    
    Requires: Vendor authentication
    Only the vendor can update their own profile
    """
    if vendor_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")
    
    update_data = profile_data.model_dump(exclude_unset=True)
    updated_vendor = await FoodVendorService.update_vendor_profile(vendor_id, update_data)
    
    if not updated_vendor:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    return updated_vendor


# ============== Restaurant Reviews (Customer) ==============
@router.post("/restaurants/{vendor_id}/reviews", response_model=VendorReviewResponse, status_code=201)
async def create_restaurant_review(
    vendor_id: int,
    review: VendorReviewCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create or update a review for restaurant (customer only)
    
    Requires: Customer authentication
    Note: One review per customer per restaurant
    """
    # Verify vendor exists
    vendor = await FoodVendorService.get_vendor_by_id(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    # Customer cannot review their own restaurant
    if vendor_id == current_user:
        raise HTTPException(status_code=400, detail="Cannot review your own restaurant")
    
    new_review = await VendorReviewService.create_review(
        vendor_id=vendor_id,
        customer_id=current_user,
        rating=review.rating,
        comment=review.comment
    )
    
    return new_review


@router.get("/restaurants/{vendor_id}/reviews", response_model=List[VendorReviewResponse])
async def get_restaurant_reviews(
    vendor_id: int,
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get reviews for a restaurant (public)
    """
    reviews, total = await VendorReviewService.get_vendor_reviews(
        vendor_id=vendor_id,
        limit=limit,
        offset=offset
    )
    return reviews


# ============== Helper Functions ==============
async def get_current_user_id() -> int:
    """
    Get current authenticated user ID
    
    TODO: Implement JWT token verification
    This is a placeholder - you need to implement actual authentication
    
    Example implementation:
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from jose import jwt, JWTError
    
    security = HTTPBearer()
    
    async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
        try:
            token = credentials.credentials
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id: int = payload.get("user_id")
            if user_id is None:
                raise HTTPException(status_code=401, detail="Invalid token")
            return user_id
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")
    """
    # Placeholder - return a test user ID
    # In production, this should decode JWT and return actual user_id
    return 1