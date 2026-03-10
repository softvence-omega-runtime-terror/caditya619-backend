from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, Optional, Sequence


MoneyLike = int | float | str | Decimal


def _to_decimal(value: MoneyLike) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: MoneyLike) -> Decimal:
    return _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _line_total(item: Dict[str, Any]) -> Decimal:
    if "line_total" in item and item["line_total"] is not None:
        return _money(item["line_total"])
    unit_price = _money(item.get("unit_price", 0))
    quantity = int(item.get("quantity", 1) or 1)
    return _money(unit_price * quantity)


def calculate_cart_subtotal(cart_items: Sequence[Dict[str, Any]]) -> Decimal:
    subtotal = Decimal("0")
    for item in cart_items:
        subtotal += _line_total(item)
    return _money(subtotal)


def calculate_discount(
    amount: MoneyLike,
    *,
    percent: MoneyLike = 0,
    flat_amount: MoneyLike = 0,
    max_cap: Optional[MoneyLike] = None,
) -> Decimal:
    base = _money(amount)
    if base <= 0:
        return Decimal("0.00")

    pct_discount = (base * _to_decimal(percent)) / Decimal("100")
    discount = pct_discount + _to_decimal(flat_amount)
    if max_cap is not None:
        discount = min(discount, _to_decimal(max_cap))

    discount = max(Decimal("0"), min(discount, base))
    return _money(discount)


def calculate_delivery_fee(
    *,
    cart_subtotal: MoneyLike,
    base_fee: MoneyLike = 0,
    free_delivery_threshold: MoneyLike = 0,
    distance_km: MoneyLike = 0,
    area_range_km: MoneyLike = 0,
    per_km_fee: MoneyLike = 0,
    extra_pickups: int = 0,
    per_pickup_fee: MoneyLike = 0,
) -> Decimal:
    subtotal = _money(cart_subtotal)
    base = _money(base_fee)

    if _to_decimal(free_delivery_threshold) > 0 and subtotal >= _to_decimal(free_delivery_threshold):
        return Decimal("0.00")

    distance_excess = max(Decimal("0"), _to_decimal(distance_km) - _to_decimal(area_range_km))
    distance_charge = distance_excess * _to_decimal(per_km_fee)
    pickup_charge = max(0, int(extra_pickups)) * _to_decimal(per_pickup_fee)

    return _money(base + distance_charge + pickup_charge)


def _calculate_generic_voucher(
    *,
    cart_items: Sequence[Dict[str, Any]],
    shipping_fee: MoneyLike,
    cart_total: MoneyLike,
    voucher_type: str = "EVENT",
    voucher_percent: MoneyLike = 0,
    voucher_max_cap: MoneyLike = 0,
    voucher_min_order_value: MoneyLike = 0,
    product_scope_categories: Optional[Iterable[str]] = None,
) -> Decimal:
    total = _money(cart_total)
    if total < _to_decimal(voucher_min_order_value):
        return Decimal("0.00")

    normalized_type = (voucher_type or "EVENT").upper()
    if normalized_type == "SHIPPING":
        base_amount = _money(shipping_fee)
    elif normalized_type == "PRODUCT":
        allowed = {str(cat).lower() for cat in (product_scope_categories or [])}
        if not allowed:
            base_amount = Decimal("0")
        else:
            base_amount = sum(
                _line_total(item)
                for item in cart_items
                if str(item.get("category", "")).lower() in allowed
            )
    else:
        base_amount = calculate_cart_subtotal(cart_items)

    discount = (base_amount * _to_decimal(voucher_percent)) / Decimal("100")
    if _to_decimal(voucher_max_cap) > 0:
        discount = min(discount, _to_decimal(voucher_max_cap))

    return _money(max(Decimal("0"), discount))


