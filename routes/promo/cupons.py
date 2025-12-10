from fastapi import APIRouter, Form, Depends, HTTPException, Query
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
        "items": added_items
    }


@router.get("/", dependencies=[Depends(permission_required('view_cupon'))])
async def get_cupons(
    cupon_code: Optional[str] = Query(None),
    min_discount: Optional[int] = Query(None),
    max_discount: Optional[int] = Query(None),
):
    query = Cupon.all()
    if cupon_code:
        query = query.filter(cupon=cupon_code)
    if min_discount is not None:
        query = query.filter(discount__gte=min_discount)
    if max_discount is not None:
        query = query.filter(discount__lte=max_discount)

    cupons = await query
    result = []
    for c in cupons:
        items = await c.items.all()
        used_users = await c.used_by.all()
        result.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "cupon": c.cupon,
            "discount": c.discount,
            "items": [item.id for item in items],
            "used_by": [user.id for user in used_users]
        })
    return result


@router.get("/my_cupon")
async def get_cupons(
    cupon_code: Optional[str] = Query(None),
    min_discount: Optional[int] = Query(None),
    max_discount: Optional[int] = Query(None),
    vendor: User = Depends(vendor_required)
):
    vendor_profile = await vendor.vendor_profile.first()
    query = Cupon.filter(vendor_id=vendor_profile.id)
    if cupon_code:
        query = query.filter(cupon=cupon_code)
    if min_discount is not None:
        query = query.filter(discount__gte=min_discount)
    if max_discount is not None:
        query = query.filter(discount__lte=max_discount)

    cupons = await query
    result = []
    for c in cupons:
        items = await c.items.all()
        used_users = await c.used_by.all()
        result.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "cupon": c.cupon,
            "discount": c.discount,
            "items": [item.id for item in items],
            "used_by": [user.id for user in used_users]
        })
    return result


@router.put("/")
async def update_cupon(
    cupon_id: int = Query(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    discount: Optional[int] = Form(None),
    item_ids: Optional[List[int]] = Form(None),  # optional updated item list
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
    item_slug: Optional[str] = Form(None)
):
    cupon = await Cupon.get_or_none(cupon=cupon_code)
    if not cupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    item = None
    if item_slug is not None:
        item = await Item.get_or_none(slug=item_slug)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

    valid, msg = await cupon.can_apply(user, item)
    return {"valid": valid, "message": msg, "discount": cupon.discount }


async def apply_cupon(
    cupon_code: str = Form(...),
    user: User = Depends(login_required),
    item_slug: Optional[str] = Form(None)
):
    cupon = await Cupon.get_or_none(cupon=cupon_code)
    if not cupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    item = None
    if item_slug is not None:
        item = await Item.get_or_none(item_slug=item_slug)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

    success, msg = await cupon.apply_coupon(user, item)
    return {"success": success, "message": msg}
