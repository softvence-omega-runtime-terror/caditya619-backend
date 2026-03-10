from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import login_required, permission_required
from applications.promo.cupon import Voucher
from applications.user.models import User

router = APIRouter(prefix="/vouchers", tags=["vouchers"])


class VoucherTypeValue(str, Enum):
    PRODUCT = "PRODUCT"
    SHIPPING = "SHIPPING"
    EVENT = "EVENT"


class ProductScopeValue(str, Enum):
    FOOD = "FOOD"
    GROCERY = "GROCERY"
    MEDICINE = "MEDICINE"
    FOOD_GROCERY = "FOOD_GROCERY"
    GROCERY_MEDICINE = "GROCERY_MEDICINE"
    FOOD_MEDICINE = "FOOD_MEDICINE"


class CartItemSchema(BaseModel):
    category: str
    line_total: int = Field(ge=0)


class SavingsRequestSchema(BaseModel):
    cart_items: List[CartItemSchema] = Field(default_factory=list)
    shipping_fee: int = Field(ge=0, default=0)
    cart_total: int = Field(ge=0)


def _parse_optional_datetime(value: Optional[Union[str, datetime]]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        cleaned = value.strip()
        if not cleaned:
            return None
        normalized = cleaned.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid expires_at. Use ISO format, e.g. 2026-12-31T23:59:59",
            ) from exc

    # Normalize to naive UTC to match existing model comparisons.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _is_valid_now(voucher: Voucher) -> bool:
    try:
        return voucher.is_valid_now()
    except TypeError:
        # Fallback for mixed aware/naive datetimes in legacy rows.
        now = datetime.utcnow()
        expires_at = voucher.expires_at
        if expires_at and expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)

        if not voucher.is_active:
            return False
        if expires_at and now > expires_at:
            return False
        if voucher.max_redeem > 0 and voucher.redeemed_count >= voucher.max_redeem:
            return False
        return True


def _voucher_to_dict(voucher: Voucher) -> Dict[str, Any]:
    expires_at = voucher.expires_at.isoformat() if voucher.expires_at else None
    return {
        "id": voucher.id,
        "title": voucher.title,
        "description": voucher.description,
        "voucher_type": _enum_value(voucher.voucher_type),
        "product_scope": _enum_value(voucher.product_scope),
        "event_name": voucher.event_name,
        "min_order_value": voucher.min_order_value,
        "discount_percent": voucher.discount_percent,
        "max_discount_amount": voucher.max_discount_amount,
        # Backward-compatible aliases used by some clients.
        "up_to": voucher.max_discount_amount,
        "max_value": voucher.min_order_value,
        "expires_at": expires_at,
        "max_redeem": voucher.max_redeem,
        "redeemed_count": voucher.redeemed_count,
        "is_active": voucher.is_active,
        "is_valid_now": _is_valid_now(voucher),
    }


def _voucher_pricing_preview(
    voucher: Voucher,
    total_cart_price: int,
    total_shipping_cost: int,
) -> Dict[str, Any]:
    cart_price = max(0, int(total_cart_price))
    shipping_cost = max(0, int(total_shipping_cost))
    combined_total = cart_price + shipping_cost

    minimum_required = int(voucher.min_order_value or 0)
    is_eligible = _is_valid_now(voucher) and combined_total >= minimum_required

    voucher_type = _enum_value(voucher.voucher_type)
    discount_percent = int(voucher.discount_percent or 0)
    max_discount_amount = int(voucher.max_discount_amount or 0)

    discount_base = shipping_cost if voucher_type == VoucherTypeValue.SHIPPING.value else cart_price
    discount_amount = 0

    if is_eligible and discount_base > 0 and discount_percent > 0:
        discount_amount = (discount_base * discount_percent) // 100
        if max_discount_amount > 0:
            discount_amount = min(discount_amount, max_discount_amount)
        discount_amount = max(0, min(discount_amount, discount_base))

    cart_discount_amount = 0
    shipping_discount_amount = 0
    if voucher_type == VoucherTypeValue.SHIPPING.value:
        shipping_discount_amount = discount_amount
    else:
        cart_discount_amount = discount_amount

    final_discounted_price = max(0, cart_price - cart_discount_amount)
    final_discounted_shipping_fee = max(0, shipping_cost - shipping_discount_amount)

    return {
        "is_eligible_for_totals": is_eligible,
        "total_cart_price": cart_price,
        "total_shipping_cost": shipping_cost,
        "discount_amount": discount_amount,
        "cart_discount_amount": cart_discount_amount,
        "shipping_discount_amount": shipping_discount_amount,
        "final_discounted_price": final_discounted_price,
        "final_discounted_shipping_fee": final_discounted_shipping_fee,
        "final_payable_amount": final_discounted_price + final_discounted_shipping_fee,
    }


