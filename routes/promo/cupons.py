from fastapi import APIRouter, Form, Depends, HTTPException, Query
from tortoise.expressions import Q
from typing import Optional, List
import string
import secrets
from applications.promo.cupon import Cupon
from applications.items.models import Item
from applications.user.models import User
from app.auth import login_required, permission_required, vendor_required

router = APIRouter(prefix="/cupons", tags=["cupons"])

# Generate random 6-character coupon code
def generate_cupon_code(length: int = 6) -> str:
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


@router.post("/")
async def create_cupon(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    discount: int = Form(...),
    up_to: int = Form(...),
    max_value: int = Form(...),
    item_ids: Optional[str] = Form(None, description='Accept as comma-separated string'),
    vendor: User = Depends(vendor_required)
):
    cupon_code = generate_cupon_code()
    vendor_profile = await vendor.vendor_profile.first()

    # Create coupon
    coupon = await Cupon.create(
        title=title,
        description=description,
        cupon=cupon_code,
        discount=discount,
        up_to=up_to,
        max_value=max_value,
        vendor=vendor_profile
    )

    # Process item_ids if provided
    added_items = []
    if item_ids:
        # Convert comma-separated string to list of integers
        try:
            ids = [int(x.strip()) for x in item_ids.split(",") if x.strip().isdigit()]
        except ValueError:
            ids = []

        for item_id in ids:
            item = await Item.get_or_none(id=item_id)
            if item:
                await coupon.items.add(item)
                added_items.append(item.id)

    return {
        "id": coupon.id,
        "title": coupon.title,
        "description": coupon.description,
        "cupon": coupon.cupon,
        "discount": coupon.discount,
        "up_to": coupon.up_to,
        "max_value": coupon.max_value,
        "items": added_items
    }


@router.get("/")
async def get_cupons(
    cupon_code: Optional[str] = Query(None),
    min_discount: Optional[int] = Query(None),
    max_discount: Optional[int] = Query(None),
    up_to: Optional[int] = Query(None),  # renamed for clarity
    user: Optional[User] = Depends(login_required)
):
    # Base query
    query = Cupon.all().prefetch_related("items", "used_by")

    if cupon_code:
        query = query.filter(cupon=cupon_code)
    if min_discount is not None:
        query = query.filter(discount__gte=min_discount)
    if max_discount is not None:
        query = query.filter(discount__lte=max_discount)
    if up_to is not None:
        query = query.filter(up_to__lte=up_to)

    # Fetch all matching coupons
    cupons = await query

    # Filter out coupons already used by the current user
    if user:
        cupons = [c for c in cupons if user.id not in [u.id for u in c.used_by]]

    # Return formatted response
    return [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "cupon": c.cupon,
            "discount": c.discount,
            "up_to": c.up_to,
            "max_value": c.max_value,
            "items": [item.id for item in c.items],
            "used_by": [u.id for u in c.used_by]
        }
        for c in cupons
    ]


@router.get("/my_cupon")
async def get_cupons(
    cupon_code: Optional[str] = Query(None),
    min_discount: Optional[int] = Query(None),
    max_discount: Optional[int] = Query(None),
    up_to: Optional[int] = Query(None),  # renamed for clarity
    vendor: User = Depends(vendor_required)
):
    if vendor.is_superuser:
        query = Cupon.all()
    else:
        vendor_profile = await vendor.vendor_profile.first()
        if not vendor_profile:
            return []  # safety check
        query = Cupon.filter(vendor_id=vendor_profile.id)

    if cupon_code:
        query = query.filter(cupon=cupon_code)
    if min_discount is not None:
        query = query.filter(discount__gte=min_discount)
    if max_discount is not None:
        query = query.filter(discount__lte=max_discount)
    if up_to is not None:
        query = query.filter(up_to__lt=up_to)

    cupons = await query.prefetch_related("items", "used_by").all()

    return [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "cupon": c.cupon,
            "discount": c.discount,
            "up_to": c.up_to,
            "max_value": c.max_value,
            "items": [item.id for item in c.items],
            "used_by": [user.id for user in c.used_by]
        }
        for c in cupons
    ]


