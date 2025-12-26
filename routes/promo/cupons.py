from fastapi import APIRouter, Form, Depends, HTTPException, Query
from typing import Optional
import string
import secrets
from applications.promo.cupon import Cupon
from applications.user.models import User
from app.auth import login_required, vendor_required

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
    uses_limit: int = Form(0),
    vendor: User = Depends(vendor_required)
):
    cupon_code = generate_cupon_code()
    vendor_profile = await vendor.vendor_profile.first()

    coupon = await Cupon.create(
        title=title,
        description=description,
        cupon=cupon_code,
        discount=discount,
        up_to=up_to,
        max_value=max_value,
        uses_limit=uses_limit,
        vendor=vendor_profile
    )

    return {
        "id": coupon.id,
        "title": coupon.title,
        "description": coupon.description,
        "cupon": coupon.cupon,
        "discount": coupon.discount,
        "up_to": coupon.up_to,
        "max_value": coupon.max_value,
        "uses_limit": coupon.uses_limit,
    }


@router.get("/")
async def get_cupons(
    cupon_code: Optional[str] = Query(None),
    min_discount: Optional[int] = Query(None),
    max_discount: Optional[int] = Query(None),
    up_to: Optional[int] = Query(None),
    user: Optional[User] = Depends(login_required)
):
    query = Cupon.all().prefetch_related("used_by")

    if cupon_code:
        query = query.filter(cupon=cupon_code)
    if min_discount is not None:
        query = query.filter(discount__gte=min_discount)
    if max_discount is not None:
        query = query.filter(discount__lte=max_discount)
    if up_to is not None:
        query = query.filter(up_to__lte=up_to)

    cupons = await query

    if user:
        cupons = [c for c in cupons if user.id not in [u.id for u in c.used_by]]

    return [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "cupon": c.cupon,
            "discount": c.discount,
            "up_to": c.up_to,
            "max_value": c.max_value,
            "uses_limit": c.uses_limit,
            "used_by": [u.id for u in c.used_by]
        }
        for c in cupons
    ]


@router.get("/my_cupon")
async def get_my_cupons(
    cupon_code: Optional[str] = Query(None),
    min_discount: Optional[int] = Query(None),
    max_discount: Optional[int] = Query(None),
    up_to: Optional[int] = Query(None),
    vendor: User = Depends(vendor_required)
):
    if vendor.is_superuser:
        query = Cupon.all()
    else:
        vendor_profile = await vendor.vendor_profile.first()
        if not vendor_profile:
            return []
        query = Cupon.filter(vendor_id=vendor_profile.id)

    if cupon_code:
        query = query.filter(cupon=cupon_code)
    if min_discount is not None:
        query = query.filter(discount__gte=min_discount)
    if max_discount is not None:
        query = query.filter(discount__lte=max_discount)
    if up_to is not None:
        query = query.filter(up_to__lte=up_to)

    cupons = await query.prefetch_related("used_by")

    return [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "cupon": c.cupon,
            "discount": c.discount,
            "up_to": c.up_to,
            "max_value": c.max_value,
            "uses_limit": c.uses_limit,
            "used_by": [u.id for u in c.used_by]
        }
        for c in cupons
    ]


@router.put("/")
async def update_cupon(
    cupon_id: int = Query(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    discount: Optional[int] = Form(None),
    up_to: Optional[int] = Form(None),
    max_value: Optional[int] = Form(None),
    uses_limit: Optional[int] = Form(None),
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
    if up_to is not None:
        cupon.up_to = up_to
    if max_value is not None:
        cupon.max_value = max_value
    if uses_limit is not None:
        cupon.uses_limit = uses_limit

    await cupon.save()

    return {
        "id": cupon.id,
        "title": cupon.title,
        "description": cupon.description,
        "discount": cupon.discount,
        "up_to": cupon.up_to,
        "max_value": cupon.max_value,
        "uses_limit": cupon.uses_limit,
    }


@router.delete("/")
async def delete_cupon(cupon_id: int = Query(...), vendor: User = Depends(vendor_required)):
    vendor_profile = await vendor.vendor_profile.first()
    cupon = await Cupon.get_or_none(id=cupon_id, vendor_id=vendor_profile.id)
    if not cupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    await cupon.delete()
    return {"detail": "Coupon deleted successfully"}


@router.post("/apply")
async def apply_cupon(
    cupon_code: str = Form(...),
    user: User = Depends(login_required),
):
    cupon = await Cupon.get_or_none(cupon=cupon_code)
    if not cupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    success, msg = await cupon.apply_coupon(user)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return {
        "success": True,
        "message": msg,
        "discount": cupon.discount,
        "up_to": cupon.up_to,
        "max_value": cupon.max_value,
        "uses_limit": cupon.uses_limit,
    }