@router.post("/add", dependencies=[Depends(permission_required("add_voucher"))])
async def create_voucher(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    voucher_type: VoucherTypeValue = Form(...),
    product_scope: Optional[ProductScopeValue] = Form(None),
    event_name: Optional[str] = Form("GENERAL"),
    min_order_value: int = Form(0, ge=0),
    discount_percent: int = Form(0, ge=0, le=100),
    max_discount_amount: int = Form(0, ge=0),
    expires_at: Optional[datetime] = Form(
        default_factory=datetime.utcnow,
        description="ISO-8601 datetime, e.g. 2026-12-31T23:59:59 or 2026-12-31T23:59:59Z",
    ),
    max_redeem: int = Form(0, ge=0),
    is_active: bool = Form(True),
):
    if voucher_type == VoucherTypeValue.PRODUCT and product_scope is None:
        raise HTTPException(status_code=400, detail="product_scope is required for PRODUCT vouchers")
    if voucher_type != VoucherTypeValue.PRODUCT and product_scope is not None:
        raise HTTPException(
            status_code=400,
            detail="product_scope is only allowed for PRODUCT vouchers",
        )
    if voucher_type == VoucherTypeValue.EVENT:
        event_name = (event_name or "GENERAL").strip() or "GENERAL"
    else:
        event_name = None

    parsed_expires_at = _parse_optional_datetime(expires_at)

    create_payload: Dict[str, Any] = {
        "title": title,
        "description": description,
        "voucher_type": voucher_type.value,
        "product_scope": product_scope.value if product_scope else None,
        "event_name": event_name,
        "min_order_value": min_order_value,
        "discount_percent": discount_percent,
        "max_discount_amount": max_discount_amount,
        "max_redeem": max_redeem,
        "is_active": is_active,
    }
    if parsed_expires_at is not None:
        create_payload["expires_at"] = parsed_expires_at

    voucher = await Voucher.create(
        **create_payload,
    )
    return _voucher_to_dict(voucher)


@router.get("/list")
async def list_vouchers(
    voucher_type: Optional[VoucherTypeValue] = Query(None),
    product_scope: Optional[ProductScopeValue] = Query(None),
    event_name: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    min_order_value: Optional[int] = Query(None, ge=0),
    expires_at: Optional[datetime] = Query(
        None,
        description="ISO-8601 datetime, e.g. 2026-12-31T23:59:59 or 2026-12-31T23:59:59Z",
    ),
    max_redeem: Optional[int] = Query(None, ge=0),
    only_valid_now: bool = Query(False),
    total_cart_price: Optional[int] = Query(None, ge=0),
    total_shipping_cost: Optional[int] = Query(None, ge=0),
):
    query = Voucher.all()

    if voucher_type is not None:
        query = query.filter(voucher_type=voucher_type.value)
    if product_scope is not None:
        query = query.filter(product_scope=product_scope.value)
    if event_name:
        stripped_event_name = event_name.strip()
        if stripped_event_name:
            query = query.filter(event_name__icontains=stripped_event_name)
    if is_active is not None:
        query = query.filter(is_active=is_active)
    if min_order_value is not None:
        query = query.filter(min_order_value=min_order_value)
    if max_redeem is not None:
        query = query.filter(max_redeem=max_redeem)
    if expires_at is not None:
        parsed_expires_at = _parse_optional_datetime(expires_at)
        if parsed_expires_at is None:
            query = query.filter(expires_at__isnull=True)
        else:
            query = query.filter(expires_at=parsed_expires_at)

    has_totals_context = total_cart_price is not None or total_shipping_cost is not None
    effective_total_cart_price = total_cart_price if total_cart_price is not None else 0
    effective_total_shipping_cost = total_shipping_cost if total_shipping_cost is not None else 0

    vouchers = await query.order_by("-id")
    if only_valid_now or has_totals_context:
        vouchers = [v for v in vouchers if _is_valid_now(v)]

    if not has_totals_context:
        response: List[Dict[str, Any]] = []
        for voucher in vouchers:
            row = _voucher_to_dict(voucher)
            row["is_best"] = False
            response.append(row)
        return response

    response: List[Dict[str, Any]] = []
    for voucher in vouchers:
        preview = _voucher_pricing_preview(
            voucher=voucher,
            total_cart_price=effective_total_cart_price,
            total_shipping_cost=effective_total_shipping_cost,
        )

        # Totals-aware list should contain only vouchers usable for this cart.
        if not preview["is_eligible_for_totals"] or preview["discount_amount"] <= 0:
            continue

        row = _voucher_to_dict(voucher)
        row.update(preview)
        row["is_best"] = False
        response.append(row)

    if response:
        best_index = max(range(len(response)), key=lambda idx: int(response[idx]["discount_amount"]))
        response[best_index]["is_best"] = True

    return response


