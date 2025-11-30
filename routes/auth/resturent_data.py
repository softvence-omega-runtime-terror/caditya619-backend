from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional

from app.auth import vendor_required
from applications.user.models import User
from applications.user.vendor import VendorProfile, RestaurantProfile
from applications.items.models import SubCategory, Item

router = APIRouter(prefix="/restaurant", tags=["Restaurant"])


# Pydantic model for request body
class RestaurantProfileUpdate(BaseModel):
    cuisines_ids: Optional[List[int]] = Field(default_factory=list, description="List of cuisine SubCategory IDs")
    specialities: Optional[str] = Field(None, description="Specialities of the restaurant")
    signature_dish_ids: Optional[List[int]] = Field(default_factory=list, description="List of signature dish Item IDs")


@router.patch("/update-or-create/")
async def create_or_update_restaurant_profile(
    data: RestaurantProfileUpdate,
    current_user: User = Depends(vendor_required),
):
    """
    Create or update a restaurant profile for the current vendor.
    """
    # Fetch vendor profile
    vendor = await VendorProfile.get_or_none(user_id=current_user.id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Only food vendors can have a restaurant profile
    if vendor.type.lower() != "food":
        raise HTTPException(status_code=400, detail="Vendor type must be 'food'")

    # Get existing RestaurantProfile or create new
    restaurant = await RestaurantProfile.get_or_none(vendor=vendor)
    is_new = False
    if not restaurant:
        restaurant = RestaurantProfile(vendor=vendor)
        is_new = True

    # Update fields
    restaurant.specialities = data.specialities
    await restaurant.save()

    # Validate and update cuisines
    if data.cuisines_ids:
        cuisines = await SubCategory.filter(id__in=data.cuisines_ids, category__type="food")
        if len(cuisines) != len(set(data.cuisines_ids)):
            invalid_ids = set(data.cuisines_ids) - {c.id for c in cuisines}
            raise HTTPException(status_code=400, detail=f"Invalid cuisine IDs: {invalid_ids}")
        await restaurant.cuisines.clear()
        if cuisines:
            await restaurant.cuisines.add(*cuisines)

    # Validate and update signature dishes
    if data.signature_dish_ids:
        items = await Item.filter(id__in=data.signature_dish_ids, category__type="food")
        if len(items) != len(set(data.signature_dish_ids)):
            invalid_ids = set(data.signature_dish_ids) - {i.id for i in items}
            raise HTTPException(status_code=400, detail=f"Invalid signature dish IDs: {invalid_ids}")
        await restaurant.signature_dish.clear()
        if items:
            await restaurant.signature_dish.add(*items)

    # Return response
    return {
        "message": "Restaurant profile created" if is_new else "Restaurant profile updated",
        "restaurant": {
            "id": restaurant.id,
            "specialities": restaurant.specialities,
            "cuisines_ids": [c.id for c in await restaurant.cuisines.all()],
            "signature_dish_ids": [i.id for i in await restaurant.signature_dish.all()]
        }
    }


@router.get("/me/")
async def get_restaurant_profile(current_user: User = Depends(vendor_required)):
    vendor = await VendorProfile.get_or_none(user_id=current_user.id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Ensure vendor type is 'food'
    if vendor.type.lower() != "food":
        raise HTTPException(status_code=400, detail="Vendor type must be 'food'")

    # Fetch restaurant profile
    restaurant = await RestaurantProfile.get_or_none(vendor=vendor)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant profile not found")

    # Fetch related cuisines
    cuisines = await restaurant.cuisines.all()
    cuisines_data = [{"id": c.id, "name": c.name} for c in cuisines]

    # Fetch related signature dishes
    signature_dishes = await restaurant.signature_dish.all()
    signature_dish_data = [
        {
            "id": i.id,
            "title": i.title,
            "price": i.price,
            "discount": i.discount,
            "sell_price": i.sell_price,
         } for i in signature_dishes
    ]

    return {
        "restaurant_id": restaurant.id,
        "specialities": restaurant.specialities,
        "cuisines": cuisines_data,
        "signature_dishes": signature_dish_data
    }


@router.get("/restaurants")
async def get_all_restaurants(
    popular: bool = None
):
    try:
        restaurants = await RestaurantProfile.filter(
            vendor__type="food",
            vendor__is_active=True
        ).prefetch_related("vendor", "cuisines", "signature_dish")

        if not restaurants:
            return {
                "success": True,
                "message": "No restaurants found",
                "data": []
            }

        restaurant_list = []
        for restaurant in restaurants:
            vendor = restaurant.vendor

            # Cuisines
            cuisines_data = [{"id": c.id, "name": c.name} for c in restaurant.cuisines]

            # Signature dishes
            signature_dish_data = [
                {
                    "id": item.id,
                    "title": item.title,
                    "price": float(item.price),
                    "discount": item.discount,
                    "sell_price": float(item.sell_price),
                }
                for item in restaurant.signature_dish
            ]

            restaurant_list.append({
                "restaurant_id": restaurant.id,
                "vendor_id": vendor.id,
                "restaurant_name": vendor.owner_name,
                "photo": vendor.photo,
                "specialities": restaurant.specialities,
                "latitude": vendor.latitude,
                "longitude": vendor.longitude,
                "open_time": vendor.open_time,
                "close_time": vendor.close_time,

                "cuisines": cuisines_data,
                "signature_dishes": signature_dish_data,
            })

        return {
            "success": True,
            "message": "Restaurant list fetched successfully",
            "data": restaurant_list,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