@router.put("/")
async def update_cupon(
    cupon_id: int = Query(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    discount: Optional[int] = Form(None),
    item_ids: Optional[List[int]] = Form(None),
    up_to: Optional[int] = Form(None),
    max_value: Optional[int] = Form(None),
    vendor: User = Depends(vendor_required)
):
    vendor_profile = await vendor.vendor_profile.first()
    cupon = await Cupon.get_or_none(id=cupon_id, vendor_id=vendor_profile.id)
    if not cupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    if title is not None:
        cupon.title = title
    if description is not None:
        cupon.description = description
    if discount is not None:
        cupon.discount = discount
    if up_to:
        cupon.up_to = up_to
    if max_value is not None:
        cupon.max_value = max_value

    await cupon.save()

    # Update items if provided
    if item_ids is not None:
        await cupon.items.clear()
        for item_id in item_ids:
            item = await Item.get_or_none(id=item_id)
            if item:
                await cupon.items.add(item)

    return {
        "id": cupon.id,
        "title": cupon.title,
        "description": cupon.description,
        "discount": cupon.discount,
        "up_to": cupon.up_to,
        "max_value": cupon.max_value,
        "items": item_ids or []
    }


@router.delete("/")
async def delete_cupon(cupon_id: int = Query(...), vendor: User = Depends(vendor_required)):
    vendor_profile = await vendor.vendor_profile.first()
    cupon = await Cupon.get_or_none(id=cupon_id, vendor_id=vendor_profile.id)
    if not cupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    await cupon.delete()
    return {"detail": "Coupon deleted successfully"}


@router.post("/verify")
async def verify_cupon(
    cupon_code: str = Form(...),
    user: User = Depends(login_required),
    item_id: Optional[int] = Form(None)
):
    # Fetch coupon
    cupon = await Cupon.get_or_none(cupon=cupon_code)
    if not cupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    # Fetch item if provided
    item = None
    if item_id is not None:
        item = await Item.get_or_none(id=item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
    else:
        # If the coupon is item-specific, must provide an item
        related_items = await cupon.items.all()
        if related_items:
            raise HTTPException(
                status_code=400,
                detail="This coupon is applicable only for specific items. Provide item_id."
            )

    # Check if coupon can be applied
    valid, msg = await cupon.can_apply(user, item)

    # Calculate discount info if applicable
    discount_info = None
    if valid and item:
        original_price = item.sell_price
        discount_amount = (original_price * cupon.discount) / 100
        if cupon.max_value:
            discount_amount = min(discount_amount, cupon.max_value)
        final_price = max(original_price - discount_amount, 0)
        discount_info = {
            "original_price": original_price,
            "discount_percent": cupon.discount,
            "discount_amount": round(discount_amount, 2),
            "final_price": round(final_price, 2)
        }

    return {
        "valid": valid,
        "message": msg,
        "discount": discount_info
    }


@router.post("/apply")
async def apply_cupon(
    cupon_code: str = Form(...),
    user: User = Depends(login_required),
    item_id: Optional[int] = Form(None)
):
    # Fetch coupon
    cupon = await Cupon.get_or_none(cupon=cupon_code)
    if not cupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    # Fetch item if provided
    item = None
    if item_id is not None:
        item = await Item.get_or_none(id=item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
    else:
        # If the coupon is item-specific, must provide an item
        related_items = await cupon.items.all()
        if related_items:
            raise HTTPException(status_code=400, detail="This coupon is applicable only for specific items. Provide item_id.")

    # Apply coupon
    success, msg, discount_info = await cupon.apply_coupon(user, item)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    # Return result with discount details
    return {
        "success": True,
        "message": msg,
        "discount": discount_info
    }