@router.get("/{voucher_id}/get")
async def get_voucher(voucher_id: int):
    voucher = await Voucher.get_or_none(id=voucher_id)
    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")
    return _voucher_to_dict(voucher)


@router.put("/{voucher_id}/update", dependencies=[Depends(permission_required("update_voucher"))])
async def update_voucher(
    voucher_id: int,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    voucher_type: Optional[VoucherTypeValue] = Form(None),
    product_scope: Optional[ProductScopeValue] = Form(None),
    event_name: Optional[str] = Form(None),
    min_order_value: Optional[int] = Form(None, ge=0),
    discount_percent: Optional[int] = Form(None, ge=0, le=100),
    max_discount_amount: Optional[int] = Form(None, ge=0),
    expires_at: Optional[datetime] = Form(
        None,
        description="ISO-8601 datetime, e.g. 2026-12-31T23:59:59 or 2026-12-31T23:59:59Z",
    ),
    max_redeem: Optional[int] = Form(None, ge=0),
    is_active: Optional[bool] = Form(None),
):
    voucher = await Voucher.get_or_none(id=voucher_id)
    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")

    next_voucher_type = (
        voucher_type.value if voucher_type is not None else _enum_value(voucher.voucher_type)
    )

    if title is not None:
        voucher.title = title
    if description is not None:
        voucher.description = description
    if voucher_type is not None:
        voucher.voucher_type = voucher_type.value
    if min_order_value is not None:
        voucher.min_order_value = min_order_value
    if discount_percent is not None:
        voucher.discount_percent = discount_percent
    if max_discount_amount is not None:
        voucher.max_discount_amount = max_discount_amount
    if max_redeem is not None:
        voucher.max_redeem = max_redeem
    if is_active is not None:
        voucher.is_active = is_active

    if expires_at is not None:
        voucher.expires_at = _parse_optional_datetime(expires_at)

    if next_voucher_type == VoucherTypeValue.PRODUCT.value:
        if product_scope is not None:
            voucher.product_scope = product_scope.value
        elif not voucher.product_scope:
            raise HTTPException(status_code=400, detail="product_scope is required for PRODUCT vouchers")
    else:
        if product_scope is not None:
            raise HTTPException(
                status_code=400,
                detail="product_scope is only allowed for PRODUCT vouchers",
            )
        voucher.product_scope = None

    if next_voucher_type == VoucherTypeValue.EVENT.value:
        if event_name is not None:
            event_name = event_name.strip()
            if not event_name:
                raise HTTPException(status_code=400, detail="event_name is required for EVENT vouchers")
            voucher.event_name = event_name
        elif not voucher.event_name:
            raise HTTPException(status_code=400, detail="event_name is required for EVENT vouchers")
    else:
        voucher.event_name = None

    await voucher.save()
    return _voucher_to_dict(voucher)


@router.delete("/{voucher_id}/delete", dependencies=[Depends(permission_required("delete_voucher"))])
async def delete_voucher(voucher_id: int):
    voucher = await Voucher.get_or_none(id=voucher_id)
    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")
    await voucher.delete()
    return {"detail": "Voucher deleted successfully"}



@router.post("/{voucher_id}/apply")
async def apply_voucher(
    voucher_id: int,
    payload: SavingsRequestSchema,
    user: User = Depends(login_required),
):
    voucher = await Voucher.get_or_none(id=voucher_id)
    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")

    cart_items = [(item.category, item.line_total) for item in payload.cart_items]
    is_applied, message, savings = await voucher.apply_voucher(
        user=user,
        cart_items=cart_items,
        shipping_fee=payload.shipping_fee,
        cart_total=payload.cart_total,
    )
    if not is_applied:
        raise HTTPException(status_code=400, detail=message)

    return {
        "success": True,
        "message": message,
        "voucher": _voucher_to_dict(voucher),
        "savings": savings,
    }