def calculate_voucher_savings(
    *,
    cart_items: Sequence[Dict[str, Any]],
    shipping_fee: MoneyLike,
    cart_total: MoneyLike,
    voucher: Optional[Any] = None,
    voucher_type: str = "EVENT",
    voucher_percent: MoneyLike = 0,
    voucher_max_cap: MoneyLike = 0,
    voucher_min_order_value: MoneyLike = 0,
    product_scope_categories: Optional[Iterable[str]] = None,
) -> Decimal:
    if voucher is not None and hasattr(voucher, "calculate_savings"):
        pairs = [(str(item.get("category", "")), int(_line_total(item))) for item in cart_items]
        return _money(voucher.calculate_savings(pairs, int(_money(shipping_fee)), int(_money(cart_total))))

    return _calculate_generic_voucher(
        cart_items=cart_items,
        shipping_fee=shipping_fee,
        cart_total=cart_total,
        voucher_type=voucher_type,
        voucher_percent=voucher_percent,
        voucher_max_cap=voucher_max_cap,
        voucher_min_order_value=voucher_min_order_value,
        product_scope_categories=product_scope_categories,
    )


def calculate_total_saving(
    *,
    item_discount: MoneyLike = 0,
    coupon_discount: MoneyLike = 0,
    voucher_saving: MoneyLike = 0,
) -> Decimal:
    total = _to_decimal(item_discount) + _to_decimal(coupon_discount) + _to_decimal(voucher_saving)
    return _money(max(Decimal("0"), total))


def calculate_cart_total(
    *,
    cart_items: Sequence[Dict[str, Any]],
    delivery_base_fee: MoneyLike = 0,
    free_delivery_threshold: MoneyLike = 0,
    distance_km: MoneyLike = 0,
    area_range_km: MoneyLike = 0,
    per_km_fee: MoneyLike = 0,
    extra_pickups: int = 0,
    per_pickup_fee: MoneyLike = 0,
    item_discount_percent: MoneyLike = 0,
    item_discount_flat: MoneyLike = 0,
    item_discount_cap: Optional[MoneyLike] = None,
    coupon_discount_percent: MoneyLike = 0,
    coupon_discount_flat: MoneyLike = 0,
    coupon_discount_cap: Optional[MoneyLike] = None,
    voucher: Optional[Any] = None,
    voucher_type: str = "EVENT",
    voucher_percent: MoneyLike = 0,
    voucher_max_cap: MoneyLike = 0,
    voucher_min_order_value: MoneyLike = 0,
    product_scope_categories: Optional[Iterable[str]] = None,
) -> Dict[str, Decimal]:
    subtotal = calculate_cart_subtotal(cart_items)

    item_discount = calculate_discount(
        subtotal,
        percent=item_discount_percent,
        flat_amount=item_discount_flat,
        max_cap=item_discount_cap,
    )
    subtotal_after_item_discount = _money(max(Decimal("0"), subtotal - item_discount))

    coupon_discount = calculate_discount(
        subtotal_after_item_discount,
        percent=coupon_discount_percent,
        flat_amount=coupon_discount_flat,
        max_cap=coupon_discount_cap,
    )
    discounted_subtotal = _money(max(Decimal("0"), subtotal_after_item_discount - coupon_discount))

    delivery_fee = calculate_delivery_fee(
        cart_subtotal=discounted_subtotal,
        base_fee=delivery_base_fee,
        free_delivery_threshold=free_delivery_threshold,
        distance_km=distance_km,
        area_range_km=area_range_km,
        per_km_fee=per_km_fee,
        extra_pickups=extra_pickups,
        per_pickup_fee=per_pickup_fee,
    )

    pre_voucher_total = _money(discounted_subtotal + delivery_fee)
    voucher_saving = calculate_voucher_savings(
        cart_items=cart_items,
        shipping_fee=delivery_fee,
        cart_total=pre_voucher_total,
        voucher=voucher,
        voucher_type=voucher_type,
        voucher_percent=voucher_percent,
        voucher_max_cap=voucher_max_cap,
        voucher_min_order_value=voucher_min_order_value,
        product_scope_categories=product_scope_categories,
    )
    voucher_saving = _money(min(voucher_saving, pre_voucher_total))

    total_saving = calculate_total_saving(
        item_discount=item_discount,
        coupon_discount=coupon_discount,
        voucher_saving=voucher_saving,
    )
    grand_total = _money(max(Decimal("0"), pre_voucher_total - voucher_saving))

    return {
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "item_discount": item_discount,
        "coupon_discount": coupon_discount,
        "voucher_saving": voucher_saving,
        "total_saving": total_saving,
        "grand_total": grand_total,
    }
